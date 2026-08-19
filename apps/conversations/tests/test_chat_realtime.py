"""Tests for the realtime chat integration.

Three surfaces are covered:

- ``/conversations/ws-ticket/`` — what a client exchanges its session for.
- ``/conversations/internal/*`` — what the Go gateway calls on a user's
  behalf. These act on a ``user_id`` supplied in the request body, so the
  tests lean hard on the authorization boundary: a valid service key must not
  let the gateway write into a conversation its user is not part of.
- ``apps.conversations.realtime`` — the push side, which must never let a
  gateway outage break a request.
"""

import json
from unittest.mock import patch

import jwt
import requests
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Candidate, Company, Recruiter
from apps.conversations.models import Conversation, Message, MessageType
from apps.conversations.quotas import CODE_DAILY_LIMIT, CODE_HOURLY_LIMIT
from apps.conversations.tickets import ROLE_CANDIDATE, ROLE_RECRUITER
from apps.profiles.models import CandidateProfile, RecruiterProfile
from apps.vacancies.models import Vacancy

SERVICE_KEY = "test-chat-service-key-that-is-long-enough"
CHAT_SECRET = "test-chat-jwt-secret-that-is-long-enough"


class ChatTestData(APITestCase):
    """Shared fixture: one recruiter, two candidates, one conversation."""

    def setUp(self):
        self.company = Company.objects.create(name="Test Company", tin="123456789", is_active=True)

        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com", password="testpass123",
            is_recruiter=True, company=self.company,
        )
        RecruiterProfile.objects.create(recruiter=self.recruiter, full_name="Test Recruiter")

        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123", is_candidate=True,
        )
        CandidateProfile.objects.create(candidate=self.candidate, full_name="Test Candidate")

        # A second candidate, used to prove that being a valid chat user does
        # not grant access to somebody else's conversation.
        self.outsider = Candidate.objects.create_user(
            email="outsider@test.com", password="testpass123", is_candidate=True,
        )
        CandidateProfile.objects.create(candidate=self.outsider, full_name="Outsider")

        self.vacancy = Vacancy.objects.create(
            title="Software Developer", created_by=self.recruiter,
            company=self.company, is_active=True,
        )

        self.conversation = Conversation.objects.create(
            candidate=self.candidate,
            recruiter=self.recruiter,
            vacancy=self.vacancy,
            is_read_by_candidate=True,
            is_read_by_recruiter=True,
        )

    def service_post(self, url, payload):
        return self.client.post(
            url, data=json.dumps(payload), content_type="application/json",
            HTTP_X_CHAT_SERVICE_KEY=SERVICE_KEY,
        )

    def service_get(self, url, params=None):
        return self.client.get(url, params or {}, HTTP_X_CHAT_SERVICE_KEY=SERVICE_KEY)


