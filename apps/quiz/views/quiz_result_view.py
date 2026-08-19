from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.responses import APIResponse
from utils.language import get_request_language
from utils import IsCandidatePermission
from ..models import QuizResult, CareerOption


class LatestQuizResultAPIView(APIView):
    """Return the most recent quiz result (career options) for the current candidate."""

    permission_classes = (IsAuthenticated, IsCandidatePermission)

    def get(self, request, *args, **kwargs):
        candidate = request.user.candidate
        result = (
            QuizResult.objects.filter(candidate=candidate)
            .select_related("domain")
            .first()
        )
        if not result:
            return APIResponse.not_found(message=_("No quiz results found"))

        lang = get_request_language()
        domain_name = None
        if result.domain:
            domain = result.domain
            if lang == "uz":
                domain_name = (
                    getattr(domain, "name_uz", None)
                    or getattr(domain, "name_en", None)
                    or domain.name
                )
            elif lang == "ru":
                domain_name = (
                    getattr(domain, "name_ru", None)
                    or getattr(domain, "name_en", None)
                    or domain.name
                )
            else:
                domain_name = getattr(domain, "name_en", None) or domain.name

        career_options = _resolve_career_options(result.career_options, lang)

        return APIResponse.success(
            data={
                "career_options": career_options,
                "domain": domain_name,
            },
            message=_("Latest quiz result retrieved successfully"),
        )


def _resolve_career_options(career_options, lang):
    """
    Resolve career options from stored IDs by fetching fresh translations
    from CareerOption in a single query, localized to the request language.

    Supported storage formats (backward-compatible):
      - Current:  [{"id": 1, "score": 80, "percentage": "85%"}, ...]
      - Previous: [{"id": 1, "position": "Backend Dev", "score": 80, ...}, ...]
      - Legacy:   ["Backend Developer", ...]

    For any entry with a numeric ``id``, the position title and description
    are resolved from the CareerOption model so that the response always
    reflects the candidate's current language setting.
    """
    if not isinstance(career_options, list):
        return []

    position_ids = set()
    for item in career_options:
        if isinstance(item, dict):
            pos_id = item.get("id")
            if isinstance(pos_id, int):
                position_ids.add(pos_id)

    career_lookup = {}
    if position_ids:
        career_options_db = CareerOption.objects.filter(
            id__in=position_ids
        ).values(
            "id",
            "title_en",
            "title_uz",
            "title_ru",
            "title",
            "description_en",
            "description_uz",
            "description_ru",
            "description",
        )
        for co in career_options_db:
            co_id = co["id"]
            if lang == "uz":
                title = co.get("title_uz") or co.get("title_en") or co.get("title")
                desc = co.get("description_uz") or co.get("description_en") or co.get("description") or ""
            elif lang == "ru":
                title = co.get("title_ru") or co.get("title_en") or co.get("title")
                desc = co.get("description_ru") or co.get("description_en") or co.get("description") or ""
            else:
                title = co.get("title_en") or co.get("title")
                desc = co.get("description_en") or co.get("description") or ""
            career_lookup[co_id] = (title, desc)

    result_list = []
    for item in career_options:
        if isinstance(item, dict):
            pos_id = item.get("id")
            if isinstance(pos_id, int):
                title, desc = career_lookup.get(pos_id, (str(pos_id), ""))
                result_list.append(
                    {
                        "id": pos_id,
                        "position": title,
                        "score": item.get("score", 0),
                        "percentage": item.get("percentage", ""),
                        "position_description": desc,
                    }
                )
            else:
                result_list.append(item)
        elif isinstance(item, str):
            result_list.append({"position": item})

    return result_list


latest_quiz_result_view = LatestQuizResultAPIView.as_view()

