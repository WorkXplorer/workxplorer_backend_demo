from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from core.responses import APIResponse
from utils.language import get_request_language
from ..localization import (
    get_localized_choices as vacancy_get_localized_choices,
    add_labels_to_vacancy_data as vacancy_add_labels_to_vacancy_data,
)


class VacancyStatusChoicesView(APIView):

    permission_classes = [AllowAny]

    @classmethod
    def get_localized_choices(cls, language: str) -> dict:
        return vacancy_get_localized_choices(language)

    @classmethod
    def add_labels_to_vacancy_data(cls, data: dict, language: str) -> dict:
        return vacancy_add_labels_to_vacancy_data(data, language)

    def get(self, request, *args, **kwargs):
        language = get_request_language()
        return APIResponse.success(data=self.get_localized_choices(language))


vacancy_status_choices_view = VacancyStatusChoicesView.as_view()
