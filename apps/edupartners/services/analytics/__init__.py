"""
Analytics module for EduPartner analytics data collection.
Provides separated components for different analytics aspects.
"""

from .main import EduPartnerAnalyticsService
from .cards import get_statistics_cards
from .employed_graduates import get_employed_graduates
from .hiring_funnel import get_hiring_funnel
from .popular_industries import get_popular_industries
from .top_companies import get_top_companies_by_placements

__all__ = [
    "EduPartnerAnalyticsService",
    "get_statistics_cards",
    "get_employed_graduates",
    "get_hiring_funnel",
    "get_popular_industries",
    "get_top_companies_by_placements",
]
