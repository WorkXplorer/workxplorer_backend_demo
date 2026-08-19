import logging
from typing import Any
from collections import defaultdict

from django.conf import settings
from django.db.models import Q
from django.utils import translation
from django.utils.translation import gettext as _

from apps.domain.models import Domain
from apps.resumes.models import Resume
from apps.quiz.models import QuizResult
from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate, Recruiter
from apps.profiles.models import CandidateProfile, RecruiterProfile
from apps.general.services.email_service import send_email_from_template_type
from apps.matching.services.matching import VacancyMatcher

logger = logging.getLogger(__name__)


class ManualEmailCampaignService:
    """
    Sends vacancy recommendation emails.

    Request contract:
      - template_type: EmailTemplate.template_type to render
      - emails: active candidate or recruiter emails
      - edupartner_ids: (candidates only) send to all active candidates
        belonging to these educational partners, instead of/in addition to
        an explicit emails list
      - no_university_only: (candidates only) send to all active candidates
        with no educational partner assigned at all, instead of/in addition
        to emails/edupartner_ids
      - audience: candidates by default, recruiters when explicitly requested
      - vacancy_limit: optional, 1..7, defaults to 5
      - recipient_limit: optional cap on how many resolved recipients actually
        get emailed (e.g. only the first 100 candidates at a university)
      - cooldown_seconds: optional delay between each successive email send,
        so a batch is paced out instead of firing all at once
      - language: optional language override for every recipient. Combine with
        edupartner_ids to send one language per university (e.g.
        Russian-speaking universities) in separate calls.

    If neither emails nor edupartner_ids is provided, the full active base
    for the chosen audience is targeted — always pair that with
    recipient_limit and/or cooldown_seconds.

    Candidate vacancies are selected by resume embedding similarity
    (pgvector cosine distance via apps.matching.VacancyMatcher) when the
    candidate has an embedded resume, falling back to resume/quiz domain
    category matching, then to the most recently created active vacancies.
    Recruiter vacancies are selected from the recruiter's company domain.
    """

    DEFAULT_VACANCY_LIMIT = 5

    def __init__(self, request=None):
        self.request = request

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        audience = payload.get("audience") or "candidates"
        vacancy_limit = payload.get("vacancy_limit") or self.DEFAULT_VACANCY_LIMIT
        recipient_limit = payload.get("recipient_limit")
        cooldown_seconds = payload.get("cooldown_seconds") or 0
        language_override = payload.get("language")
        recipients, skipped = self._get_recipients(
            audience,
            payload.get("emails") or [],
            edupartner_ids=payload.get("edupartner_ids") or [],
            no_university_only=payload.get("no_university_only") or False,
            recipient_limit=recipient_limit,
        )
        all_domain_ids = {
            domain_id
            for recipient in recipients
            for domain_id in recipient["domain_ids"]
        }
        domain_names_by_id = self._get_domain_names(all_domain_ids)

        sent = []
        failed = []
        vacancy_payloads_by_id = {}

        for recipient in recipients:
            effective_language = (
                language_override or recipient.get("preferred_language") or "uz"
            )
            self._language = effective_language

            vacancies = self._recommended_vacancies(recipient, limit=vacancy_limit)
            if not vacancies:
                skipped.append(
                    {
                        "email": recipient["email"],
                        "reason": self._no_vacancies_reason(recipient),
                    }
                )
                continue

            for vacancy in vacancies:
                vacancy_payloads_by_id[vacancy.id] = self._serialize_vacancy(vacancy)

            context = self._build_context(
                payload=payload,
                recipient=recipient,
                vacancies=vacancies,
                domain_names_by_id=domain_names_by_id,
                language=effective_language,
                vacancy_limit=vacancy_limit,
            )

            try:
                # Pace by position among successful sends only — skipped/failed
                # recipients don't consume a slot in the cooldown schedule.
                delay_seconds = len(sent) * cooldown_seconds
                send_email_from_template_type(
                    to_email=recipient["email"],
                    template_type=payload["template_type"],
                    context=context,
                    language=effective_language,
                    delay_seconds=delay_seconds,
                )
                sent.append(
                    {
                        "email": recipient["email"],
                        "delay_seconds": delay_seconds,
                    }
                )
            except Exception as exc:
                logger.exception(
                    "Failed to enqueue vacancy recommendation email to %s",
                    recipient["email"],
                )
                failed.append(
                    {
                        "email": recipient["email"],
                        "error": str(exc),
                    }
                )

        return {
            "audience": audience,
            "template_type": payload["template_type"],
            "vacancy_limit": vacancy_limit,
            "recipient_limit": recipient_limit,
            "cooldown_seconds": cooldown_seconds,
            "recipient_count": len(recipients),
            "sent_count": len(sent),
            "failed_count": len(failed),
            "skipped_count": len(skipped),
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "vacancies": list(vacancy_payloads_by_id.values()),
            "domain_ids": sorted(all_domain_ids),
            "domains": [
                {"id": domain_id, "name": name}
                for domain_id, name in sorted(domain_names_by_id.items())
            ],
        }

    def _get_recipients(
        self,
        audience: str,
        emails: list[str],
        edupartner_ids: list[str] | None = None,
        no_university_only: bool = False,
        recipient_limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        if audience == "recruiters":
            return self._get_recruiter_recipients(emails, recipient_limit=recipient_limit)
        return self._get_candidate_recipients(
            emails,
            edupartner_ids=edupartner_ids or [],
            no_university_only=no_university_only,
            recipient_limit=recipient_limit,
        )

    def _get_candidate_recipients(
        self,
        emails: list[str],
        edupartner_ids: list[str] | None = None,
        no_university_only: bool = False,
        recipient_limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        edupartner_ids = edupartner_ids or []

        filters = Q()
        if emails:
            filters |= Q(email__in=emails)
        if edupartner_ids:
            filters |= Q(edupartner_id__in=edupartner_ids)
        if no_university_only:
            filters |= Q(edupartner_id__isnull=True)

        queryset = (
            Candidate.objects.filter(is_active=True)
            .filter(filters)
            .select_related("edupartner")
            .order_by("email")
            .distinct()
        )
        # Only slice at the DB level when there's no explicit emails list to
        # reconcile against — otherwise candidates trimmed by the limit would
        # be misreported as "not found" instead of "limited out".
        if recipient_limit and not emails:
            queryset = queryset[:recipient_limit]
        candidates = list(queryset)
        found_emails = {candidate.email.lower() for candidate in candidates}
        skipped = self._missing_email_skips(emails, found_emails, "candidate")
        if recipient_limit and emails:
            candidates = candidates[:recipient_limit]
        candidate_ids = [candidate.id for candidate in candidates]

        resume_domains = self._candidate_resume_domains(candidate_ids)
        quiz_domains = self._candidate_quiz_domains(candidate_ids)
        embedded_resumes = self._candidate_embedded_resumes(candidate_ids)
        names = dict(
            CandidateProfile.objects.filter(candidate_id__in=candidate_ids).values_list(
                "candidate_id",
                "full_name",
            )
        )

        recipients = []
        for candidate in candidates:
            candidate_domain_ids = set(resume_domains.get(candidate.id, set()))
            candidate_domain_ids.update(quiz_domains.get(candidate.id, set()))
            recipients.append(
                {
                    "id": candidate.id,
                    "email": candidate.email,
                    "full_name": names.get(candidate.id, ""),
                    "type": "candidate",
                    "preferred_language": candidate.preferred_language or "uz",
                    "university": candidate.edupartner.name if candidate.edupartner_id else "",
                    "domain_ids": candidate_domain_ids,
                    "resume_domain_ids": set(resume_domains.get(candidate.id, set())),
                    "quiz_domain_ids": set(quiz_domains.get(candidate.id, set())),
                    "embedded_resume": embedded_resumes.get(candidate.id),
                }
            )

        return recipients, skipped

    def _get_recruiter_recipients(
        self, emails: list[str], recipient_limit: int | None = None
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        queryset = Recruiter.objects.filter(is_active=True)
        queryset = queryset.filter(email__in=emails) if emails else queryset
        queryset = (
            queryset.select_related("company", "company__domain")
            .order_by("email")
            .distinct()
        )
        # See _get_candidate_recipients for why DB-level slicing is skipped
        # when there's an explicit emails list to reconcile against.
        if recipient_limit and not emails:
            queryset = queryset[:recipient_limit]
        recruiters = list(queryset)
        found_emails = {recruiter.email.lower() for recruiter in recruiters}
        skipped = self._missing_email_skips(emails, found_emails, "recruiter")
        if recipient_limit and emails:
            recruiters = recruiters[:recipient_limit]
        recruiter_ids = [recruiter.id for recruiter in recruiters]

        names = {}
        for profile in RecruiterProfile.objects.filter(
            recruiter_id__in=recruiter_ids
        ).order_by("full_name"):
            names.setdefault(profile.recruiter_id, profile.full_name or "")

        recipients = []
        for recruiter in recruiters:
            domain_id = recruiter.company.domain_id if recruiter.company_id else None
            recipients.append(
                {
                    "id": recruiter.id,
                    "email": recruiter.email,
                    "full_name": names.get(recruiter.id, ""),
                    "type": "recruiter",
                    "preferred_language": recruiter.preferred_language or "uz",
                    "company": recruiter.company.name if recruiter.company_id else "",
                    "domain_ids": {domain_id} if domain_id else set(),
                    "resume_domain_ids": set(),
                    "quiz_domain_ids": set(),
                }
            )

        return recipients, skipped

    def _candidate_resume_domains(
        self, candidate_ids: list[Any]
    ) -> dict[Any, set[int]]:
        if not candidate_ids:
            return {}

        domains = defaultdict(set)
        queryset = Resume.objects.filter(
            candidate_id__in=candidate_ids,
            domain_id__isnull=False,
        )
        for candidate_id, domain_id in queryset.values_list("candidate_id", "domain_id"):
            domains[candidate_id].add(domain_id)
        return domains

    def _candidate_quiz_domains(
        self, candidate_ids: list[Any]
    ) -> dict[Any, set[int]]:
        if not candidate_ids:
            return {}

        domains = defaultdict(set)
        queryset = QuizResult.objects.filter(
            candidate_id__in=candidate_ids,
            domain_id__isnull=False,
        )
        for candidate_id, domain_id in queryset.values_list("candidate_id", "domain_id"):
            domains[candidate_id].add(domain_id)
        return domains

    def _candidate_embedded_resumes(
        self, candidate_ids: list[Any]
    ) -> dict[Any, Resume]:
        """One embedded resume per candidate — the most recently created."""
        if not candidate_ids:
            return {}

        resumes = {}
        queryset = Resume.objects.filter(
            candidate_id__in=candidate_ids,
            is_embedded=True,
            embedding__isnull=False,
        ).order_by("candidate_id", "-created_at")
        for resume in queryset:
            resumes.setdefault(resume.candidate_id, resume)
        return resumes

    def _recommended_vacancies(
        self, recipient: dict[str, Any], limit: int
    ) -> list[Vacancy]:
        resume = recipient.get("embedded_resume")
        if resume is not None:
            vacancies = self._embedding_matched_vacancies(resume, limit=limit)
            if vacancies:
                return vacancies

        if recipient["domain_ids"]:
            vacancies = self._matching_vacancies(recipient["domain_ids"], limit=limit)
            if vacancies:
                return vacancies

        return self._default_vacancies(limit=limit)

    def _embedding_matched_vacancies(self, resume: Resume, limit: int) -> list[Vacancy]:
        # Widen the similarity search so recency can act as a tiebreaker
        # among comparably-relevant vacancies instead of just taking the
        # single closest match regardless of how stale it is.
        candidates = VacancyMatcher.find_matching_vacancies(
            resume, top_k=max(limit * 3, limit), min_similarity=0.3
        )
        candidates.sort(key=lambda v: (-round(v.similarity_score, 2), -v.created_at.timestamp()))
        return candidates[:limit]

    def _matching_vacancies(
        self,
        domain_ids: set[int],
        limit: int,
    ) -> list[Vacancy]:
        if not domain_ids:
            return []

        return list(
            Vacancy.objects.filter(
                is_active=True,
                domain_id__in=domain_ids,
            )
            .select_related("company", "domain")
            .order_by("-created_at")[:limit]
        )

    def _default_vacancies(self, limit: int) -> list[Vacancy]:
        return list(
            Vacancy.objects.filter(is_active=True)
            .select_related("company", "domain")
            .order_by("-created_at")[:limit]
        )

    def _missing_email_skips(
        self,
        requested_emails: list[str],
        found_emails: set[str],
        audience_label: str,
    ) -> list[dict[str, str]]:
        return [
            {
                "email": email,
                "reason": _("No active %(audience_label)s found for this email.")
                % {"audience_label": audience_label},
            }
            for email in requested_emails
            if email.lower() not in found_emails
        ]

    def _no_vacancies_reason(self, recipient: dict[str, Any]) -> str:
        if recipient["type"] == "recruiter":
            return _("No active vacancies found for this recruiter's company domain.")
        return _("No active vacancies found for this candidate's domains.")

    def _get_domain_names(self, domain_ids: set[int]) -> dict[int, str]:
        if not domain_ids:
            return {}

        return dict(
            Domain.objects.filter(id__in=domain_ids).values_list("id", "name")
        )

    def _build_context(
        self,
        payload: dict[str, Any],
        recipient: dict[str, Any],
        vacancies: list[Vacancy],
        domain_names_by_id: dict[int, str],
        language: str,
        vacancy_limit: int,
    ) -> dict[str, Any]:
        self._language = language
        serialized_vacancies = [
            self._serialize_vacancy(vacancy) for vacancy in vacancies
        ]
        first_vacancy = serialized_vacancies[0] if serialized_vacancies else {}
        domain_names = [
            domain_names_by_id[domain_id]
            for domain_id in sorted(recipient["domain_ids"])
            if domain_id in domain_names_by_id
        ]

        return {
            "site_name": getattr(settings, "SITE_NAME", "WorkXplorer"),
            "frontend_url": self._frontend_url(),
            "language": language,
            "audience": payload.get("audience") or "candidates",
            "recipient_type": recipient["type"],
            "recipient_email": recipient["email"],
            "user_email": recipient["email"],
            "recipient_name": recipient.get("full_name") or "",
            "user_full_name": recipient.get("full_name") or "",
            "company": recipient.get("company") or "",
            "university": recipient.get("university") or "",
            "domain": domain_names[0] if domain_names else "",
            "domains": domain_names,
            "domain_ids": sorted(recipient["domain_ids"]),
            "resume_domain_ids": sorted(recipient.get("resume_domain_ids", set())),
            "quiz_domain_ids": sorted(recipient.get("quiz_domain_ids", set())),
            "vacancy_limit": vacancy_limit,
            "total_count": len(serialized_vacancies),
            "has_vacancies": bool(serialized_vacancies),
            "vacancies": serialized_vacancies,
            "vacancy": first_vacancy,
            "vacancy_title": first_vacancy.get("title", ""),
            "vacancy_url": first_vacancy.get("url", ""),
            "vacancy_link": first_vacancy.get("url", ""),
            "all_vacancies_url": self._all_vacancies_url(),
        }

    def _serialize_vacancy(self, vacancy: Vacancy) -> dict[str, Any]:
        url = self._vacancy_url(vacancy)
        return {
            "id": str(vacancy.id),
            "title": vacancy.title,
            "url": url,
            "link": url,
            "vacancy_url": url,
            "domain": vacancy.domain.name if vacancy.domain_id else "",
            "domain_id": vacancy.domain_id,
            "company": vacancy.company.name if vacancy.company_id else "",
            "location": vacancy.location or "",
            "employment_type": vacancy.employment_type,
            "employment_format": vacancy.employment_format,
            "salary": self._format_salary(vacancy, language=self._current_language()),
            "description": vacancy.additional_info or vacancy.requirements or "",
            "requirements": vacancy.requirements,
            "responsibilities": vacancy.responsibilities,
        }

    def _current_language(self) -> str:
        return getattr(self, "_language", "uz")

    def _format_salary(self, vacancy: Vacancy, language: str = "uz") -> str:
        if vacancy.salary_min and vacancy.salary_max:
            return (
                f"{vacancy.salary_min:g} - {vacancy.salary_max:g} "
                f"{vacancy.salary_currency}"
            )
        if vacancy.salary_min:
            return f"{vacancy.salary_min:g}+ {vacancy.salary_currency}"
        if vacancy.salary_max:
            with translation.override(language):
                return _("up to %(amount)s %(currency)s") % {
                    "amount": f"{vacancy.salary_max:g}",
                    "currency": vacancy.salary_currency,
                }
        return ""

    def _vacancy_url(self, vacancy: Vacancy) -> str:
        frontend_url = self._frontend_url()
        if frontend_url:
            language = self._current_language()
            return f"{frontend_url}/{language}/dashboard/vacancies/{vacancy.id}"

        if self.request:
            return self.request.build_absolute_uri(
                f"/api/v1/vacancies/{vacancy.id}/"
            )

        return f"/vacancies/{vacancy.id}/"

    def _all_vacancies_url(self) -> str:
        frontend_url = self._frontend_url()
        if frontend_url:
            language = self._current_language()
            return f"{frontend_url}/{language}/dashboard/vacancies"

        if self.request:
            return self.request.build_absolute_uri("/api/v1/vacancies/")

        return "/vacancies/"

    def _frontend_url(self) -> str:
        url = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
        if not url:
            logger.warning(
                "FRONTEND_URL is not configured in settings. "
                "Vacancy links in campaign emails will be broken."
            )
        return url
