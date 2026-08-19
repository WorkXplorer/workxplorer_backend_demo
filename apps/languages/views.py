from rest_framework import generics
from rest_framework.permissions import AllowAny
from .models import Language
from .serializers import LanguageSerializer


class LanguageListView(generics.ListAPIView):
    """
    List all available languages.

    Returns all languages that candidates can select when adding
    language proficiency to their resumes.

    GET /api/v1/languages/
    """

    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = [AllowAny]
    pagination_class = None


language_list_view = LanguageListView.as_view()
