from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now


REGISTRATION = "registration"
CREATE_PROFILE = "create_profile"
CREATE_RESUME = "create_resume"
VACANCY_APPLY = "vacancy_apply"
VERIFY_VAULT = "verify_vault"

STATUS_LABELS = {
    REGISTRATION: _("Email registration"),
    CREATE_PROFILE: _("Create profile"),
    CREATE_RESUME: _("Create resume"),
    VACANCY_APPLY: _("Apply for vacancy"),
    VERIFY_VAULT: _("Connect LMS"),
}

PROGRESS_STEPS = [
    (CREATE_PROFILE, STATUS_LABELS[CREATE_PROFILE]),
    (CREATE_RESUME, STATUS_LABELS[CREATE_RESUME]),
    (VACANCY_APPLY, STATUS_LABELS[VACANCY_APPLY]),
    (VERIFY_VAULT, STATUS_LABELS[VERIFY_VAULT]),
]

# Step ordering for status resolution (index defines priority)
_STEP_ORDER = [code for code, _ in PROGRESS_STEPS]

# Navigation paths for each onboarding step (language placeholder filled at runtime)
ONBOARDING_STEP_PATHS = {
    CREATE_PROFILE: "/{lang}/dashboard/profile",
    CREATE_RESUME: "/{lang}/dashboard/resume/create",
    VACANCY_APPLY: "/{lang}/dashboard/vacancies/list",
    VERIFY_VAULT: "/{lang}/dashboard/analytics",
}


def get_safe_progress(candidate):
    progress = candidate.onboarding_progress

    if not isinstance(progress, dict):
        return {}

    return progress


def resolve_candidate_status(candidate) -> str:
    """Return the highest completed step in the defined flow order."""
    progress = get_safe_progress(candidate)

    if not progress:
        return REGISTRATION

    # Walk steps in reverse order and return the first (highest) completed one
    for step_code in reversed(_STEP_ORDER):
        if step_code in progress:
            return step_code

    return REGISTRATION


def get_status_label(status_code: str) -> str:
    return str(STATUS_LABELS.get(status_code, status_code))


def update_candidate_step(candidate, step: str) -> None:
    progress = get_safe_progress(candidate)

    if step in progress:
        return

    progress[step] = now().isoformat()
    candidate.onboarding_progress = progress
    candidate.save(update_fields=["onboarding_progress"])


def sync_candidate_resume_step(candidate) -> None:
    """Backfill the resume onboarding step when a resume already exists."""
    progress = get_safe_progress(candidate)

    if CREATE_RESUME in progress:
        return

    if not hasattr(candidate, "resumes") or not candidate.resumes.exists():
        return

    progress[CREATE_RESUME] = now().isoformat()
    candidate.onboarding_progress = progress
    candidate.save(update_fields=["onboarding_progress"])


def get_step_url(step_code: str, language: str = "en") -> str:
    """Build a full frontend URL for the given onboarding step."""
    path_template = ONBOARDING_STEP_PATHS.get(step_code)
    if not path_template:
        return ""

    base_url = getattr(settings, "FRONTEND_URL", "")
    if not base_url:
        return ""

    path = path_template.replace("{lang}", language)
    return f"{base_url.rstrip('/')}{path}"


def get_candidate_progress(candidate, language: str = "en"):
    """Return structured onboarding progress with navigation URLs."""
    progress_data = get_safe_progress(candidate)

    result = []
    completed_count = 0
    current_step = None

    for code, label in PROGRESS_STEPS:
        is_done = code in progress_data

        if is_done:
            completed_count += 1
        elif current_step is None:
            current_step = code

        result.append({
            "code": code,
            "label": label,
            "completed": is_done,
            "completed_at": progress_data.get(code),
            "url": get_step_url(code, language),
        })

    progress_percent = int((completed_count / len(PROGRESS_STEPS)) * 100)

    status = resolve_candidate_status(candidate)

    return {
        "progress": progress_percent,
        "current_step": current_step,
        "status": status,
        "status_label": get_status_label(status),
        "steps": result,
    }
