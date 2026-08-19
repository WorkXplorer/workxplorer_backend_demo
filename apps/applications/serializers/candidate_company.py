"""
Schema serializers for the candidate ↔ company applications aggregation.

The actual payloads are produced by CandidateCompanyApplicationsService;
these serializers exist so drf-spectacular documents the responses.
"""

from rest_framework import serializers


class CandidateCompanyRecruiterSerializer(serializers.Serializer):
    """Recruiter assigned to the vacancy (Vacancy.created_by)."""

    id = serializers.UUIDField()
    full_name = serializers.CharField(allow_null=True)


class CandidateCompanyApplicationEntrySerializer(serializers.Serializer):
    """One application of the candidate to a company vacancy."""

    application_id = serializers.UUIDField()
    vacancy_id = serializers.UUIDField()
    vacancy_title = serializers.CharField()
    applied_at = serializers.CharField(
        allow_null=True,
        help_text="Application date in dd.mm.yyyy format",
    )
    ai_score = serializers.FloatField(
        allow_null=True,
        help_text="AI evaluation match score (0-100)",
    )
    ai_evaluation_status = serializers.CharField(
        help_text="AI evaluation pipeline status (pending/processing/completed/failed)",
    )
    ai_passed = serializers.BooleanField(
        allow_null=True,
        help_text="Whether the score passes the vacancy's minimum_ai_score threshold",
    )
    status = serializers.CharField(help_text="Application status key")
    status_label = serializers.CharField(help_text="Localized status label")
    status_color = serializers.CharField(allow_null=True)
    is_best_match = serializers.BooleanField(
        help_text="True only for the highest-scoring application of the candidate",
    )
    recruiter = CandidateCompanyRecruiterSerializer(allow_null=True)
    salary = serializers.CharField(
        allow_null=True,
        help_text="Salary the company posted for this vacancy, or '-' if unspecified",
    )


class CandidateCompanyApplicationsResponseSerializer(serializers.Serializer):
    """Detail response: all applications of a candidate to the company."""

    candidate_id = serializers.UUIDField()
    total_count = serializers.IntegerField()
    applications = CandidateCompanyApplicationEntrySerializer(many=True)


class CandidateCompanySummarySerializer(serializers.Serializer):
    """Per-row summary embedded in the candidates list and kanban cards."""

    total_count = serializers.IntegerField(
        help_text="How many vacancies of this company the candidate applied to",
    )
    applications = CandidateCompanyApplicationEntrySerializer(
        many=True,
        help_text="Every application this candidate submitted to the company, "
                  "best match first (the first item has is_best_match=True)",
    )
    best_match = CandidateCompanyApplicationEntrySerializer(
        allow_null=True,
        help_text="Deprecated: same as applications[0]. Kept for backward "
                  "compatibility with existing v1 consumers; new clients "
                  "should read applications instead.",
    )
