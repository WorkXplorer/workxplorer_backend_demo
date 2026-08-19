from django.conf import settings


def resolve_profile_status(user) -> tuple[str, str]:
    """Returns (profile_status, next_action) for the mobile session response.
    Mirrors the web flow's missing-profile handling (404 -> create-profile)."""
    from apps.profiles.models.candidate_profile import CandidateProfile

    has_profile = CandidateProfile.objects.filter(candidate_id=user.id).exists()
    if has_profile:
        return "complete", "home"
    return "missing", "complete_profile"


def build_session_response_data(user, bundle) -> dict:
    """Shared shape for every mobile endpoint that creates/rotates a session
    (password login, Google, Apple, refresh)."""
    session = bundle.session
    profile_status, next_action = resolve_profile_status(user)

    return {
        "access_token": bundle.access_token,
        "refresh_token": bundle.refresh_token,
        "token_type": "Bearer",
        "expires_in": int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        "refresh_idle_expires_in": settings.MOBILE_SESSION_IDLE_TTL_DAYS * 86400,
        "session_absolute_expires_at": session.absolute_expires_at.isoformat(),
        "session_id": str(session.id),
        "user": {"id": str(user.id), "role": "candidate", "email": user.email},
        "profile_status": profile_status,
        "next_action": next_action,
    }


def build_refresh_response_data(bundle) -> dict:
    """Slimmer shape for /auth/mobile/refresh/ — no user/profile_status,
    matching the TZ's refresh response (client already has that from login)."""
    session = bundle.session
    return {
        "access_token": bundle.access_token,
        "refresh_token": bundle.refresh_token,
        "token_type": "Bearer",
        "expires_in": int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        "refresh_idle_expires_in": settings.MOBILE_SESSION_IDLE_TTL_DAYS * 86400,
        "session_absolute_expires_at": session.absolute_expires_at.isoformat(),
        "session_id": str(session.id),
    }
