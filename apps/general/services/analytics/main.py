"""
Main HR analytics service.
Orchestrates all analytics components and provides the main entry points.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.utils import timezone

from apps.authentication.models import Company
from apps.profiles.models import CompanyProfile
from apps.vacancies.models import Vacancy

from .cards import get_all_cards_metrics
from .top_industries import calculate_top_industries
from .hiring_dynamics import calculate_hiring_dynamics
from .application_dynamics import calculate_application_dynamics_yearly
from .utils import serialize_value

logger = logging.getLogger(__name__)


class HRAnalyticsService:
    """
    Service to collect HR analytics data for companies.
    Provides company-specific analytics that are isolated per company.
    """

    DEFAULT_PERIOD_DAYS = 30

    @staticmethod
    def get_company_analytics(
            company_id: str,
            end_date: Optional[datetime] = None,
            period_days: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Collect complete analytics data for a specific company.
        
        Args:
            company_id: UUID string of the company
            end_date: End date of the analysis period
            period_days: Length of the analysis period
            
        Returns:
            Complete analytics payload for the company, or None if not found
        """
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            logger.warning(f"Company with id {company_id} not found")
            return None

        if end_date is None:
            end_date = timezone.now()

        start_date = end_date - timedelta(days=period_days)

        # Get company profile
        try:
            company_profile = CompanyProfile.objects.get(company=company)
        except CompanyProfile.DoesNotExist:
            company_profile = None

        # Get vacancy IDs for this company
        vacancy_ids = list(
            Vacancy.objects.filter(company_id=company_id).values_list("id", flat=True)
        )

        # Build company info
        company_info = HRAnalyticsService._build_company_info(company, company_profile)

        # Collect all analytics components
        cards = HRAnalyticsService._collect_cards(
            start_date, end_date, period_days, company_id, vacancy_ids
        )

        analytics = HRAnalyticsService._collect_analytics(
            start_date, end_date, period_days, company_id
        )

        logger.info(
            f"Analytics collected for company {company.name}: "
            f"cards={bool(cards)}, analytics_components={len(analytics)}"
        )

        return {
            "source": "workxplorer",
            "timestamp": serialize_value(timezone.now()),
            "meta": {
                "env": getattr(settings, "ENVIRONMENT", "unknown"),
                "company_id": str(company_id),
            },
            "company": company_info,
            "cards": cards,
            "analytics": analytics,
            "analytics_timestamp": serialize_value(timezone.now()),
        }

    @staticmethod
    def _build_company_info(
            company: Company,
            company_profile: Optional[CompanyProfile]
    ) -> Dict[str, Any]:
        """Build company information dictionary.
        
        Note: Vacancy data is no longer included here.
        Vacancy analytics are sent via a separate dedicated webhook.
        """
        # Build full photo URL
        photo_url = None
        if company_profile and company_profile.photo:
            base_url = getattr(settings, "SITE_URL", "")
            photo_url = f"{base_url}{company_profile.photo.url}" if base_url else company_profile.photo.url

        return {
            "id": str(company.id),
            "name": company.name,
            "domain": company.domain.name if company.domain else None,
            "tin": company.tin,
            "is_active": company.is_active,
            "description": company_profile.description if company_profile else None,
            "address": company_profile.address if company_profile else None,
            "website": company_profile.website if company_profile else None,
            "photo": photo_url,
        }

    @staticmethod
    def _collect_cards(
            start_date: datetime,
            end_date: datetime,
            period_days: int,
            company_id: str,
            vacancy_ids: List
    ) -> Dict[str, Any]:
        """Collect all card metrics with error handling."""
        try:
            return get_all_cards_metrics(
                start_date=start_date,
                end_date=end_date,
                period_days=period_days,
                company_id=company_id,
                vacancy_ids=vacancy_ids,
            )
        except Exception as e:
            logger.warning(f"Failed to calculate cards for company {company_id}: {e}")
            return {}

    @staticmethod
    def _collect_analytics(
            start_date: datetime,
            end_date: datetime,
            period_days: int,
            company_id: str
    ) -> Dict[str, Any]:
        """Collect all analytics components with error handling."""
        analytics = {}

        # Top Industries
        try:
            analytics["top_industries"] = calculate_top_industries(
                start_date=start_date,
                end_date=end_date,
                period_days=period_days,
                company_id=company_id,
            )
        except Exception as e:
            logger.warning(f"Failed to calculate top_industries: {e}")
            analytics["top_industries"] = None

        # Hiring Dynamics
        try:
            analytics["hiring_dynamics"] = calculate_hiring_dynamics(
                start_date=start_date,
                end_date=end_date,
                period_days=period_days,
                interval="day",
                company_id=company_id,
            )
        except Exception as e:
            logger.warning(f"Failed to calculate hiring_dynamics: {e}")
            analytics["hiring_dynamics"] = None

        # Application Dynamics Yearly
        try:
            analytics["application_response_dynamics_yearly"] = calculate_application_dynamics_yearly(
                current_year=end_date.year,
                company_id=company_id,
            )
        except Exception as e:
            logger.warning(f"Failed to calculate application_response_dynamics_yearly: {e}")
            analytics["application_response_dynamics_yearly"] = None

        return analytics

    @staticmethod
    def get_company_ids() -> List[str]:
        """
        Get all active company IDs.
        
        Returns:
            List of active company ID strings
        """
        return list(
            Company.objects.filter(is_active=True).values_list("id", flat=True)
        )

    @staticmethod
    def get_analytics_summary(company_id: str) -> Dict[str, Any]:
        """
        Get a quick summary of analytics for a company.
        Useful for dashboard overview without full analytics.
        
        Args:
            company_id: UUID string of the company
            
        Returns:
            Summary dictionary with key metrics
        """
        end_date = timezone.now()
        period_days = 30
        start_date = end_date - timedelta(days=period_days)

        from .cards import (
            calculate_applications_count,
            calculate_open_vacancies,
        )

        applications = calculate_applications_count(
            start_date, end_date, period_days, company_id
        )
        vacancies = calculate_open_vacancies(end_date, period_days, company_id)

        return {
            "company_id": company_id,
            "applications_count": applications.get("current_count", 0),
            "applications_change": applications.get("percentage_change"),
            "open_vacancies": vacancies.get("current_count", 0),
            "vacancies_change": vacancies.get("percentage_change"),
            "period_days": period_days,
            "generated_at": serialize_value(timezone.now()),
        }
