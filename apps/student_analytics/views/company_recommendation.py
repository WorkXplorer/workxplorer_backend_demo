from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.skills.localization import user_preferred_language
from apps.student_analytics.serializers.company_recommendation import RecommendedCompanySerializer
from apps.student_analytics.services.company_recommendation import get_recommended_companies
from core.responses import APIResponse


class RecommendedCompaniesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        description="Get top 7 recommended companies for the candidate based on resume-vacancy matching, sorted by subscription priority (Pro > Basic > Free).",
        responses={
            200: OpenApiResponse(
                response=RecommendedCompanySerializer(many=True),
                description="List of recommended companies",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "data": [
                                {
                                    "id": "550e8400-e29b-41d4-a716-446655440000",
                                    "name": "Uzum",
                                    "logo": "https://example.com/media/company_photos/uzum.jpg",
                                    "domain_name": "E-commerce",
                                    "employees_count": 1000,
                                    "open_vacancies_count": 24,
                                    "matching_vacancies_count": 12,
                                    "salary_min": "12000000.00",
                                    "salary_max": "18000000.00",
                                    "is_top_match": True,
                                    "subscription_tier": "company-pro",
                                },
                                {
                                    "id": "550e8400-e29b-41d4-a716-446655440001",
                                    "name": "Click",
                                    "logo": None,
                                    "domain_name": "Платежи",
                                    "employees_count": 500,
                                    "open_vacancies_count": 18,
                                    "matching_vacancies_count": 6,
                                    "salary_min": "9500000.00",
                                    "salary_max": "13000000.00",
                                    "is_top_match": True,
                                    "subscription_tier": "company-basic",
                                },
                            ],
                            "timestamp": "2026-06-19T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="User is not a candidate",
            ),
        },
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can access recommended companies."))

        language = user_preferred_language(user)
        companies = get_recommended_companies(user)

        serializer = RecommendedCompanySerializer(
            companies,
            many=True,
            context={"language": language},
        )
        return APIResponse.success(data=serializer.data)
