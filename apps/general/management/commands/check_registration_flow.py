"""
Answers "why did no email arrive?" without needing a mailbox in your hand.

Run it on the box that serves registration (demo or production):

    python manage.py check_registration_flow
    python manage.py check_registration_flow --send-to me@example.com

Registration email travels four hops, and a break in any one of them looks
identical from outside: the API still returns 201 "check your email" because
_send_set_password_email swallows its exception, and the RQ worker's failure
is a log line nobody is tailing. The hops are:

    view -> Redis queue -> RQ worker -> EmailTemplate row -> SMTP

This walks all four and names the one that is broken. The template check is
the hop that catches out a fresh environment: templates are uploaded through
the admin, never seeded from the repo, so a new database has none of them and
every send returns False after logging "TEMPLATE NOT FOUND".

--send-to proves the last hop for real: it sends synchronously, in this
process, so an SMTP rejection surfaces here as a traceback instead of inside
a worker. Add --via-queue to post the same mail through Redis instead, which
proves the worker is consuming as well.
"""

import smtplib

from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.core.management.base import BaseCommand

from apps.general.models import EmailTemplate
from apps.general.services.base_email_service import BaseEmailService

# template_type values the registration and password flows ask for by name.
# Missing ones are fatal for the flow named beside them.
REQUIRED_TEMPLATES = {
    "set-password": "candidate registration (and quiz sign-up)",
    "reset-password": "password recovery",
    "confirm-recruiter": "recruiter approval",
    "rejected-recruiter": "recruiter rejection",
}


