import requests
from django.conf import settings
from django.core.cache import cache

from apps.skills.localization import clean_text, clean_market_skill_name, split_requirement_text, unique_items


DEFAULT_HH_API_BASE_URL = "https://api.hh.uz"
DEFAULT_HH_USER_AGENT = "WorkXplorer/1.0 (https://workxplorer.uz)"
DEFAULT_AREA_ID = "97"
DEFAULT_MAX_PAGES = 2
DEFAULT_PER_PAGE = 30
DEFAULT_CANDIDATE_HH_MAX_PAGES = 1
DEFAULT_CANDIDATE_HH_PER_PAGE = 10
MAX_PAGES = 5
MAX_PER_PAGE = 50
DEFAULT_HH_TOKEN_URL = "https://hh.ru/oauth/token"
DEFAULT_HH_TOKEN_CACHE_SECONDS = 60 * 60 * 24

_HH_TOKEN_CACHE_KEY = "hh_application_token"


class HHConfigurationError(requests.RequestException):
    """Raised when HH API integration is not configured for protected methods."""


class HHAPIError(requests.HTTPError):
    """HTTP error with HH's response payload included in the exception text."""


def get_hh_setting(name, default=""):
    return str(getattr(settings, name, default) or "").strip()


def get_hh_api_base_url():
    return get_hh_setting("HH_API_BASE_URL", DEFAULT_HH_API_BASE_URL).rstrip("/")


def get_hh_access_token():
    return get_hh_setting("HH_ACCESS_TOKEN")


def get_hh_client_id():
    return get_hh_setting("HH_CLIENT_ID")


def get_hh_client_secret():
    return get_hh_setting("HH_CLIENT_SECRET")


def get_hh_token_url():
    return get_hh_setting("HH_TOKEN_URL", DEFAULT_HH_TOKEN_URL)


def get_hh_token_cache_seconds():
    value = getattr(settings, "HH_TOKEN_CACHE_SECONDS", DEFAULT_HH_TOKEN_CACHE_SECONDS)
    try:
        return max(int(value), 300)
    except (TypeError, ValueError):
        return DEFAULT_HH_TOKEN_CACHE_SECONDS


def get_hh_user_agent():
    return get_hh_setting("HH_USER_AGENT", DEFAULT_HH_USER_AGENT)


def get_hh_request_timeout():
    value = getattr(settings, "HH_REQUEST_TIMEOUT_SECONDS", 7)
    try:
        return max(float(value), 2.0)
    except (TypeError, ValueError):
        return 7


def hh_method_requires_authorization(path):
    return path == "/vacancies" or path.startswith("/vacancies/")


def hh_authorization_is_configured():
    return bool(
        get_hh_access_token()
        or (get_hh_client_id() and get_hh_client_secret())
    )


def clear_hh_application_token_cache():
    cache.delete(_HH_TOKEN_CACHE_KEY)


def extract_hh_error_payload(response):
    try:
        data = response.json()
    except ValueError:
        return clean_text(getattr(response, "text", ""))[:500]

    errors = data.get("errors") if isinstance(data, dict) else None
    if not isinstance(errors, list):
        return data

    details = []
    for error in errors:
        if not isinstance(error, dict):
            continue

        error_type = error.get("type")
        error_value = error.get("value")
        if error_type and error_value:
            details.append(f"{error_type}: {error_value}")
        elif error_type:
            details.append(str(error_type))

    return "; ".join(details) if details else data


def raise_for_hh_status(response, include_authorization_hint=True):
    if response.status_code < 400:
        return

    reason = getattr(response, "reason", "") or "Error"
    url = getattr(response, "url", "")
    message = f"{response.status_code} {reason}"
    if url:
        message = f"{message} for url: {url}"
    payload = extract_hh_error_payload(response)
    if payload:
        message = f"{message}. HH response: {payload}"

    if (
        include_authorization_hint
        and response.status_code == 403
        and not hh_authorization_is_configured()
    ):
        message = (
            f"{message}. Configure HH_ACCESS_TOKEN, or configure "
            "HH_CLIENT_ID and HH_CLIENT_SECRET so the backend can fetch an "
            "application access token."
        )

    raise HHAPIError(message, response=response)


def fetch_hh_application_token():
    cached_token = cache.get(_HH_TOKEN_CACHE_KEY)
    if cached_token:
        return cached_token

    response = requests.post(
        get_hh_token_url(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "HH-User-Agent": get_hh_user_agent(),
            "User-Agent": get_hh_user_agent(),
        },
        data={
            "grant_type": "client_credentials",
            "client_id": get_hh_client_id(),
            "client_secret": get_hh_client_secret(),
        },
        timeout=15,
    )
    raise_for_hh_status(response)

    token_data = response.json()
    access_token = clean_text(token_data.get("access_token"))
    if not access_token:
        raise HHConfigurationError(
            "HH token endpoint did not return access_token. Set HH_ACCESS_TOKEN "
            "directly or verify HH_CLIENT_ID and HH_CLIENT_SECRET."
        )

    cache_seconds = get_hh_token_cache_seconds()
    cache.set(_HH_TOKEN_CACHE_KEY, access_token, timeout=cache_seconds)
    return access_token


