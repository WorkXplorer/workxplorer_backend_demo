from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import AllowAny

from utils.language import get_request_language

from ..models import Citizenship
from ..serializers import CitizenshipSerializer


class CitizenshipListView(generics.ListAPIView):
    """
    List all citizenships with multilingual support.

    Supports search by name in the requested language.

    Query Parameters:
        - search: Search term to filter citizenships by name

    The name is returned in the language specified by the Accept-Language header.
    Supported languages: en, ru, uz

    GET /api/v1/profiles/citizenships/
    GET /api/v1/profiles/citizenships/?search=uzbek
    """

    serializer_class = CitizenshipSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        queryset = Citizenship.objects.all()
        search = self.request.query_params.get("search", "").strip()

        if search:
            language = get_request_language()

            # Build search query based on language
            if language == "ru":
                queryset = queryset.filter(
                    Q(name_ru__icontains=search)
                    | Q(name_en__icontains=search)
                    | Q(name__icontains=search)
                )
            elif language == "uz":
                queryset = queryset.filter(
                    Q(name_uz__icontains=search)
                    | Q(name_en__icontains=search)
                    | Q(name__icontains=search)
                )
            else:
                queryset = queryset.filter(
                    Q(name_en__icontains=search) | Q(name__icontains=search)
                )

        return queryset


citizenship_list_view = CitizenshipListView.as_view()
