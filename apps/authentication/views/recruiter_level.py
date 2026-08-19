from rest_framework.views import APIView
from apps.profiles.models import RecruiterProfile
from core.responses import APIResponse
from utils.language import get_request_language


class RecruiterLevelsAPIView(APIView):
    permission_classes = []

    # Translation mapping for level labels
    LEVEL_LABELS = {
        "Recruiter": {"uz": "Rekruter", "ru": "Рекрутер", "en": "Recruiter"},
        "Admin": {"uz": "Admin", "ru": "Админ", "en": "Admin"},
    }

    def get(self, request, *args, **kwargs):
        # Get requested language
        language = get_request_language()

        levels = [
            {
                "value": value,
                "label": self.LEVEL_LABELS.get(value, {}).get(language, label)
            }
            for value, label in RecruiterProfile.Level.choices
        ]
        return APIResponse.success(data={"levels": levels})


recruiter_levels_view = RecruiterLevelsAPIView.as_view()
