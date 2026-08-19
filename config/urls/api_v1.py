import logging
from django.urls import path, include
from django.conf import settings
from apps.authentication.views.cookie_auth import (
    CookieTokenObtainPairView,
    AdminCookieTokenObtainPairView,
    CookieTokenRefreshView,
    CookieTokenVerifyView,
    CookieLogoutView,
)
from apps.authentication.views.mobile_auth import (
    MobileLoginView,
    MobileRefreshView,
    MobileLogoutView,
    MobileLogoutAllView,
)
from apps.authentication.views.mobile_oauth import (
    MobileOAuthChallengeView,
    MobileGoogleView,
    MobileAppleView,
)
from apps.authentication.views.language import UpdateLanguageView
from apps.authentication.views.oauth_views import GoogleOAuthCandidateView
from apps.authentication.views.phone_verification import SendPhoneOtpView, VerifyPhoneOtpView
from apps.authentication.views.phone_registration import (
    SendPhoneRegistrationOtpView,
    VerifyPhoneRegistrationView,
)
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

logger = logging.getLogger(__name__)


urlpatterns = [
    # Custom users app urls
    path("users/", include("apps.authentication.urls")),
    # Profiles app urls
    path("profiles/", include("apps.profiles.urls")),
    # Vacancies app urls
    path("vacancies/", include("apps.vacancies.urls")),
    # Applications app urls
    path("applications/", include("apps.applications.urls")),
    # Resumes app urls
    path("resumes/", include("apps.resumes.urls")),
    # Matching app urls
    path("matching/", include("apps.matching.urls")),
    # Quiz app urls
    path("quiz/", include("apps.quiz.urls")),
    # Skills app urls
    path("skills/", include("apps.skills.urls")),
    # Edu-Partners app urls
    path("edupartners/", include("apps.edupartners.urls")),
    # Notifications app urls
    path("notifications/", include("apps.notifications.urls")),
    # General app urls
    path("general/", include("apps.general.urls")),
    # Domain app urls
    path("domain/", include("apps.domain.urls")),
    # Conversations app urls
    path("conversations/", include("apps.conversations.urls")),
    # Languages app urls
    path("languages/", include("apps.languages.urls")),
    # HR Templates app urls
    path("hr-templates/", include("apps.hr_templates.urls")),
    # Subscriptions app urls
    path("subscriptions/", include("apps.subscriptions.urls")),
    # AI app urls
    path("ai/", include("apps.ai.urls")),
    # Banners app urls
    path("banners/", include("apps.banners.urls")),
    # Student Analytics app urls
    path("student-analytics/", include("apps.student_analytics.urls")),
    # Skill Tests app urls
    path("skill-tests/", include("apps.skill_tests.urls")),
    # Cookie-based authentication
    path("auth/login/", CookieTokenObtainPairView.as_view(), name="cookie-login"),
    path("auth/admin-login/", AdminCookieTokenObtainPairView.as_view(), name="admin-cookie-login"),
    path("auth/refresh/", CookieTokenRefreshView.as_view(), name="cookie-refresh"),
    path("auth/verify/", CookieTokenVerifyView.as_view(), name="cookie-verify"),
    path("auth/logout/", CookieLogoutView.as_view(), name="cookie-logout"),
    # Mobile app authentication (tokens in body, not cookies; opaque
    # refresh tokens backed by MobileSession, see apps/authentication/services/mobile_session_service.py)
    path("auth/mobile/login/", MobileLoginView.as_view(), name="mobile-login"),
    path("auth/mobile/refresh/", MobileRefreshView.as_view(), name="mobile-refresh"),
    path("auth/mobile/logout/", MobileLogoutView.as_view(), name="mobile-logout"),
    path("auth/mobile/logout-all/", MobileLogoutAllView.as_view(), name="mobile-logout-all"),
    path("auth/mobile/oauth/challenge/", MobileOAuthChallengeView.as_view(), name="mobile-oauth-challenge"),
    path("auth/mobile/google/", MobileGoogleView.as_view(), name="mobile-google"),
    path("auth/mobile/apple/", MobileAppleView.as_view(), name="mobile-apple"),
    path("auth/google/", GoogleOAuthCandidateView.as_view(), name="google-oauth-candidate"),
    path("auth/language/", UpdateLanguageView.as_view(), name="update-language"),
    # Phone verification — attach/verify a phone on an existing account
    # (shared by web + mobile, both authenticate via CookieJWTAuthentication)
    path("auth/phone/send-otp/", SendPhoneOtpView.as_view(), name="phone-send-otp"),
    path("auth/phone/verify-otp/", VerifyPhoneOtpView.as_view(), name="phone-verify-otp"),
    # Phone-based registration — anonymous signup by phone OTP (also shared by web + mobile)
    path("auth/phone/register/send-otp/", SendPhoneRegistrationOtpView.as_view(), name="phone-register-send-otp"),
    path("auth/phone/register/verify/", VerifyPhoneRegistrationView.as_view(), name="phone-register-verify"),
    # Django RQ
    path("django-rq/", include("django_rq.urls")),
    # schema
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # swagger UI
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # redoc
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Only add debug toolbar URLs in development
if settings.DEBUG:
    try:
        from debug_toolbar.toolbar import debug_toolbar_urls

        urlpatterns += debug_toolbar_urls()
    except ImportError:
        logger.warning("Debug toolbar is not installed, skipping debug toolbar URLs.")
