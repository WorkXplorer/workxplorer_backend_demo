import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)


def notify_partner_registration(company_id: str) -> None:
    """
    Send a partner notification to Telegram when a company registers.

    Called as an RQ background task so the registration request is not
    blocked by the Telegram bot API call.
    """
    try:
        from apps.authentication.models import Company, Recruiter
        from apps.profiles.models import CompanyProfile, RecruiterProfile

        company = Company.objects.get(id=company_id)

        profile = CompanyProfile.objects.filter(company=company).first()
        recruiter_profiles = {
            rp.recruiter_id: rp
            for rp in RecruiterProfile.objects.filter(
                recruiter__company=company
            ).only("recruiter_id", "full_name")
        }

        recruiters_data = []
        for recruiter in Recruiter.objects.filter(company=company).only(
            "email", "id"
        ):
            rec_profile = recruiter_profiles.get(recruiter.id)
            full_name = rec_profile.full_name if rec_profile else ""
            recruiters_data.append({
                "email": recruiter.email,
                "full_name": full_name,
            })

        payload = {
            "company_name": company.name,
            "company_inn": company.tin or "",
            "website": profile.website if profile and profile.website else "",
            "phone_number": profile.phone_number if profile and profile.phone_number else "",
            "recruiters": recruiters_data,
        }

        bot_api_url = settings.TELEGRAM_BOT_API_URL.rstrip("/")
        api_secret = settings.TELEGRAM_BOT_API_SECRET

        if not api_secret:
            logger.warning(
                "TELEGRAM_BOT_API_SECRET not configured — skipping partner notification for company %s",
                company_id,
            )
            return

        import requests

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{bot_api_url}/api/partner/notify",
                    json=payload,
                    headers={"X-API-Secret": api_secret},
                    timeout=10,
                )
                if response.status_code == 200:
                    logger.info(
                        "Partner notification sent successfully for company %s (%s)",
                        company.name, company_id,
                    )
                    break
                else:
                    logger.warning(
                        "Partner notification attempt %d/%d failed for company %s: HTTP %s — %s",
                        attempt + 1, max_retries, company_id,
                        response.status_code, response.text[:200],
                    )
            except requests.Timeout:
                logger.warning(
                    "Partner notification attempt %d/%d timed out for company %s",
                    attempt + 1, max_retries, company_id,
                )
            except requests.ConnectionError as e:
                logger.warning(
                    "Partner notification attempt %d/%d connection error for company %s: %s",
                    attempt + 1, max_retries, company_id, e,
                )

            if attempt < max_retries - 1:
                time.sleep(2)
        else:
            logger.error(
                "Partner notification failed for company %s after %d attempts",
                company_id, max_retries,
            )

    except Exception:
        logger.exception(
            "Failed to send partner notification for company %s", company_id,
        )
