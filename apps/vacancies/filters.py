"""
Filters for the vacancies app.
Provides advanced search and filtering capabilities for job vacancies.
"""

import django_filters
from django.db import models
from django.db.models import Exists, OuterRef
from .models import Vacancy
from apps.applications.models import JobApplication
from apps.authentication.models import Candidate
from apps.applications.models.choices import ApplicationStatus


class VacancyFilter(django_filters.FilterSet):
    """
    Advanced filtering for job vacancies.
    Enables students to search and filter job postings by multiple criteria.
    """

    # Text search in title
    search = django_filters.CharFilter(method="search_filter", label="Search")

    # Employment type filter
    employment_type = django_filters.ChoiceFilter(
        field_name="employment_type",
        choices=Vacancy._meta.get_field("employment_type").choices,
        label="Employment Type",
    )

    # Company address filter (case-insensitive partial match)

    location = django_filters.CharFilter(method="filter_location", label="Company Address")

    # Employment format filter
    employment_format = django_filters.ChoiceFilter(
        field_name="employment_format",
        choices=Vacancy._meta.get_field("employment_format").choices,
        label="Employment Format",
    )

    # Salary range filters
    salary_min = django_filters.NumberFilter(
        method="filter_salary_min", label="Minimum Salary (at least)"
    )
    salary_max = django_filters.NumberFilter(
        method="filter_salary_max", label="Maximum Salary (at most)"
    )

    # Currency for salary filter conversion
    currency = django_filters.CharFilter(
        method="filter_currency",
        label="Currency for salary filter (USD, UZS, EUR). Defaults to UZS if not specified.",
    )

    # Company filter
    company = django_filters.UUIDFilter(field_name="company__id", label="Company ID")
    company_name = django_filters.CharFilter(
        field_name="company__name", lookup_expr="icontains", label="Company Name"
    )

    # Date filters
    created_after = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="gte", label="Created After"
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="lte", label="Created Before"
    )

    # Skill filter (filter by required skills)
    skill = django_filters.NumberFilter(
        field_name="required_skills__id", label="Skill ID"
    )

    is_applied = django_filters.BooleanFilter(
        method="filter_is_applied",
        help_text="Filter by application status. True: show only applied vacancies, False: show only non-applied vacancies",
    )

    def filter_location(self, queryset, name, value):
        """
        Filter vacancies based on company address.
        Uses the company's profile address field.
        Ensures that each vacancy appears only once even if a company has
        multiple profiles with matching addresses.
        """
        return queryset.filter(
            company__companyprofile__address__icontains=value
        ).distinct()

    def filter_is_applied(self, queryset, name, value):
        """
        Filter vacancies based on whether the current user has applied.
        Only works for authenticated candidates.

        Uses Exists subquery for efficient single-pass filtering
        without duplicate rows.

        When is_applied=true: returns only vacancies the candidate has applied to
        (excluding withdrawn applications).
        When is_applied=false: returns vacancies where the candidate has NOT applied,
        OR where the application is withdrawn.
        """
        if not self.request or not self.request.user.is_authenticated:
            return queryset.none() if value else queryset

        if not (
                hasattr(self.request.user, "is_candidate")
                and self.request.user.is_candidate
        ):
            return queryset.none() if value else queryset

        try:
            candidate = Candidate.objects.get(email=self.request.user.email)

            applied_subquery = Exists(
                JobApplication.objects.filter(
                    vacancy=OuterRef("pk"),
                    candidate=candidate,
                ).exclude(status=ApplicationStatus.WITHDRAWN)
            )

            if value:
                # Show only vacancies the candidate has applied to (excluding withdrawn)
                return queryset.filter(applied_subquery)
            else:
                # Show vacancies where the candidate has NOT applied, OR where the application is withdrawn
                return queryset.exclude(applied_subquery)

        except Candidate.DoesNotExist:
            return queryset.none() if value else queryset

    def filter_salary_min(self, queryset, name, value):
        """
        Store salary_min value for combined processing in filter_currency.
        If currency filter is not provided, defaults to UZS for comparison.
        """
        self._salary_min = value
        if not self.data.get("currency"):
            from utils.currency_converter import filter_vacancies_by_salary
            return filter_vacancies_by_salary(queryset, str(value), None, "UZS")
        return queryset

    def filter_salary_max(self, queryset, name, value):
        """
        Store salary_max value for combined processing in filter_currency.
        If currency filter is not provided, defaults to UZS for comparison.
        """
        self._salary_max = value
        if not self.data.get("currency"):
            from utils.currency_converter import filter_vacancies_by_salary
            return filter_vacancies_by_salary(queryset, None, str(value), "UZS")
        return queryset

    def filter_currency(self, queryset, name, value):
        """
        Apply currency conversion to salary filters.
        Converts the user's salary range to each vacancy's own currency.
        """
        from utils.currency_converter import filter_vacancies_by_salary

        salary_min = self.data.get("salary_min")
        salary_max = self.data.get("salary_max")

        if not salary_min and not salary_max:
            return queryset

        return filter_vacancies_by_salary(queryset, salary_min, salary_max, value)

    class Meta:
        model = Vacancy
        fields = [
            "search",
            "employment_type",
            "employment_format",
            "location",
            "salary_min",
            "salary_max",
            "currency",
            "company",
            "company_name",
            "created_after",
            "created_before",
            "skill",
            "is_active",
            "is_applied",
        ]

    def search_filter(self, queryset, name, value):
        """
        Filter vacancies based on search term.
        """
        if value:
            return queryset.filter(
                models.Q(title__icontains=value) |
                models.Q(company__name__icontains=value)
            )
        return queryset
