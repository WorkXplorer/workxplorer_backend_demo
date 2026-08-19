from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.authentication.models.user import CustomUser
from apps.general.services.language_cache import LanguageCacheService
from core.responses import APIResponse


class UpdateLanguageView(APIView):
    """
    Update the authenticated user's preferred language.

    Works for both candidates and recruiters.
    Saves the preference to the database and refreshes the Redis cache.
    """

    permission_classes = [IsAuthenticated]

    SUPPORTED_LANGUAGES = CustomUser.LanguageChoices.values

    @extend_schema(
        summary="Update preferred language",
        description="Set the authenticated user's preferred language (uz, ru, en). "
                    "Persists to DB and Redis cache.",
        request=inline_serializer(
            name="UpdateLanguageRequest",
            fields={"preferred_language": serializers.ChoiceField(choices=CustomUser.LanguageChoices.choices)},
        ),
        responses={
            200: inline_serializer(
                name="UpdateLanguageResponse",
                fields={"preferred_language": serializers.CharField()},
            )
        },
    )
    def patch(self, request, *args, **kwargs):
        language = request.data.get("language") or request.data.get("preferred_language")

        if not language:
            return APIResponse.bad_request(
                message=_("preferred_language is required."),
            )

        if language not in self.SUPPORTED_LANGUAGES:
            return APIResponse.bad_request(
                message=_("Unsupported language. Allowed values: uz, ru, en."),
            )

        user = request.user
        user.preferred_language = language
        user.save(update_fields=["preferred_language"])
        LanguageCacheService.set_user_language(str(user.id), language)

        return APIResponse.success(
            data={"preferred_language": language},
            message=_("Language preference updated successfully."),
        )