def resolve_hh_access_token():
    access_token = get_hh_access_token()
    if access_token:
        return access_token

    if get_hh_client_id() and get_hh_client_secret():
        return fetch_hh_application_token()

    return ""


def build_hh_headers():
    headers = {
        "Accept": "application/json",
        "HH-User-Agent": get_hh_user_agent(),
        "User-Agent": get_hh_user_agent(),
    }

    access_token = resolve_hh_access_token()
    if access_token:
        if access_token.lower().startswith("bearer "):
            headers["Authorization"] = access_token
        else:
            headers["Authorization"] = f"Bearer {access_token}"

    return headers


def require_hh_authorization(path):
    if not hh_method_requires_authorization(path) or hh_authorization_is_configured():
        return

    raise HHConfigurationError(
        "HH access is not configured. HH vacancy search requires a HeadHunter "
        "application access token. Register an application at "
        "https://dev.hh.uz/admin or https://dev.hh.ru/admin, then set either "
        "HH_ACCESS_TOKEN (or HH_APP_TOKEN) or both HH_CLIENT_ID and "
        "HH_CLIENT_SECRET in the backend environment."
    )


def request_hh_json(path, params=None):
    require_hh_authorization(path)

    response = requests.get(
        f"{get_hh_api_base_url()}{path}",
        headers=build_hh_headers(),
        params=params,
        timeout=get_hh_request_timeout(),
    )
    raise_for_hh_status(response)
    return response.json()


def collect_hh_api_vacancies(
    query,
    area_id=DEFAULT_AREA_ID,
    max_pages=DEFAULT_MAX_PAGES,
    per_page=DEFAULT_PER_PAGE,
    max_details=None,
):
    vacancies = []
    detail_count = 0
    reached_limit = False

    for page in range(max_pages):
        search_data = request_hh_json(
            "/vacancies",
            params={
                "text": query,
                "area": area_id,
                "page": page,
                "per_page": per_page,
            },
        )

        for item in search_data.get("items", []):
            vacancy_id = item.get("id")
            if not vacancy_id:
                continue
            if max_details is not None and detail_count >= max_details:
                reached_limit = True
                break

            detail = request_hh_json(f"/vacancies/{vacancy_id}")
            detail_count += 1
            search_snippet = item.get("snippet") or {}
            detail_snippet = detail.get("snippet") or {}
            requirement = (
                search_snippet.get("requirement")
                or detail_snippet.get("requirement")
                or ""
            )

            salary_data = detail.get("salary") or {}
            vacancies.append(
                {
                    "external_id": detail.get("id"),
                    "title": detail.get("name") or item.get("name") or "",
                    "company": (detail.get("employer") or {}).get("name") or "",
                    "url": (
                        detail.get("alternate_url")
                        or item.get("alternate_url")
                        or ""
                    ),
                    "requirements": split_requirement_text(requirement),
                    "description_requirements": split_requirement_text(
                        detail.get("description")
                    ),
                    "key_skills": unique_items(
                        clean_market_skill_name(skill.get("name"))
                        for skill in detail.get("key_skills", [])
                        if skill.get("name")
                    ),
                    "salary_from": salary_data.get("from"),
                    "salary_to": salary_data.get("to"),
                    "salary_currency": salary_data.get("currency"),
                }
            )

        if reached_limit:
            break
        if page >= search_data.get("pages", 1) - 1:
            break

    return vacancies


def collect_hh_salaries(
    query,
    area_id=DEFAULT_AREA_ID,
    max_pages=DEFAULT_MAX_PAGES,
    per_page=DEFAULT_PER_PAGE,
):
    """Collect salary data from HH API for market median calculation."""
    salaries = []

    for page in range(max_pages):
        search_data = request_hh_json(
            "/vacancies",
            params={
                "text": query,
                "area": area_id,
                "page": page,
                "per_page": per_page,
                "only_with_salary": "true",
            },
        )

        for item in search_data.get("items", []):
            salary = item.get("salary")
            if salary and salary.get("from") is not None and salary.get("currency"):
                salaries.append({
                    "from": salary["from"],
                    "to": salary.get("to"),
                    "currency": salary["currency"],
                })

        if page >= search_data.get("pages", 1) - 1:
            break

    return salaries


def collect_hh_vacancy_by_id(vacancy_id):
    detail = request_hh_json(f"/vacancies/{vacancy_id}")
    snippet = detail.get("snippet") or {}
    salary_data = detail.get("salary") or {}
    return {
        "external_id": detail.get("id"),
        "title": detail.get("name") or "",
        "company": (detail.get("employer") or {}).get("name") or "",
        "url": detail.get("alternate_url") or "",
        "requirements": split_requirement_text(snippet.get("requirement") or ""),
        "description_requirements": split_requirement_text(detail.get("description")),
        "key_skills": unique_items(
            clean_market_skill_name(skill.get("name"))
            for skill in detail.get("key_skills", [])
            if skill.get("name")
        ),
        "salary_from": salary_data.get("from"),
        "salary_to": salary_data.get("to"),
        "salary_currency": salary_data.get("currency"),
    }
