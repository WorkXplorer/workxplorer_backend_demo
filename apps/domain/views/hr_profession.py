from rest_framework.permissions import IsAuthenticated, IsAdminUser

from apps.domain.models import HrCreatedProfession
from apps.domain.serializers import HrCreatedProfessionSerializer
from rest_framework import generics


class HrCreatedProfessionListCreateAPIView(generics.ListCreateAPIView):
    """
    API endpoint for listing and creating HR created professions.
    Requires authentication.
    """

    queryset = (
        HrCreatedProfession.objects.select_related("company", "created_by")
        .all()
        .order_by("name")
    )
    serializer_class = HrCreatedProfessionSerializer
    permission_classes = [IsAdminUser]

    filterset_fields = ["company", "created_by"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]


class HrCreatedProfessionRetrieveUpdateDestroyAPIView(
    generics.RetrieveUpdateDestroyAPIView
):
    """
    API endpoint for retrieving, updating, and deleting a specific HR created profession.
    Requires authentication.
    """

    queryset = HrCreatedProfession.objects.select_related("company", "created_by").all()
    serializer_class = HrCreatedProfessionSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"
    lookup_url_kwarg = "profession_id"

    # ponytail: perform_update/save, perform_destroy, get_object all just call super()


hr_created_profession_list_create_view = HrCreatedProfessionListCreateAPIView.as_view()
hr_created_profession_detail_view = (
    HrCreatedProfessionRetrieveUpdateDestroyAPIView.as_view()
)
