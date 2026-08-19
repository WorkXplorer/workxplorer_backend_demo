"""
Main EduPartner analytics service.
Orchestrates all analytics components and provides the main entry points.
"""

import logging
from django.utils import timezone

from apps.edupartners.models import EduPartner, Faculty
from apps.authentication.models import Candidate

from .cards import get_statistics_cards
from .employed_graduates import get_employed_graduates
from .hiring_funnel import get_hiring_funnel
from .popular_industries import get_popular_industries
from .top_companies import get_top_companies_by_placements

logger = logging.getLogger(__name__)


class EduPartnerAnalyticsService:
    """
    Service to collect analytics data for educational partners.
    Provides university-specific analytics that are isolated per edu-partner.
    """

    PERIOD_7_DAYS = "7_days"
    PERIOD_30_DAYS = "30_days"
    PERIOD_12_MONTHS = "12_months"

    @staticmethod
    def get_edupartner_analytics(edupartner_id):
        try:
            edupartner = (
                EduPartner.objects.select_related("edupartner_type")
                .prefetch_related("faculties__domain")
                .get(id=edupartner_id, is_active=True)
            )
        except EduPartner.DoesNotExist:
            logger.warning(f"EduPartner with id {edupartner_id} not found or inactive")
            return None

        candidates = Candidate.objects.filter(edupartner=edupartner).values_list(
            "id", flat=True
        )

        candidates_list = list(candidates)
        total_candidates = len(candidates_list)

        faculty_domains = (
            edupartner.faculties.filter(is_active=True, domain__isnull=False)
            .values_list("domain_id", flat=True)
            .distinct()
        )
        faculty_domains_list = list(faculty_domains)

        edupartner_info = {
            "id": str(edupartner.id),
            "name": edupartner.name,
            "type": (
                edupartner.edupartner_type.name
                if edupartner.edupartner_type
                else None
            ),
            "country": edupartner.country,
            "city": edupartner.city,
            "website": edupartner.website,
        }

        empty_stats = {
            "edupartner": edupartner_info,
            "statistics": {
                "source_students": 0,
                "registered": 0,
                "active_30_days": 0,
                "resume_uploaded": 0,
                "profile_filled": 0,
                "assessment_passed": 0,
                "average_graduate_salary": 0,
                "students_on_internships": 0,
                "total_vacancies": 0,
            },
            "employed_graduates": {
                "total_graduates": 0,
                "employed_count": 0,
                "employment_rate_percentage": 0,
            },
            "popular_industries": {
                "7_days": [],
                "30_days": [],
                "12_months": [],
            },
            "timestamp": timezone.now().isoformat(),
        }

        if not candidates_list:
            logger.info(f"No active candidates found for {edupartner.name}")
            if faculty_domains_list:
                empty_stats["popular_industries"] = get_popular_industries(
                    faculty_domains_list
                )
            return empty_stats

        statistics = get_statistics_cards(
            candidates_list,
            faculty_domains_list,
            edupartner_id=str(edupartner.id),
        )
        employed_graduates_data = get_employed_graduates(candidates_list, total_candidates)
        hiring_funnel = get_hiring_funnel(candidates_list)
        top_companies = get_top_companies_by_placements(candidates_list, limit=10)

        if faculty_domains_list:
            popular_industries = get_popular_industries(faculty_domains_list)
        else:
            popular_industries = {
                "7_days": [],
                "30_days": [],
                "12_months": [],
            }

        logger.info(
            f"Analytics for {edupartner.name}: "
            f"source={statistics['source_students']}, "
            f"registered={statistics['registered']}, "
            f"active_30d={statistics['active_30_days']}, "
            f"resume={statistics['resume_uploaded']}, "
            f"profile={statistics['profile_filled']}, "
            f"assessment={statistics['assessment_passed']}, "
            f"salary={statistics['average_graduate_salary']}, "
            f"internships={statistics['students_on_internships']}, "
            f"vacancies={statistics['total_vacancies']}"
        )

        return {
            "edupartner": edupartner_info,
            "statistics": statistics,
            "employed_graduates": employed_graduates_data,
            "popular_industries": popular_industries,
            "hiring_funnel": hiring_funnel,
            "top_companies_by_placements": top_companies,
            "timestamp": timezone.now().isoformat(),
        }

    @staticmethod
    def get_faculty_analytics(faculty_id):
        try:
            faculty = Faculty.objects.select_related(
                "edupartner__edupartner_type", "domain"
            ).get(id=faculty_id, is_active=True)
        except Faculty.DoesNotExist:
            logger.warning(f"Faculty with id {faculty_id} not found or inactive")
            return None

        candidates = Candidate.objects.filter(faculty=faculty).values_list(
            "id", flat=True
        )

        candidates_list = list(candidates)
        total_candidates = len(candidates_list)

        faculty_domains_list = [faculty.domain.id] if faculty.domain else []

        edupartner_info = {
            "id": str(faculty.edupartner.id),
            "name": faculty.edupartner.name,
            "type": (
                faculty.edupartner.edupartner_type.name
                if faculty.edupartner.edupartner_type
                else None
            ),
            "country": faculty.edupartner.country,
            "city": faculty.edupartner.city,
            "website": faculty.edupartner.website,
        }

        faculty_info = {
            "id": str(faculty.id),
            "name": faculty.name,
            "description": faculty.description,
            "domain": (
                {
                    "id": str(faculty.domain.id),
                    "name": faculty.domain.name,
                }
                if faculty.domain
                else None
            ),
        }

        empty_stats = {
            "edupartner": edupartner_info,
            "faculty": faculty_info,
            "statistics": {
                "source_students": 0,
                "registered": 0,
                "active_30_days": 0,
                "resume_uploaded": 0,
                "profile_filled": 0,
                "assessment_passed": 0,
                "average_graduate_salary": 0,
                "students_on_internships": 0,
                "total_vacancies": 0,
            },
            "employed_graduates": {
                "total_graduates": 0,
                "employed_count": 0,
                "employment_rate_percentage": 0,
            },
            "popular_industries": {
                "7_days": [],
                "30_days": [],
                "12_months": [],
            },
            "hiring_funnel": {
                "resumes_created": 0,
                "interviewed": 0,
                "offered": 0,
                "hired": 0,
                "conversion_rates": {
                    "resume_to_interview": 0.0,
                    "interview_to_offer": 0.0,
                    "offer_to_hire": 0.0,
                    "overall_conversion": 0.0,
                },
            },
            "top_companies_by_placements": [],
            "timestamp": timezone.now().isoformat(),
        }

        if not candidates_list:
            logger.info(f"No active candidates found for faculty {faculty.name}")
            if faculty_domains_list:
                empty_stats["popular_industries"] = get_popular_industries(
                    faculty_domains_list
                )
            return empty_stats

        statistics = get_statistics_cards(
            candidates_list,
            faculty_domains_list,
            edupartner_id=str(faculty.edupartner.id),
        )
        employed_graduates_data = get_employed_graduates(candidates_list, total_candidates)
        hiring_funnel = get_hiring_funnel(candidates_list)
        top_companies = get_top_companies_by_placements(candidates_list, limit=10)

        if faculty_domains_list:
            popular_industries = get_popular_industries(faculty_domains_list)
        else:
            popular_industries = {
                "7_days": [],
                "30_days": [],
                "12_months": [],
            }

        logger.info(
            f"Analytics for faculty {faculty.name} in {faculty.edupartner.name}: "
            f"source={statistics['source_students']}, "
            f"registered={statistics['registered']}, "
            f"active_30d={statistics['active_30_days']}, "
            f"resume={statistics['resume_uploaded']}, "
            f"profile={statistics['profile_filled']}, "
            f"assessment={statistics['assessment_passed']}, "
            f"salary={statistics['average_graduate_salary']}, "
            f"internships={statistics['students_on_internships']}, "
            f"vacancies={statistics['total_vacancies']}"
        )

        return {
            "edupartner": edupartner_info,
            "faculty": faculty_info,
            "statistics": statistics,
            "employed_graduates": employed_graduates_data,
            "popular_industries": popular_industries,
            "hiring_funnel": hiring_funnel,
            "top_companies_by_placements": top_companies,
            "timestamp": timezone.now().isoformat(),
        }

    @staticmethod
    def get_edupartner_ids():
        return list(
            EduPartner.objects.filter(is_active=True).values_list("id", flat=True)
        )

    @staticmethod
    def get_faculty_ids():
        return list(
            Faculty.objects.filter(
                is_active=True, edupartner__is_active=True
            ).values_list("id", flat=True)
        )

    @staticmethod
    def get_faculty_less_edupartner_ids():
        """
        Edupartners with candidates but zero active faculties.
        These are invisible to the per-faculty sync (get_faculty_ids) and
        need to be synced at the edupartner level instead.
        """
        edupartner_ids_with_candidates = (
            Candidate.objects.filter(edupartner__isnull=False)
            .values_list("edupartner_id", flat=True)
            .distinct()
        )
        edupartner_ids_with_faculty = (
            Faculty.objects.filter(is_active=True)
            .values_list("edupartner_id", flat=True)
            .distinct()
        )
        faculty_less_ids = set(edupartner_ids_with_candidates) - set(edupartner_ids_with_faculty)
        return list(
            EduPartner.objects.filter(
                id__in=faculty_less_ids, is_active=True
            ).values_list("id", flat=True)
        )
