from django.urls import path
from .views import (
    profile_picture_view,
    inactive_company_view,
    company_confirm_view,
    manual_email_campaign_view,
)

urlpatterns = [
    path("avatars/", profile_picture_view, name="profile-avatars"),
    path(
        "email-campaigns/send/",
        manual_email_campaign_view,
        name="manual-email-campaign-send",
    ),
    path("inactive-companies/", inactive_company_view, name="inactive-companies"),
    path("confirm-company/", company_confirm_view, name="confirm-company"),
]