@override_settings(
    CHAT_ENABLED=True,
    CHAT_JWT_SECRET=CHAT_SECRET,
    CHAT_SERVICE_KEY=SERVICE_KEY,
    CHAT_WS_URL="wss://chat.example.test/ws",
)
class ChatTicketTests(ChatTestData):
    """The handshake credential."""

    def setUp(self):
        super().setUp()
        self.url = reverse("chat-ws-ticket")

    def decode(self, token):
        return jwt.decode(
            token, CHAT_SECRET, algorithms=["HS256"],
            audience=settings.CHAT_TICKET_AUDIENCE,
            issuer=settings.CHAT_TICKET_ISSUER,
        )

    def test_anonymous_user_cannot_get_a_ticket(self):
        response = self.client.post(self.url)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_candidate_receives_a_ticket_scoped_to_themselves(self):
        self.client.force_authenticate(user=self.candidate)

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()["data"]
        self.assertEqual(data["role"], ROLE_CANDIDATE)
        self.assertEqual(data["ws_url"], "wss://chat.example.test/ws")

        claims = self.decode(data["ticket"])
        self.assertEqual(claims["sub"], str(self.candidate.id))
        self.assertEqual(claims["role"], ROLE_CANDIDATE)
        self.assertEqual(claims["typ"], settings.CHAT_TICKET_TYPE)

    def test_recruiter_receives_a_recruiter_ticket(self):
        self.client.force_authenticate(user=self.recruiter)

        claims = self.decode(self.client.post(self.url).json()["data"]["ticket"])
        self.assertEqual(claims["sub"], str(self.recruiter.id))
        self.assertEqual(claims["role"], ROLE_RECRUITER)

    def test_tickets_are_single_use_by_construction(self):
        """Every issued ticket carries a distinct jti.

        The gateway refuses to accept a jti twice, which only works if the
        platform never mints the same one again.
        """
        self.client.force_authenticate(user=self.candidate)

        first = self.decode(self.client.post(self.url).json()["data"]["ticket"])
        second = self.decode(self.client.post(self.url).json()["data"]["ticket"])
        self.assertNotEqual(first["jti"], second["jti"])

    def test_ticket_is_short_lived(self):
        self.client.force_authenticate(user=self.candidate)

        claims = self.decode(self.client.post(self.url).json()["data"]["ticket"])
        self.assertLessEqual(claims["exp"] - claims["iat"], 300)

    def test_ticket_is_not_signed_with_the_api_secret(self):
        """A leaked chat secret must not be usable against the API."""
        self.client.force_authenticate(user=self.candidate)
        token = self.client.post(self.url).json()["data"]["ticket"]

        with self.assertRaises(jwt.InvalidSignatureError):
            jwt.decode(
                token, settings.JWT_SECRET_KEY, algorithms=["HS256"],
                audience=settings.CHAT_TICKET_AUDIENCE,
                issuer=settings.CHAT_TICKET_ISSUER,
            )

    @override_settings(CHAT_ENABLED=False)
    def test_disabled_chat_reports_unavailable(self):
        self.client.force_authenticate(user=self.candidate)

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)


