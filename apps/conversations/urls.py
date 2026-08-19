from django.urls import path
from apps.conversations.views import (
    recruiter_conversation_list_view,
    recruiter_conversation_detail_view,
    candidate_conversation_list_view,
    candidate_conversation_detail_view,
    conversation_unread_count_view,
    headhunting_candidate_list_view,
    headhunting_invitation_view,
    chat_ticket_view,
    internal_message_create_view,
    internal_mark_read_view,
    internal_membership_view,
    internal_peers_view,
)
from apps.conversations.views.discussions import (
    discussion_list_create_view,
    discussion_detail_view,
)

urlpatterns = [
    # Recruiter endpoints
    path(
        "recruiter/",
        recruiter_conversation_list_view,
        name="recruiter-conversation-list",
    ),
    path(
        "recruiter/<uuid:id>/",
        recruiter_conversation_detail_view,
        name="recruiter-conversation-detail",
    ),
    # Candidate endpoints
    path(
        "candidate/",
        candidate_conversation_list_view,
        name="candidate-conversation-list",
    ),
    path(
        "candidate/<uuid:id>/",
        candidate_conversation_detail_view,
        name="candidate-conversation-detail",
    ),
    # Headhunting endpoints (for recruiters)
    path(
        "headhunting/candidates/",
        headhunting_candidate_list_view,
        name="headhunting-candidate-list",
    ),
    path(
        "headhunting/invite/",
        headhunting_invitation_view,
        name="headhunting-invitation",
    ),
    # Unread badge on the chat icon. Shared by candidates and recruiters —
    # the unread flag is per side, so each user sees only their own count.
    path(
        "unread-count/",
        conversation_unread_count_view,
        name="conversation-unread-count",
    ),
    # Realtime chat — clients exchange their API session for a short-lived,
    # single-use WebSocket ticket here.
    path(
        "ws-ticket/",
        chat_ticket_view,
        name="chat-ws-ticket",
    ),
    # Endpoints the Go chat gateway calls on behalf of a connected user.
    # Authenticated by the shared CHAT_SERVICE_KEY, not by a user session —
    # keep them off the public internet at the reverse proxy.
    path(
        "internal/messages/",
        internal_message_create_view,
        name="chat-internal-message-create",
    ),
    path(
        "internal/read/",
        internal_mark_read_view,
        name="chat-internal-mark-read",
    ),
    path(
        "internal/membership/",
        internal_membership_view,
        name="chat-internal-membership",
    ),
    path(
        "internal/peers/",
        internal_peers_view,
        name="chat-internal-peers",
    ),
    # Internal recruiter discussions
    path(
        "applications/<uuid:application_id>/discussions/",
        discussion_list_create_view,
        name="discussion-list-create",
    ),
    path(
        "applications/<uuid:application_id>/discussions/<uuid:id>/",
        discussion_detail_view,
        name="discussion-detail",
    ),
]
