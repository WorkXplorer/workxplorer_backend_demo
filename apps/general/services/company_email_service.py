import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Prefetch
from utils import encode_uid
from utils.language import get_request_language
from apps.general.services.email_service import send_email_from_template_type

logger = logging.getLogger(__name__)


def send_company_confirmation_emails(company_ids, is_active, request=None):
    """
    Send confirmation/rejection emails to company admins and recruiters.

    Extracted from CompanyConfirmAPIView so both the view and background
    tasks can call it directly without an HTTP self-call.

    Args:
        company_ids: list of company UUID strings (normalized & deduplicated).
        is_active: bool — True sends confirm-company, False sends rejected-company.
        request: optional HttpRequest — used only as fallback for URL building
                 when ``settings.FRONTEND_URL`` is not configured.

    Returns:
        dict with keys:
        - sent_emails: list[str]
        - failed_emails: list[str]
        - not_found_company_ids: list[str]
        - recruiters_missing_email: list[dict]
    """
    from apps.authentication.models import Company, Recruiter
    from apps.profiles.models import RecruiterProfile

    normalized_ids = list({str(i) for i in company_ids})

    if not normalized_ids:
        return {
            "sent_emails": [],
            "failed_emails": [],
            "not_found_company_ids": [],
            "recruiters_missing_email": [],
        }

    template_type_admin = "confirm-company" if is_active else "rejected-company"
    template_type_recruiter = "confirm-recruiter"
    language = get_request_language()

    companies = Company.objects.filter(id__in=normalized_ids).prefetch_related(
        Prefetch(
            "recruiters",
            queryset=Recruiter.objects.prefetch_related(
                Prefetch(
                    "recruiterprofile_set",
                    queryset=RecruiterProfile.objects.all(),
                    to_attr="profile_list",
                )
            ),
        )
    )
    found_ids = {str(c.id) for c in companies}
    not_found = [cid for cid in normalized_ids if cid not in found_ids]

    admin_emails_contexts: dict[str, dict] = {}
    recruiter_emails_contexts: dict[str, dict] = {}
    recruiters_missing_email = []

    all_emails = set()

    for comp in companies:
        recruiters_qs = comp.recruiters.all()
        for r in recruiters_qs:
            email = getattr(r, "email", None)
            if not email:
                recruiters_missing_email.append({
                    "company_id": str(comp.id),
                    "company_name": comp.name,
                    "recruiter_id": getattr(r, "id", None),
                })
                continue

            all_emails.add(email)

            profile = (
                r.profile_list[0]
                if hasattr(r, "profile_list") and r.profile_list
                else None
            )
            level = getattr(profile, "level", None) if profile else None
            is_admin = str(level).lower() == "admin" if level else False

            if email in admin_emails_contexts:
                if is_admin:
                    admin_emails_contexts[email]["companies"].append(comp.name)
                continue

            full_name = getattr(profile, "full_name", None) if profile else None

            if is_admin:
                admin_emails_contexts[email] = {
                    "user_email": email,
                    "user_full_name": full_name,
                    "reset_url": None,
                    "site_name": getattr(settings, "SITE_NAME", "WorkXplorer"),
                    "companies": [comp.name],
                }
                recruiter_emails_contexts.pop(email, None)
            else:
                if email in recruiter_emails_contexts:
                    recruiter_emails_contexts[email]["companies"].append(comp.name)
                    continue
                recruiter_emails_contexts[email] = {
                    "user_email": email,
                    "user_full_name": full_name,
                    "reset_url": None,
                    "site_name": getattr(settings, "SITE_NAME", "WorkXplorer"),
                    "companies": [comp.name],
                }

    url_map = _build_set_password_url_batch(list(all_emails), request)

    for email, ctx in admin_emails_contexts.items():
        ctx["reset_url"] = url_map.get(email, "")
    for email, ctx in recruiter_emails_contexts.items():
        ctx["reset_url"] = url_map.get(email, "")

    sent = []
    failed = []

    for email, ctx in admin_emails_contexts.items():
        try:
            send_email_from_template_type(
                to_email=email,
                template_type=template_type_admin,
                context=ctx,
                language=language,
            )
            sent.append(email)
        except Exception:
            logger.exception("Failed sending admin email to %s", email)
            failed.append(email)

    for email, ctx in recruiter_emails_contexts.items():
        if email in admin_emails_contexts:
            continue
        try:
            send_email_from_template_type(
                to_email=email,
                template_type=template_type_recruiter,
                context=ctx,
                language=language,
            )
            sent.append(email)
        except Exception:
            logger.exception("Failed sending recruiter email to %s", email)
            failed.append(email)

    return {
        "sent_emails": sent,
        "failed_emails": failed,
        "not_found_company_ids": not_found,
        "recruiters_missing_email": recruiters_missing_email,
    }


def _build_set_password_url_batch(emails, request=None):
    """
    Build set-password URLs for multiple emails at once to avoid N+1 queries.
    Returns a dict mapping email -> URL.
    """
    User = get_user_model()
    url_map = {}

    try:
        users = User.objects.filter(email__in=emails)
        user_by_email = {user.email: user for user in users}
        frontend = getattr(settings, "FRONTEND_URL", None)

        for email in emails:
            user = user_by_email.get(email)
            if user:
                try:
                    token = default_token_generator.make_token(user)
                    uid = encode_uid(user.pk)
                    if frontend:
                        url_map[email] = (
                            f"{frontend.rstrip('/')}/set-password/recruiter/{uid}/{token}/"
                        )
                    elif request:
                        url_map[email] = request.build_absolute_uri(
                            f"/auth/set-password/{uid}/{token}/"
                        )
                    else:
                        url_map[email] = ""
                except Exception:
                    url_map[email] = _fallback_url(email, request)
            else:
                url_map[email] = _fallback_url(email, request)
    except Exception:
        for email in emails:
            url_map[email] = _fallback_url(email, request)

    return url_map


def _fallback_url(email, request=None):
    """Build a fallback set-password URL when token generation fails."""
    frontend = getattr(settings, "FRONTEND_URL", None)
    if frontend:
        return f"{frontend.rstrip('/')}/auth/set-new-password/?email={email}"
    if request:
        return request.build_absolute_uri(f"/auth/set-new-password/?email={email}")
    return ""