@override_settings(CHAT_ENABLED=True, CHAT_SERVICE_KEY=SERVICE_KEY)
class InternalMessageTests(ChatTestData):
    """Persisting a message the gateway received over a socket."""

    def setUp(self):
        super().setUp()
        self.url = reverse("chat-internal-message-create")

    def payload(self, **overrides):
        data = {
            "user_id": str(self.candidate.id),
            "role": ROLE_CANDIDATE,
            "conversation_id": str(self.conversation.id),
            "content": "Hello, I am interested",
            "client_msg_id": "client-1",
        }
        data.update(overrides)
        return data

    # --- authentication ---------------------------------------------------

    def test_request_without_the_service_key_is_rejected(self):
        response = self.client.post(
            self.url, data=json.dumps(self.payload()), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Message.objects.count(), 0)

    def test_request_with_a_wrong_service_key_is_rejected(self):
        response = self.client.post(
            self.url, data=json.dumps(self.payload()), content_type="application/json",
            HTTP_X_CHAT_SERVICE_KEY="not-the-key",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Message.objects.count(), 0)

    @override_settings(CHAT_SERVICE_KEY="")
    def test_unset_service_key_fails_closed(self):
        """An empty configured key must not match an empty header.

        Otherwise a misconfigured deployment would let any anonymous caller
        post messages as any user.
        """
        response = self.client.post(
            self.url, data=json.dumps(self.payload()), content_type="application/json",
            HTTP_X_CHAT_SERVICE_KEY="",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Message.objects.count(), 0)

    # --- authorization ----------------------------------------------------

    def test_outsider_cannot_write_to_a_conversation(self):
        response = self.service_post(self.url, self.payload(user_id=str(self.outsider.id)))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Message.objects.count(), 0)

    def test_participant_cannot_write_as_the_other_side(self):
        """The candidate's own id with the recruiter's role must not work.

        Membership is checked against the column matching the claimed role,
        so a participant cannot post messages attributed to their
        counterpart.
        """
        response = self.service_post(
            self.url, self.payload(user_id=str(self.candidate.id), role=ROLE_RECRUITER)
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Message.objects.count(), 0)

    def test_unknown_conversation_is_not_found(self):
        response = self.service_post(
            self.url,
            self.payload(conversation_id="0197e0c1-2f3a-7c4d-9b21-000000000000"),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unsupported_role_is_rejected(self):
        response = self.service_post(self.url, self.payload(role="ADMIN"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- persistence ------------------------------------------------------

    def test_message_is_persisted_and_attributed_to_the_sender(self):
        response = self.service_post(self.url, self.payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        message = Message.objects.get()
        self.assertEqual(message.conversation, self.conversation)
        self.assertEqual(message.sender_type, ROLE_CANDIDATE)
        self.assertEqual(message.message_type, MessageType.TEXT)
        self.assertEqual(message.content, "Hello, I am interested")
        self.assertFalse(message.is_read)

    def test_response_tells_the_gateway_who_to_deliver_to(self):
        data = self.service_post(self.url, self.payload()).json()["data"]

        self.assertEqual(data["message_id"], str(Message.objects.get().id))
        self.assertCountEqual(
            data["recipients"],
            [str(self.candidate.id), str(self.recruiter.id)],
        )

    def test_serialized_message_matches_the_rest_shape(self):
        """The socket and a page load must produce the same message object."""
        message = self.service_post(self.url, self.payload()).json()["data"]["message"]

        self.assertEqual(
            set(message.keys()),
            {
                "id", "sender_type", "message_type", "title", "content",
                "metadata", "is_read", "hunting_status", "created_at",
            },
        )

    def test_sending_marks_the_conversation_unread_for_the_recipient(self):
        self.service_post(self.url, self.payload())

        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.is_read_by_candidate)
        self.assertFalse(self.conversation.is_read_by_recruiter)

    def test_recruiter_sending_flips_the_flags_the_other_way(self):
        self.service_post(
            self.url, self.payload(user_id=str(self.recruiter.id), role=ROLE_RECRUITER)
        )

        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.is_read_by_recruiter)
        self.assertFalse(self.conversation.is_read_by_candidate)

    # --- content handling -------------------------------------------------
    #
    # Chat bubbles are rendered as HTML on the client, so message bodies get
    # two layers of defence: InputValidationMiddleware rejects overtly
    # malicious payloads before the view runs, and everything that does reach
    # the view is run through the shared bleach allowlist.

    def test_obvious_xss_payloads_are_rejected_outright(self):
        response = self.service_post(
            self.url,
            self.payload(content='Hi <script>alert("xss")</script>'),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Message.objects.count(), 0)

    def test_event_handler_attributes_are_rejected_outright(self):
        response = self.service_post(
            self.url, self.payload(content='<img src=x onerror=alert(1)>')
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Message.objects.count(), 0)

    def test_markup_past_the_middleware_is_still_sanitized(self):
        """The middleware's patterns are not the only thing standing between
        a chat message and ``innerHTML``.

        An ``<iframe>`` carries no script and no event handler, so it sails
        past the middleware — the allowlist is what removes it.
        """
        self.service_post(
            self.url,
            self.payload(content='Look <iframe src="https://evil.example"></iframe> here'),
        )

        content = Message.objects.get().content
        self.assertNotIn("<iframe", content)
        self.assertIn("Look", content)
        self.assertIn("here", content)

    def test_style_and_form_markup_is_stripped(self):
        self.service_post(
            self.url,
            self.payload(content='<style>body{display:none}</style><form action="/x"></form>Hi'),
        )

        content = Message.objects.get().content
        self.assertNotIn("<style", content)
        self.assertNotIn("<form", content)
        self.assertIn("Hi", content)

    def test_safe_formatting_survives(self):
        self.service_post(self.url, self.payload(content="<p>Hello <strong>there</strong></p>"))

        self.assertEqual(Message.objects.get().content, "<p>Hello <strong>there</strong></p>")

    def test_plain_text_survives_unchanged(self):
        self.service_post(self.url, self.payload(content="Salom! 5 > 3 & 2 < 4"))

        # bleach escapes the bare angle brackets rather than dropping them,
        # so the text still renders as the user typed it.
        content = Message.objects.get().content
        self.assertIn("Salom!", content)
        self.assertNotIn("<script", content)

    def test_empty_content_is_rejected(self):
        response = self.service_post(self.url, self.payload(content="   \n  "))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Message.objects.count(), 0)

    def test_content_that_sanitizes_to_nothing_is_rejected(self):
        response = self.service_post(self.url, self.payload(content="<script>alert(1)</script>"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Message.objects.count(), 0)

    def test_non_string_content_is_rejected(self):
        response = self.service_post(self.url, self.payload(content={"evil": True}))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(CHAT_MAX_MESSAGE_LENGTH=50)
    def test_oversized_content_is_rejected(self):
        response = self.service_post(self.url, self.payload(content="x" * 51))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Message.objects.count(), 0)


@override_settings(CHAT_ENABLED=True, CHAT_SERVICE_KEY=SERVICE_KEY)
class InternalMarkReadTests(ChatTestData):
    """Read receipts arriving over the socket."""

    def setUp(self):
        super().setUp()
        self.url = reverse("chat-internal-mark-read")

        self.from_recruiter = Message.objects.create(
            conversation=self.conversation, sender_type=ROLE_RECRUITER,
            message_type=MessageType.TEXT, content="Are you available?", is_read=False,
        )
        self.from_candidate = Message.objects.create(
            conversation=self.conversation, sender_type=ROLE_CANDIDATE,
            message_type=MessageType.TEXT, content="Yes", is_read=False,
        )

    def test_reading_marks_only_the_counterparts_messages(self):
        response = self.service_post(self.url, {
            "user_id": str(self.candidate.id),
            "role": ROLE_CANDIDATE,
            "conversation_id": str(self.conversation.id),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.from_recruiter.refresh_from_db()
        self.from_candidate.refresh_from_db()
        self.assertTrue(self.from_recruiter.is_read)
        # The candidate reading must not mark their own outbox as seen by the
        # recruiter.
        self.assertFalse(self.from_candidate.is_read)

    def test_receipt_is_addressed_to_the_other_party_only(self):
        data = self.service_post(self.url, {
            "user_id": str(self.candidate.id),
            "role": ROLE_CANDIDATE,
            "conversation_id": str(self.conversation.id),
        }).json()["data"]

        self.assertEqual(data["recipients"], [str(self.recruiter.id)])

    def test_outsider_cannot_mark_a_conversation_read(self):
        response = self.service_post(self.url, {
            "user_id": str(self.outsider.id),
            "role": ROLE_CANDIDATE,
            "conversation_id": str(self.conversation.id),
        })

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.from_recruiter.refresh_from_db()
        self.assertFalse(self.from_recruiter.is_read)


@override_settings(CHAT_ENABLED=True, CHAT_SERVICE_KEY=SERVICE_KEY)
class InternalMembershipTests(ChatTestData):
    """Participant lookups, which double as the permission check for typing."""

    def setUp(self):
        super().setUp()
        self.url = reverse("chat-internal-membership")

    def test_participant_gets_the_participant_list(self):
        response = self.service_get(self.url, {
            "conversation_id": str(self.conversation.id),
            "user_id": str(self.candidate.id),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        participants = response.json()["data"]["participants"]
        self.assertCountEqual(
            [(p["user_id"], p["role"]) for p in participants],
            [
                (str(self.candidate.id), ROLE_CANDIDATE),
                (str(self.recruiter.id), ROLE_RECRUITER),
            ],
        )

    def test_outsider_is_refused(self):
        """Without this, typing frames would be a conversation-id oracle."""
        response = self.service_get(self.url, {
            "conversation_id": str(self.conversation.id),
            "user_id": str(self.outsider.id),
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_conversation_is_not_found(self):
        response = self.service_get(self.url, {
            "conversation_id": "0197e0c1-2f3a-7c4d-9b21-000000000000",
            "user_id": str(self.candidate.id),
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(CHAT_ENABLED=True, CHAT_SERVICE_KEY=SERVICE_KEY)
class InternalPeersTests(ChatTestData):
    """Presence is scoped to people the user actually talks to."""

    def setUp(self):
        super().setUp()
        self.url = reverse("chat-internal-peers")

    def test_candidate_sees_their_recruiters(self):
        response = self.service_get(self.url, {"user_id": str(self.candidate.id)})

        self.assertEqual(response.json()["data"]["user_ids"], [str(self.recruiter.id)])

    def test_recruiter_sees_their_candidates(self):
        response = self.service_get(self.url, {"user_id": str(self.recruiter.id)})

        self.assertEqual(response.json()["data"]["user_ids"], [str(self.candidate.id)])

    def test_user_without_conversations_has_no_peers(self):
        response = self.service_get(self.url, {"user_id": str(self.outsider.id)})

        self.assertEqual(response.json()["data"]["user_ids"], [])


@override_settings(
    CHAT_ENABLED=True,
    CHAT_SERVICE_KEY=SERVICE_KEY,
    CHAT_INTERNAL_URL="http://chat.internal.test:8081",
)
class RealtimePublishTests(ChatTestData):
    """The push side must never be able to break a request."""

    def test_broadcast_pushes_to_both_participants(self):
        from apps.conversations.realtime import broadcast_message

        message = Message.objects.create(
            conversation=self.conversation, sender_type=ROLE_RECRUITER,
            message_type=MessageType.TEXT, content="Hello", is_read=False,
        )

        # Publishing is deferred to commit on purpose, so that a rolled-back
        # transaction cannot announce a message that no longer exists.
        with patch("apps.conversations.realtime._session.post") as post:
            post.return_value.status_code = 202
            with self.captureOnCommitCallbacks(execute=True):
                broadcast_message(message, conversation=self.conversation)

        pushed = {call.kwargs["json"]["user_ids"][0] for call in post.call_args_list}
        self.assertEqual(pushed, {str(self.candidate.id), str(self.recruiter.id)})

        for call in post.call_args_list:
            body = call.kwargs["json"]
            self.assertEqual(body["event"]["type"], "message.new")
            self.assertEqual(
                body["event"]["data"]["conversation_id"], str(self.conversation.id)
            )
            self.assertEqual(
                call.kwargs["headers"]["X-Chat-Service-Key"], SERVICE_KEY
            )

    def test_gateway_outage_does_not_raise(self):
        """A message is committed before it is published.

        If the gateway is unreachable the recipient loses a live update, not
        a message — so the exception must stop here.
        """
        from apps.conversations.realtime import broadcast_message

        message = Message.objects.create(
            conversation=self.conversation, sender_type=ROLE_RECRUITER,
            message_type=MessageType.TEXT, content="Hello", is_read=False,
        )

        with patch(
            "apps.conversations.realtime._session.post",
            side_effect=requests.ConnectionError("gateway down"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                broadcast_message(message, conversation=self.conversation)

    def test_gateway_error_response_does_not_raise(self):
        from apps.conversations.realtime import publish

        with patch("apps.conversations.realtime._session.post") as post:
            post.return_value.status_code = 500
            post.return_value.text = "boom"
            self.assertFalse(publish([str(self.candidate.id)], {"type": "message.new"}))

    @override_settings(CHAT_ENABLED=False)
    def test_disabled_chat_makes_no_network_calls(self):
        from apps.conversations.realtime import publish

        with patch("apps.conversations.realtime._session.post") as post:
            self.assertFalse(publish([str(self.candidate.id)], {"type": "message.new"}))
        post.assert_not_called()

    def test_disconnect_users_reaches_the_gateway(self):
        from apps.conversations.realtime import disconnect_users

        with patch("apps.conversations.realtime._session.post") as post:
            post.return_value.status_code = 200
            disconnect_users([self.candidate.id], reason="logout")

        url, = post.call_args.args
        self.assertTrue(url.endswith("/internal/disconnect"))
        self.assertEqual(post.call_args.kwargs["json"]["reason"], "logout")

    def test_disconnect_failure_does_not_raise(self):
        """Logout must succeed even when the gateway is unreachable."""
        from apps.conversations.realtime import disconnect_users

        with patch(
            "apps.conversations.realtime._session.post",
            side_effect=requests.Timeout("slow"),
        ):
            self.assertFalse(disconnect_users([self.candidate.id]))

    def test_participants_are_served_in_their_own_language(self):
        from apps.conversations.realtime import broadcast_message

        self.candidate.preferred_language = "ru"
        self.candidate.save(update_fields=["preferred_language"])
        self.recruiter.preferred_language = "en"
        self.recruiter.save(update_fields=["preferred_language"])
        self.conversation.refresh_from_db()

        message = Message.objects.create(
            conversation=self.conversation, sender_type="SYSTEM",
            message_type=MessageType.STATUS_CHANGE, content="",
            metadata={
                "old_status": "APPLIED", "new_status": "INTERVIEW_SCHEDULED",
                "changed_by": "RECRUITER",
            },
            is_read=False,
        )

        with patch("apps.conversations.realtime.serialize_message") as serialize:
            serialize.return_value = {}
            with patch("apps.conversations.realtime._session.post") as post:
                post.return_value.status_code = 202
                with self.captureOnCommitCallbacks(execute=True):
                    broadcast_message(message, conversation=self.conversation)

        languages = {call.kwargs["language"] for call in serialize.call_args_list}
        self.assertEqual(languages, {"ru", "en"})


@override_settings(CHAT_ENABLED=True, CHAT_SERVICE_KEY=SERVICE_KEY)
class UnreadCountTests(ChatTestData):
    """The count behind the badge on the chat icon."""

    def setUp(self):
        super().setUp()
        self.url = reverse("conversation-unread-count")

    def count_for(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get(self.url).json()["data"]["unread_conversations"]

    def test_anonymous_user_is_rejected(self):
        response = self.client.get(self.url)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_read_conversation_counts_as_zero(self):
        self.assertEqual(self.count_for(self.candidate), 0)
        self.assertEqual(self.count_for(self.recruiter), 0)

    def test_unread_is_counted_only_for_the_side_it_belongs_to(self):
        """The flag is per participant, so one unread conversation must not
        light up the badge for both people in it."""
        self.conversation.is_read_by_candidate = False
        self.conversation.save(update_fields=["is_read_by_candidate"])

        self.assertEqual(self.count_for(self.candidate), 1)
        self.assertEqual(self.count_for(self.recruiter), 0)

    def test_recruiter_side_counts_independently(self):
        self.conversation.is_read_by_recruiter = False
        self.conversation.save(update_fields=["is_read_by_recruiter"])

        self.assertEqual(self.count_for(self.recruiter), 1)
        self.assertEqual(self.count_for(self.candidate), 0)

    def test_a_user_never_sees_other_peoples_conversations(self):
        self.conversation.is_read_by_candidate = False
        self.conversation.save(update_fields=["is_read_by_candidate"])

        # The outsider takes part in nothing, so their badge stays empty even
        # though an unread conversation exists in the database.
        self.assertEqual(self.count_for(self.outsider), 0)

    def test_sending_a_message_raises_the_recipients_count(self):
        """End to end through the gateway's own endpoint, so the count and the
        write path cannot drift apart."""
        self.client.force_authenticate(user=None)
        response = self.service_post(
            reverse("chat-internal-message-create"),
            {
                "user_id": str(self.candidate.id),
                "role": ROLE_CANDIDATE,
                "conversation_id": str(self.conversation.id),
                "content": "Hello",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(self.count_for(self.recruiter), 1)
        self.assertEqual(self.count_for(self.candidate), 0)


@override_settings(
    CHAT_ENABLED=True,
    CHAT_SERVICE_KEY=SERVICE_KEY,
    CHAT_CANDIDATE_HOURLY_MESSAGE_LIMIT=5,
    CHAT_CANDIDATE_DAILY_MESSAGE_LIMIT=1000,
)
class CandidateQuotaTests(ChatTestData):
    """The candidate message allowance.

    The rule exists to stop a candidate burying a recruiter, and is shaped so
    that a genuine conversation never notices it. Both halves of that are
    worth testing: that it blocks a flood, and that it gets out of the way the
    moment the recruiter engages.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse("chat-internal-message-create")

    def send_as_candidate(self, content="hello"):
        return self.service_post(self.url, {
            "user_id": str(self.candidate.id),
            "role": ROLE_CANDIDATE,
            "conversation_id": str(self.conversation.id),
            "content": content,
        })

    def send_as_recruiter(self, content="replying"):
        return self.service_post(self.url, {
            "user_id": str(self.recruiter.id),
            "role": ROLE_RECRUITER,
            "conversation_id": str(self.conversation.id),
            "content": content,
        })

    def test_candidate_may_send_up_to_the_hourly_limit(self):
        for i in range(5):
            response = self.send_as_candidate(f"message {i}")
            self.assertEqual(
                response.status_code, status.HTTP_201_CREATED,
                f"message {i} should have been accepted",
            )

    def test_the_sixth_message_is_refused(self):
        for i in range(5):
            self.send_as_candidate(f"message {i}")

        response = self.send_as_candidate("one too many")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.json()["error"]["code"], CODE_HOURLY_LIMIT)
        # Only the five accepted messages exist.
        self.assertEqual(
            Message.objects.filter(sender_type=ROLE_CANDIDATE).count(), 5
        )

    def test_the_refusal_says_when_writing_becomes_possible(self):
        for i in range(5):
            self.send_as_candidate(f"message {i}")

        details = self.send_as_candidate("blocked").json()["error"]["details"]
        self.assertIsNotNone(details["retry_after"])
        self.assertGreater(details["retry_after"], 0)
        # The rolling hour means the next slot is within the hour, not later.
        self.assertLessEqual(details["retry_after"], 3600)

    def test_a_recruiter_reply_clears_the_quota(self):
        """The point of the rule: a reply lets the candidate answer at once."""
        for i in range(5):
            self.send_as_candidate(f"message {i}")
        self.assertEqual(
            self.send_as_candidate("blocked").status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

        self.send_as_recruiter("thanks, tell me more")

        response = self.send_as_candidate("here is more")
        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED,
            "a recruiter reply must restore the candidate's allowance",
        )

    def test_a_long_conversation_is_never_blocked(self):
        """Alternating messages must run indefinitely."""
        for round_number in range(8):
            for i in range(5):
                response = self.send_as_candidate(f"round {round_number} msg {i}")
                self.assertEqual(
                    response.status_code, status.HTTP_201_CREATED,
                    f"blocked during round {round_number}",
                )
            self.send_as_recruiter(f"reply {round_number}")

    def test_recruiters_are_not_limited(self):
        for i in range(20):
            response = self.send_as_recruiter(f"recruiter message {i}")
            self.assertEqual(
                response.status_code, status.HTTP_201_CREATED,
                f"recruiter message {i} should never be refused",
            )

    def test_the_quota_is_per_conversation(self):
        """Exhausting one thread must not silence the candidate everywhere.

        A second recruiter is needed rather than a second thread with the same
        one: the model allows a candidate and recruiter only one headhunting
        conversation between them.
        """
        other_recruiter = Recruiter.objects.create_user(
            email="recruiter2@test.com", password="testpass123",
            is_recruiter=True, company=self.company,
        )
        RecruiterProfile.objects.create(
            recruiter=other_recruiter, full_name="Other Recruiter"
        )
        other = Conversation.objects.create(
            candidate=self.candidate,
            recruiter=other_recruiter,
            application=None,
            vacancy=None,
        )
        for i in range(5):
            self.send_as_candidate(f"message {i}")
        self.assertEqual(
            self.send_as_candidate("blocked").status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

        response = self.service_post(self.url, {
            "user_id": str(self.candidate.id),
            "role": ROLE_CANDIDATE,
            "conversation_id": str(other.id),
            "content": "different conversation",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(CHAT_CANDIDATE_DAILY_MESSAGE_LIMIT=3)
    def test_the_daily_backstop_applies_across_conversations(self):
        # Under the hourly limit, but over the daily one.
        for i in range(3):
            self.send_as_candidate(f"message {i}")

        response = self.send_as_candidate("over the daily cap")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.json()["error"]["code"], CODE_DAILY_LIMIT)

    def test_status_changes_also_clear_the_quota(self):
        """A recruiter changing status with no note is stored as SYSTEM.

        That is still the other side engaging, so it should not leave the
        candidate unable to respond to it.
        """
        for i in range(5):
            self.send_as_candidate(f"message {i}")

        Message.objects.create(
            conversation=self.conversation, sender_type="SYSTEM",
            message_type=MessageType.STATUS_CHANGE, content="", is_read=False,
        )

        self.assertEqual(
            self.send_as_candidate("responding to the status change").status_code,
            status.HTTP_201_CREATED,
        )

    def test_quota_is_reported_on_the_conversation_detail(self):
        """So the composer can warn before the candidate is blocked."""
        self.send_as_candidate("first")
        self.send_as_candidate("second")

        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(
            reverse("candidate-conversation-detail", kwargs={"id": self.conversation.id})
        )
        quota = response.json()["data"]["message_quota"]

        self.assertEqual(quota["limit"], 5)
        self.assertEqual(quota["used"], 2)
        self.assertEqual(quota["remaining"], 3)
        self.assertIsNotNone(quota["resets_at"])

    def test_recruiters_are_not_shown_a_quota(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            reverse("recruiter-conversation-detail", kwargs={"id": self.conversation.id})
        )
        self.assertIsNone(response.json()["data"]["message_quota"])
