from rest_framework import generics
from django.shortcuts import get_object_or_404
from django.utils import timezone
from utils.candidate_permission import IsCandidatePermission
from apps.vacancies.models import VacancyView
from apps.vacancies.serializers import VacancyViewSerializer
from core.responses import APIResponse
from django.utils.translation import gettext as _


class EndVacancyViewSessionView(generics.UpdateAPIView):
    """
    End vacancy view session and calculate duration.
    Called when candidate leaves vacancy page or closes browser.
    """

    permission_classes = [IsCandidatePermission]
    queryset = VacancyView.objects.all()
    serializer_class = VacancyViewSerializer

    def update(self, request, *args, **kwargs):
        view_session_id = kwargs.get("pk")
        vacancy_view = get_object_or_404(
            self.get_queryset(), id=view_session_id, candidate=request.user.candidate
        )

        if not vacancy_view.session_end:
            vacancy_view.session_end = timezone.now()
            vacancy_view.save()  # This will trigger duration calculation in the model

            return APIResponse.success(
                data={"duration_seconds": vacancy_view.duration_seconds},
                message=_("Session ended successfully"),
            )

        return APIResponse.success(message=_("Session already ended"))

    def post(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


end_vacancy_view_session_view = EndVacancyViewSessionView.as_view()
