from rest_framework.permissions import AllowAny
from django.db.models import Q, Case, When, IntegerField
from rest_framework.generics import ListAPIView, RetrieveAPIView

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from apps.domain.models import Domain
from apps.domain.serializers import DomainSerializer, DomainListSerializer
from utils.language import get_request_language


class DomainDetailAPIView(RetrieveAPIView):
    """
    API endpoint for retrieving a specific domain.
    Requires domain ID in the URL.
    """

    queryset = Domain.objects.all()
    serializer_class = DomainSerializer
    permission_classes = [AllowAny]
    lookup_field = "pk"

    # ponytail: get() just calls super() — no custom logic needed


class DomainListNamesAPIView(ListAPIView):
    """
    API endpoint for getting a lightweight list of domains (id and name only).
    """

    queryset = Domain.objects.all().order_by("name")
    serializer_class = DomainListSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    @extend_schema(
        summary="Get domain names list (autocomplete)",
        description="Get a lightweight list of domains with only ID and name. Ideal for dropdown/autocomplete with search filtering. NO AUTHENTICATION REQUIRED.",
        parameters=[
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Search by domain name (case-insensitive substring match). Recommended: minimum 2 characters",
                required=False,
                examples=[
                    OpenApiExample("Search by 'IT'", value="IT"),
                    OpenApiExample("Search by 'Healthcare'", value="Health"),
                ],
            ),
        ],
        responses={
            200: DomainListSerializer(many=True),
        },
        tags=["Domains"],
    )
    def get(self, request, *args, **kwargs):
        """
        Get lightweight list of domains for dropdown/autocomplete.
        """
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """
        Filter domains by search parameter with relevance ordering.
        Prioritizes matches at the beginning of the name.
        """
        queryset = super().get_queryset()
        search = self.request.query_params.get("search", "").strip().lower()
        language = get_request_language()
        name_field = f"name_{language}"
        if search:
            # Filter: only items that start with the search term (case-insensitive)
            queryset = queryset.filter(
                Q(name_en__icontains=search)
                | Q(name_ru__icontains=search)
                | Q(name_uz__icontains=search)
            )

            # Order by relevance: exact match first, then by name
            queryset = queryset.annotate(
                relevance=Case(
                    When(**{f"{name_field}__istartswith": search}, then=1),
                    When(**{f"{name_field}__icontains": search}, then=2),
                    default=3,
                    output_field=IntegerField(),
                )
            ).order_by("relevance", name_field)
        return queryset


# Create view instances
domain_detail_view = DomainDetailAPIView.as_view()
domain_list_names_view = DomainListNamesAPIView.as_view()