class Command(BaseCommand):
    help = "Check the registration email pipeline and web Google sign-in configuration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send-to",
            metavar="EMAIL",
            help="Send a real test email to this address to prove SMTP end to end.",
        )
        parser.add_argument(
            "--via-queue",
            action="store_true",
            help="With --send-to, post the test mail through RQ instead of sending it inline, "
                 "which also proves a worker is consuming the queue.",
        )

    def handle(self, *args, **options):
        self.failures = 0

        self.stdout.write(self.style.MIGRATE_HEADING("SMTP configuration"))
        self._check_smtp_settings()

        self.stdout.write(self.style.MIGRATE_HEADING("SMTP connection"))
        self._check_smtp_connection()

        self.stdout.write(self.style.MIGRATE_HEADING("Queue"))
        self._check_redis()
        self._check_workers()

        self.stdout.write(self.style.MIGRATE_HEADING("Email templates"))
        self._check_templates()

        self.stdout.write(self.style.MIGRATE_HEADING("Links and sign-in"))
        self._check_frontend_url()
        self._check_google_client_id()

        if options["send_to"]:
            self.stdout.write(self.style.MIGRATE_HEADING("Test send"))
            self._send_test(options["send_to"], options["via_queue"])

        self.stdout.write("")
        if self.failures:
            self.stderr.write(self.style.ERROR(f"{self.failures} check(s) failed."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("All checks passed."))

    # --- reporting -----------------------------------------------------------

    def _ok(self, label, detail=""):
        self.stdout.write(f"  {self.style.SUCCESS('OK')}   {label}" + (f" — {detail}" if detail else ""))

    def _fail(self, label, detail):
        self.failures += 1
        self.stdout.write(f"  {self.style.ERROR('FAIL')} {label} — {detail}")

    def _warn(self, label, detail):
        self.stdout.write(f"  {self.style.WARNING('WARN')} {label} — {detail}")

    # --- smtp ----------------------------------------------------------------

    def _check_smtp_settings(self):
        host = getattr(settings, "EMAIL_HOST", None)
        if not host:
            self._fail("EMAIL_HOST", "unset")
        elif host in ("localhost", "127.0.0.1"):
            self._fail(
                "EMAIL_HOST",
                f"{host} — the settings default, meaning EMAIL_HOST is missing from this "
                "environment's .env file. Nothing listens there, so every send fails",
            )
        else:
            self._ok("EMAIL_HOST", f"{host}:{getattr(settings, 'EMAIL_PORT', '?')}")

        if not getattr(settings, "EMAIL_HOST_USER", None):
            self._fail("EMAIL_HOST_USER", "unset — the relay will reject an unauthenticated session")
        else:
            self._ok("EMAIL_HOST_USER", settings.EMAIL_HOST_USER)

        if not getattr(settings, "EMAIL_HOST_PASSWORD", None):
            self._fail("EMAIL_HOST_PASSWORD", "unset")
        else:
            self._ok("EMAIL_HOST_PASSWORD", "set")

        if not getattr(settings, "DEFAULT_FROM_EMAIL", None):
            self._fail("DEFAULT_FROM_EMAIL", "unset — send_mail() has no envelope sender")
        else:
            self._ok("DEFAULT_FROM_EMAIL", settings.DEFAULT_FROM_EMAIL)

        port = getattr(settings, "EMAIL_PORT", None)
        tls = getattr(settings, "EMAIL_USE_TLS", False)
        ssl = getattr(settings, "EMAIL_USE_SSL", False)
        if port == 587 and not tls:
            self._warn(
                "EMAIL_USE_TLS",
                "False on port 587 — set EMAIL_USE_TLS=True (the value is compared to the "
                "string 'True', so 'true' or '1' will not enable it)",
            )
        elif port == 465 and not ssl:
            self._warn("EMAIL_USE_SSL", "False on port 465 — implicit TLS expected there")
        else:
            self._ok("Transport security", f"TLS={tls} SSL={ssl}")

    def _check_smtp_connection(self):
        backend = getattr(settings, "EMAIL_BACKEND", "")
        if "smtp" not in backend:
            self._warn("EMAIL_BACKEND", f"{backend} — not SMTP, no mail leaves this host")
            return

        connection = get_connection(fail_silently=False, timeout=10)
        try:
            connection.open()
        except smtplib.SMTPAuthenticationError as exc:
            self._fail(
                "SMTP login",
                f"rejected ({exc.smtp_code} {exc.smtp_error!r}) — for a Google Workspace "
                "sender EMAIL_HOST_PASSWORD must be a 16-character app password, not the "
                "account password",
            )
            return
        except Exception as exc:
            self._fail("SMTP connect", f"{type(exc).__name__}: {exc}")
            return

        self._ok("SMTP connect + login", f"{settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
        try:
            connection.close()
        except Exception:
            pass

    # --- queue ---------------------------------------------------------------

    def _check_redis(self):
        url = getattr(settings, "REDIS_URL", None)
        try:
            BaseEmailService.get_redis_connection().ping()
        except Exception as exc:
            self._fail("Redis unreachable", f"{url} — {type(exc).__name__}: {exc}. No email can be queued")
            return
        self._ok("Redis reachable", url)

        # The worker resolves its queue through django-rq's RQ_QUEUES, the
        # enqueue side through settings.REDIS_URL. Same value everywhere today,
        # but if they ever drift the jobs land in a queue nobody is watching.
        queue_url = (getattr(settings, "RQ_QUEUES", {}).get("default") or {}).get("URL")
        if queue_url and queue_url != url:
            self._fail(
                "Queue URL mismatch",
                f"enqueue uses {url}, RQ_QUEUES['default'] uses {queue_url} — "
                "jobs are written where no worker reads",
            )

    def _check_workers(self):
        try:
            from rq import Worker
        except ImportError as exc:
            self._warn("RQ", f"not importable ({exc})")
            return

        try:
            queue = BaseEmailService.get_queue()
            workers = Worker.all(queue=queue)
        except Exception as exc:
            self._fail("RQ worker lookup", f"{type(exc).__name__}: {exc}")
            return

        if not workers:
            self._fail(
                "RQ workers",
                "none listening on the 'default' queue — mail is queued and never sent. "
                "Check the rq-worker container is up",
            )
        else:
            self._ok("RQ workers", f"{len(workers)} listening on 'default'")

        try:
            pending = len(queue)
        except Exception:
            pending = None
        if pending:
            self._warn("Queue backlog", f"{pending} job(s) pending on 'default'")

        self._report_failed_jobs(queue)

    def _report_failed_jobs(self, queue):
        """A failed job carries the real reason — surface the newest one."""
        try:
            from rq.registry import FailedJobRegistry

            registry = FailedJobRegistry(queue=queue)
            job_ids = registry.get_job_ids()
        except Exception:
            return

        if not job_ids:
            self._ok("Failed job registry", "empty")
            return

        self._warn("Failed jobs", f"{len(job_ids)} in the failed registry")
        try:
            from rq.job import Job

            job = Job.fetch(job_ids[-1], connection=queue.connection)
            reason = (job.latest_result().exc_string if job.latest_result() else None) or "no traceback stored"
            self.stdout.write(f"       newest: {job.func_name}")
            self.stdout.write("       " + reason.strip().splitlines()[-1][:300])
        except Exception:
            pass

    # --- templates -----------------------------------------------------------

    def _check_templates(self):
        """
        A missing row is the quiet failure: the worker logs TEMPLATE NOT FOUND,
        returns False, and the caller already told the user to check their inbox.
        """
        for template_type, used_by in REQUIRED_TEMPLATES.items():
            rows = EmailTemplate.objects.filter(template_type=template_type)
            if not rows.exists():
                self._fail(
                    f"template '{template_type}'",
                    f"no row in the database — {used_by} sends nothing. Upload the HTML "
                    "through the admin (General > Email templates)",
                )
                continue

            languages = sorted(rows.values_list("language", flat=True))
            unreadable = [row.language for row in rows if not self._body_readable(row)]
            if unreadable:
                self._fail(
                    f"template '{template_type}'",
                    f"row exists for {languages} but the body file is missing from media "
                    f"storage for {unreadable} — re-upload it (media is not shared between "
                    "environments)",
                )
            else:
                self._ok(f"template '{template_type}'", f"languages {languages}")

    @staticmethod
    def _body_readable(row):
        try:
            row.body.open("r")
        except Exception:
            return False
        try:
            return bool(row.body.read())
        except Exception:
            return False
        finally:
            try:
                row.body.close()
            except Exception:
                pass

    # --- links and sign-in ---------------------------------------------------

    def _check_frontend_url(self):
        url = getattr(settings, "FRONTEND_URL", None)
        if not url:
            self._fail(
                "FRONTEND_URL",
                "unset — set-password links render as 'None/set-password/...' and no "
                "recipient can complete registration",
            )
        elif not url.startswith(("http://", "https://")):
            self._fail("FRONTEND_URL", f"{url} — missing scheme, the link will not resolve")
        elif url.endswith("/"):
            self._warn("FRONTEND_URL", f"{url} — trailing slash produces a '//set-password' link")
        else:
            self._ok("FRONTEND_URL", url)

    def _check_google_client_id(self):
        client_id = getattr(settings, "APP_CLIENT_ID", None)
        if not client_id:
            self._fail(
                "APP_CLIENT_ID",
                "unset — POST /auth/google/ verifies the ID token against an empty audience "
                "and always answers 401 INVALID_GOOGLE_TOKEN",
            )
            return
        self._ok("APP_CLIENT_ID", client_id)
        if not client_id.endswith(".apps.googleusercontent.com"):
            self._warn("APP_CLIENT_ID", "does not look like a Google OAuth client id")
        self.stdout.write(
            "       note: the browser must send an ID token minted for THIS client id, so the\n"
            "       frontend's NEXT_PUBLIC_GOOGLE_CLIENT_ID has to match it, and this host's\n"
            "       origin must be listed under the client's Authorized JavaScript origins."
        )

    # --- test send -----------------------------------------------------------

    def _send_test(self, to_email, via_queue):
        subject = "WorkXplorer registration flow check"
        body = "<p>If you are reading this, SMTP delivery works from this host.</p>"

        if via_queue:
            try:
                job = BaseEmailService.enqueue_job(
                    _test_email_worker, to_email, subject, body
                )
            except Exception as exc:
                self._fail("Queued test email", f"{type(exc).__name__}: {exc}")
                return
            self._ok("Queued test email", f"job {job.id} — check the worker log and the inbox")
            return

        try:
            sent = send_mail(
                subject=subject,
                message="If you are reading this, SMTP delivery works from this host.",
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[to_email],
                html_message=body,
                fail_silently=False,
            )
        except Exception as exc:
            self._fail("Inline test email", f"{type(exc).__name__}: {exc}")
            return

        if sent:
            self._ok("Inline test email", f"accepted by the relay for {to_email}")
        else:
            self._fail("Inline test email", "the relay accepted 0 recipients")


def _test_email_worker(to_email, subject, body):
    """Module-level so RQ can import it by path in the worker process."""
    BaseEmailService.send_email(to_email=to_email, subject=subject, body=body)
    return True
