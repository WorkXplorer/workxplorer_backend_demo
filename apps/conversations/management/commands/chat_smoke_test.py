"""End-to-end smoke test for realtime chat.

Drives the whole path a real user takes — issue a ticket, open a WebSocket to
the gateway, send a message, watch it get persisted and delivered — and
checks the security boundaries along the way.

Run it after ``docker compose up`` to confirm the two services are talking:

    python manage.py chat_smoke_test

It creates two throwaway accounts and one conversation (reused on later
runs), so it needs a writable database. It refuses to run against production.

The WebSocket client is written against the raw protocol rather than a
library, so the test exercises the actual wire format and the project gains
no new dependency.
"""

import base64
import json
import os
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

CANDIDATE_EMAIL = "chat-smoke-candidate@workxplorer.local"
RECRUITER_EMAIL = "chat-smoke-recruiter@workxplorer.local"


# ---------------------------------------------------------------------------
# Minimal WebSocket client (RFC 6455, text frames only)
# ---------------------------------------------------------------------------

class SimpleWebSocket:
    """Just enough WebSocket to send and receive JSON frames."""

    def __init__(self, url, ticket, timeout=10):
        parsed = urllib.parse.urlparse(url)
        secure = parsed.scheme == "wss"
        host = parsed.hostname
        port = parsed.port or (443 if secure else 80)
        path = parsed.path or "/"

        raw = socket.create_connection((host, port), timeout=timeout)
        if secure:
            raw = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        self.sock = raw

        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET {path}?ticket={urllib.parse.quote(ticket)} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )

        self.buffer = b""
        header = self._read_until(b"\r\n\r\n")
        try:
            self.status = int(header.split(b" ")[1])
        except (IndexError, ValueError):
            self.status = 0

        self.frames = []
        # Read cursor, so wait_for() never re-matches a frame a previous call
        # already consumed — otherwise a later assertion can pass on an
        # earlier frame and hide a real failure.
        self.cursor = 0
        self.close_code = None

        if self.status == 101:
            threading.Thread(target=self._reader, daemon=True).start()

    def _read_until(self, marker):
        while marker not in self.buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            self.buffer += chunk
        head, _, rest = self.buffer.partition(marker)
        self.buffer = rest
        return head

    def _recv_exactly(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("socket closed")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def _reader(self):
        try:
            while True:
                first, second = self._recv_exactly(2)
                opcode = first & 0x0F
                length = second & 0x7F
                if length == 126:
                    length = struct.unpack(">H", self._recv_exactly(2))[0]
                elif length == 127:
                    length = struct.unpack(">Q", self._recv_exactly(8))[0]
                payload = self._recv_exactly(length) if length else b""

                if opcode == 0x1:
                    self.frames.append(json.loads(payload))
                elif opcode == 0x9:
                    self._send_frame(0xA, payload)  # answer the gateway's ping
                elif opcode == 0x8:
                    self.close_code = (
                        struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else 1005
                    )
                    return
        except Exception:
            return

    def _send_frame(self, opcode, payload):
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 1 << 16:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(header + mask + masked)

    def send(self, frame_type, data=None):
        self._send_frame(0x1, json.dumps({"type": frame_type, "data": data or {}}).encode())

    def wait_for(self, frame_type, timeout=8):
        deadline = time.time() + timeout
        while time.time() < deadline:
            while self.cursor < len(self.frames):
                frame = self.frames[self.cursor]
                self.cursor += 1
                if frame.get("type") == frame_type:
                    return frame
            time.sleep(0.05)
        return None

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class Command(BaseCommand):
    help = "End-to-end smoke test of the realtime chat path (platform + gateway)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ws-url",
            default=None,
            help="Gateway WebSocket URL. Defaults to settings.CHAT_WS_URL.",
        )
        parser.add_argument(
            "--internal-url",
            default=None,
            help="Gateway internal URL. Defaults to settings.CHAT_INTERNAL_URL.",
        )
        parser.add_argument(
            "--platform-url",
            default=None,
            help=(
                "This platform's own API root, as the gateway reaches it. Used by "
                "the preflight to check the running server rather than this "
                "process. Defaults to http://127.0.0.1:8000/api/v1."
            ),
        )
        parser.add_argument(
            "--keep",
            action="store_true",
            help="Keep the messages this run created instead of deleting them.",
        )
        parser.add_argument(
            "--preflight-only",
            action="store_true",
            help=(
                "Run only the read-only configuration checks: is the gateway "
                "reachable, and do this process, the running web server and the "
                "gateway agree on CHAT_SERVICE_KEY. Creates nothing, so it is "
                "allowed in production."
            ),
        )

    def handle(self, *args, **options):
        preflight_only = options["preflight_only"]

        if os.getenv("DJANGO_ENVIRONMENT") == "production" and not preflight_only:
            raise CommandError(
                "Refusing to run against production — this command creates accounts "
                "and messages. Use --preflight-only for the read-only checks, which "
                "are safe here."
            )
        if not settings.CHAT_ENABLED:
            raise CommandError("CHAT_ENABLED is false; nothing to test.")

        self.ws_url = options["ws_url"] or settings.CHAT_WS_URL
        self.internal_url = (options["internal_url"] or settings.CHAT_INTERNAL_URL).rstrip("/")
        self.platform_url = (
            options["platform_url"] or "http://127.0.0.1:8000/api/v1"
        ).rstrip("/")
        self.failures = []

        self.stdout.write("=" * 68)
        self.stdout.write("Realtime chat smoke test")
        self.stdout.write(f"  gateway ws:       {self.ws_url}")
        self.stdout.write(f"  gateway internal: {self.internal_url}")
        self.stdout.write("=" * 68)

        if preflight_only:
            # Any user id will do — the peers endpoint is a read, and what is
            # being tested is whether the call is authorized at all.
            candidate = self._any_user()
            if candidate is None:
                raise CommandError("No users in the database to check the peers endpoint with.")
            if not self._preflight(candidate):
                raise CommandError("Preflight failed — see above.")
            self.stdout.write("=" * 68)
            self.stdout.write(self.style.SUCCESS("Preflight passed."))
            return

        candidate, recruiter, conversation = self._fixtures()

        # Preflight before the functional checks. Without it a secret mismatch
        # produces eight unrelated-looking failures spread across every
        # section, and the actual cause is only visible in the gateway's log.
        if not self._preflight(candidate):
            raise CommandError("Preflight failed — fix the above before re-running.")

        message_ids_before = self._message_ids(conversation)

        try:
            self._run_checks(candidate, recruiter, conversation)
        finally:
            if not options["keep"]:
                self._cleanup(conversation, message_ids_before)

        self.stdout.write("=" * 68)
        if self.failures:
            raise CommandError(
                f"{len(self.failures)} check(s) failed: " + "; ".join(self.failures)
            )
        self.stdout.write(self.style.SUCCESS("All checks passed."))

    # -- helpers ------------------------------------------------------------

    def _check(self, label, ok, detail=""):
        if ok:
            self.stdout.write(self.style.SUCCESS(f"  PASS  {label}"))
        else:
            self.stdout.write(self.style.ERROR(f"  FAIL  {label}" + (f" — {detail}" if detail else "")))
            self.failures.append(label)

    def _any_user(self):
        """Return an existing user, for read-only checks that need an id."""
        from apps.authentication.models import CustomUser

        return CustomUser.objects.order_by("id").first()

    def _preflight(self, candidate):
        """Verify the three parties agree on the shared secrets.

        Chat spans three processes — this command, the long-running web
        server, and the gateway — and each reads its own copy of the
        environment. A mismatch between any two of them is by far the most
        common failure, so it is worth localising precisely instead of
        letting it surface as unrelated symptoms later.
        """
        self.stdout.write("\nPreflight")
        ok = True

        # 1. Is the gateway even there?
        try:
            with urllib.request.urlopen(self.internal_url + "/healthz", timeout=5):
                pass
        except (urllib.error.URLError, OSError) as exc:
            self.stdout.write(self.style.ERROR(f"  FAIL  the gateway is reachable — {exc}"))
            self.stdout.write(
                self.style.WARNING(
                    f"\n  Nothing is answering at {self.internal_url}.\n"
                    "  Start the gateway, and check CHAT_INTERNAL_URL points at it.\n"
                    "  From inside a container, 127.0.0.1 is the container itself —\n"
                    "  you may need host.docker.internal or a host-network setup."
                )
            )
            return False
        self.stdout.write(self.style.SUCCESS("  PASS  the gateway is reachable"))

        # 2. Does the gateway accept *this process's* service key?
        try:
            request = urllib.request.Request(
                self.internal_url + "/internal/stats",
                headers={"X-Chat-Service-Key": settings.CHAT_SERVICE_KEY},
            )
            urllib.request.urlopen(request, timeout=5)
            self.stdout.write(self.style.SUCCESS("  PASS  the gateway accepts our CHAT_SERVICE_KEY"))
        except urllib.error.HTTPError as exc:
            ok = False
            self.stdout.write(
                self.style.ERROR(f"  FAIL  the gateway accepts our CHAT_SERVICE_KEY — status {exc.code}")
            )
            self.stdout.write(
                self.style.WARNING(
                    "\n  This process and the gateway disagree on CHAT_SERVICE_KEY.\n"
                    "  They must be byte-identical. Check for quotes around the value\n"
                    "  in the gateway's .env — docker compose keeps them, python-dotenv\n"
                    "  strips them, so \"abc\" and abc end up different."
                )
            )
        except (urllib.error.URLError, OSError) as exc:
            ok = False
            self.stdout.write(self.style.ERROR(f"  FAIL  the gateway accepts our CHAT_SERVICE_KEY — {exc}"))

        # 3. Does the *running web server* agree with this process? This is
        #    the hop the gateway actually uses, and the one that breaks when a
        #    container was started before .env was filled in: `manage.py` in a
        #    fresh `exec` re-reads the file, the server does not.
        peers_url = (
            f"{self.platform_url}/conversations/internal/peers/"
            f"?user_id={candidate.id}"
        )
        try:
            request = urllib.request.Request(
                peers_url, headers={"X-Chat-Service-Key": settings.CHAT_SERVICE_KEY}
            )
            urllib.request.urlopen(request, timeout=5)
            self.stdout.write(
                self.style.SUCCESS("  PASS  the running web server shares our CHAT_SERVICE_KEY")
            )
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                ok = False
                self.stdout.write(
                    self.style.ERROR(
                        "  FAIL  the running web server shares our CHAT_SERVICE_KEY "
                        f"— status {exc.code}"
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        "\n  The web server serving the gateway's requests has a DIFFERENT\n"
                        "  CHAT_SERVICE_KEY than this command does. Almost always this means\n"
                        "  the container was started before the value was added to the env\n"
                        "  file: `docker compose exec` re-reads it, the running server does\n"
                        "  not.\n\n"
                        "      docker compose -f docker-compose.dev.yml up -d --force-recreate \\\n"
                        "          workxplorer-backend\n\n"
                        "  Symptom if ignored: the WebSocket connects fine and then every\n"
                        "  message, typing event and read receipt is rejected with a 403."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  SKIP  could not check the running web server — status {exc.code}"
                    )
                )
        except (urllib.error.URLError, OSError) as exc:
            # A TLS error on a URL we asked for over plain HTTP means the
            # request was redirected to https:// and the client followed it
            # into a handshake with a server that speaks neither. That is
            # SECURE_SSL_REDIRECT catching an internal call that arrives over
            # loopback without X-Forwarded-Proto — and it is not a skippable
            # condition, it is the whole feature being broken.
            if "ssl" in str(exc).lower() or "handshake" in str(exc).lower():
                ok = False
                self.stdout.write(
                    self.style.ERROR(
                        "  FAIL  the running web server shares our CHAT_SERVICE_KEY "
                        f"— TLS error on a plain-HTTP URL ({exc})"
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        "\n  This platform is redirecting internal API calls to https://.\n"
                        "  SECURE_SSL_REDIRECT applies to the gateway's loopback calls,\n"
                        "  which have no nginx in front to set X-Forwarded-Proto, so Django\n"
                        "  answers 301 to a port that serves plain HTTP. The caller hangs on\n"
                        "  a handshake that cannot complete while a worker here burns trying\n"
                        "  to parse a TLS ClientHello as an HTTP request.\n\n"
                        "  Fix: add the internal paths to SECURE_REDIRECT_EXEMPT.\n\n"
                        "  Symptom if ignored: every message fails with 'context deadline\n"
                        "  exceeded' in the gateway, and the whole site slows down."
                    )
                )
            else:
                # Not fatal: the server may simply not be reachable at the
                # assumed URL (different port, or run outside a container).
                self.stdout.write(
                    self.style.WARNING(
                        f"  SKIP  could not reach this platform at {self.platform_url} ({exc}); "
                        "pass --platform-url to check it"
                    )
                )

        return ok

    def _fixtures(self):
        from apps.authentication.models import Candidate, Company, Recruiter
        from apps.conversations.models import Conversation
        from apps.profiles.models import CandidateProfile, RecruiterProfile
        from apps.vacancies.models import Vacancy

        company, _ = Company.objects.get_or_create(
            tin="000000001",
            defaults={"name": "Chat Smoke Test Co", "is_active": True},
        )

        recruiter = Recruiter.objects.filter(email=RECRUITER_EMAIL).first()
        if not recruiter:
            recruiter = Recruiter.objects.create_user(
                email=RECRUITER_EMAIL, password=os.urandom(16).hex(),
                is_recruiter=True, company=company,
            )
            RecruiterProfile.objects.create(recruiter=recruiter, full_name="Smoke Recruiter")

        candidate = Candidate.objects.filter(email=CANDIDATE_EMAIL).first()
        if not candidate:
            candidate = Candidate.objects.create_user(
                email=CANDIDATE_EMAIL, password=os.urandom(16).hex(), is_candidate=True,
            )
            CandidateProfile.objects.create(candidate=candidate, full_name="Smoke Candidate")

        vacancy, _ = Vacancy.objects.get_or_create(
            title="Chat Smoke Test Vacancy", created_by=recruiter,
            defaults={"company": company, "is_active": True},
        )

        conversation = Conversation.objects.filter(
            candidate=candidate, recruiter=recruiter
        ).first()
        if not conversation:
            conversation = Conversation.objects.create(
                candidate=candidate, recruiter=recruiter, vacancy=vacancy,
            )

        self.stdout.write(f"\nFixtures: conversation {conversation.id}\n")
        return candidate, recruiter, conversation

    def _message_ids(self, conversation):
        return set(conversation.messages.values_list("id", flat=True))

    def _cleanup(self, conversation, before):
        created = conversation.messages.exclude(id__in=before)
        count = created.count()
        created.delete()
        if count:
            self.stdout.write(f"\nCleaned up {count} message(s) created by this run.")

    def _connect(self, user):
        from apps.conversations.tickets import issue_ticket

        payload = issue_ticket(user)
        return SimpleWebSocket(self.ws_url, payload["ticket"]), payload["ticket"]

    def _internal_post(self, path, body):
        request = urllib.request.Request(
            self.internal_url + path,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Chat-Service-Key": settings.CHAT_SERVICE_KEY,
            },
        )
        return urllib.request.urlopen(request, timeout=5)

    # -- the checks ---------------------------------------------------------

    def _run_checks(self, candidate, recruiter, conversation):
        from apps.conversations.models import Message

        conversation_id = str(conversation.id)

        # --- handshake -----------------------------------------------------
        self.stdout.write("Handshake")

        bogus = SimpleWebSocket(self.ws_url, "not-a-real-ticket")
        self._check("a bogus ticket is refused", bogus.status == 401, f"status {bogus.status}")
        bogus.close()

        candidate_ws, used_ticket = self._connect(candidate)
        self._check(
            "a valid ticket opens the socket",
            candidate_ws.status == 101,
            f"status {candidate_ws.status}",
        )
        if candidate_ws.status != 101:
            # Nothing below can work; fail fast with a useful hint.
            self.stdout.write(
                self.style.WARNING(
                    "\n  The gateway refused the handshake. Check that CHAT_JWT_SECRET "
                    "is identical on both services and that CHAT_WS_URL points at the "
                    "gateway."
                )
            )
            return

        replay = SimpleWebSocket(self.ws_url, used_ticket)
        self._check("the same ticket cannot be reused", replay.status == 401, f"status {replay.status}")
        replay.close()

        connected = candidate_ws.wait_for("connected")
        self._check("gateway greets with `connected`", connected is not None)
        if connected:
            self._check(
                "the connection carries the ticket's identity",
                connected["data"]["user_id"] == str(candidate.id),
            )

        recruiter_ws, _ = self._connect(recruiter)
        self._check("the recruiter connects too", recruiter_ws.status == 101)
        recruiter_ws.wait_for("connected")

        # --- delivery ------------------------------------------------------
        self.stdout.write("\nMessage delivery")

        body = "Smoke test message"
        candidate_ws.send("message.send", {
            "conversation_id": conversation_id,
            "content": body,
            "client_msg_id": "smoke-1",
        })

        ack = candidate_ws.wait_for("message.ack")
        self._check("the sender gets an ack", ack is not None)

        delivered = recruiter_ws.wait_for("message.new")
        self._check("the other party receives it", delivered is not None)
        if delivered:
            self._check(
                "content survives the round trip",
                delivered["data"]["message"]["content"] == body,
                delivered["data"]["message"]["content"],
            )

        if ack:
            self._check(
                "the message is in the database",
                Message.objects.filter(id=ack["data"]["message_id"]).exists(),
            )

        # --- security ------------------------------------------------------
        self.stdout.write("\nSecurity boundaries")

        candidate_ws.send("message.send", {
            "conversation_id": conversation_id,
            "content": "Claiming to be someone else",
            "client_msg_id": "smoke-spoof",
            "user_id": str(recruiter.id),
            "role": "RECRUITER",
        })
        spoofed = recruiter_ws.wait_for("message.new")
        self._check(
            "a frame claiming another identity is still attributed to the sender",
            spoofed is not None and spoofed["data"]["message"]["sender_type"] == "CANDIDATE",
            spoofed["data"]["message"]["sender_type"] if spoofed else "no frame",
        )

        candidate_ws.send("message.send", {
            "conversation_id": "00000000-0000-7000-0000-000000000000",
            "content": "Should never land",
            "client_msg_id": "smoke-foreign",
        })
        refused = candidate_ws.wait_for("message.error")
        self._check(
            "writing into a foreign conversation is refused",
            refused is not None and refused["data"]["code"] in ("NOT_FOUND", "FORBIDDEN"),
            refused["data"]["code"] if refused else "no frame",
        )

        try:
            request = urllib.request.Request(
                self.internal_url + "/internal/publish",
                data=json.dumps({"user_ids": [str(candidate.id)], "event": {"type": "x"}}).encode(),
                headers={"Content-Type": "application/json", "X-Chat-Service-Key": "wrong"},
            )
            urllib.request.urlopen(request, timeout=5)
            self._check("the internal API rejects a bad service key", False, "request succeeded")
        except urllib.error.HTTPError as exc:
            self._check("the internal API rejects a bad service key", exc.code == 401, f"status {exc.code}")

        # --- typing and receipts -------------------------------------------
        self.stdout.write("\nTyping and read receipts")

        candidate_ws.send("typing.start", {"conversation_id": conversation_id})
        typing = recruiter_ws.wait_for("typing")
        self._check("typing reaches the other party", typing is not None and typing["data"]["is_typing"])

        recruiter_ws.send("conversation.read", {"conversation_id": conversation_id})
        receipt = candidate_ws.wait_for("conversation.read")
        self._check("read receipts reach the other party", receipt is not None)

        # --- platform -> gateway --------------------------------------------
        self.stdout.write("\nServer-generated events")

        try:
            response = self._internal_post("/internal/publish", {
                "user_ids": [str(candidate.id)],
                "event": {
                    "type": "message.new",
                    "data": {
                        "conversation_id": conversation_id,
                        "message": {"id": "smoke-server", "message_type": "STATUS_CHANGE"},
                    },
                },
            })
            self._check("the platform can publish to the gateway", response.status == 202)
        except (urllib.error.URLError, OSError) as exc:
            self._check(
                "the platform can publish to the gateway", False,
                f"{exc} — check CHAT_INTERNAL_URL ({self.internal_url})",
            )

        pushed = candidate_ws.wait_for("message.new")
        self._check("a pushed event reaches the client", pushed is not None)

        # --- revocation ------------------------------------------------------
        self.stdout.write("\nSession revocation")

        try:
            self._internal_post("/internal/disconnect", {
                "user_ids": [str(recruiter.id)], "reason": "smoke_test",
            })
        except (urllib.error.URLError, OSError) as exc:
            self._check("the platform can close sockets", False, str(exc))

        deadline = time.time() + 5
        while recruiter_ws.close_code is None and time.time() < deadline:
            time.sleep(0.1)
        self._check(
            "a revoked session is closed with 4009",
            recruiter_ws.close_code == 4009,
            f"close code {recruiter_ws.close_code}",
        )

        candidate_ws.close()
        recruiter_ws.close()
