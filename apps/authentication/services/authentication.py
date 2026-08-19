# backend/apps/authentication/authentication.py
import zoneinfo
import logging
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


def activate_request_timezone(request, user=None):
    """Activate timezone from X-Timezone header or user's saved timezone.

    Runs at the start of a request so all datetime operations in the
    request lifecycle use the correct timezone.

    Can be called before the user is fully authenticated (login flow).
    When user is provided and a valid X-Timezone header exists, persists
    it to the user's profile (cache + DB).
    """
    header_tzname = request.headers.get("X-Timezone")
    tzname = None

    if header_tzname:
        try:
            zoneinfo.ZoneInfo(header_tzname)
            tzname = header_tzname
            if user:
                _persist_user_timezone(user, header_tzname)
        except Exception as e:
            logger.debug(f"Invalid timezone from header: {header_tzname}: {e}")

    if not tzname and user:
        cache_key = f"user_timezone_{user.id}"
        tzname = cache.get(cache_key)
        if not tzname:
            tzname = getattr(user, "timezone", None)
            if tzname:
                cache_timeout = getattr(settings, 'TIMEZONE_CACHE_TIMEOUT', 60 * 60 * 24 * 365)
                cache.set(cache_key, tzname, cache_timeout)

    if tzname:
        try:
            timezone.activate(zoneinfo.ZoneInfo(tzname))
            return
        except Exception as e:
            logger.warning(f"Invalid timezone value: {tzname}: {e}")

    timezone.deactivate()


def _persist_user_timezone(user, tzname):
    """Save timezone to cache and database."""
    cache_key = f"user_timezone_{user.id}"
    cached = cache.get(cache_key)
    if cached == tzname:
        return
    cache_timeout = getattr(settings, 'TIMEZONE_CACHE_TIMEOUT', 60 * 60 * 24 * 365)
    cache.set(cache_key, tzname, cache_timeout)
    try:
        from apps.authentication.models import CustomUser
        CustomUser.objects.filter(id=user.id).update(timezone=tzname)
    except Exception as e:
        logger.error(f"Failed to persist timezone for user {user.id}: {e}")


class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads tokens from the httpOnly access_token
    cookie (web) and falls back to the Authorization: Bearer header (mobile
    app, which cannot rely on httpOnly cookies) when no cookie is present.

    Uses request-level caching to prevent duplicate DB queries when
    authenticate() is called multiple times within the same request.
    Also activates user timezone post-authentication.
    """

    def authenticate(self, request):
        access_token = request.COOKIES.get("access_token")

        if access_token is None:
            header = self.get_header(request)
            access_token = self.get_raw_token(header) if header is not None else None

        if access_token is None:
            return None

        # Request-level cache: prevent duplicate DB queries when called
        # multiple times within the same request cycle.
        cache_attr = "_cached_jwt_auth_result"
        cached = getattr(request, cache_attr, None)
        if cached is not None:
            return cached

        try:
            validated_token = self.get_validated_token(access_token)

            # Mobile access tokens carry a 'sid' claim tying them to a
            # MobileSession. Web tokens never have this claim, so this is a
            # no-op for web — checked so logout/logout-all take effect
            # immediately instead of waiting out the token's 15-minute exp.
            sid = validated_token.get("sid")
            if sid is not None:
                from apps.authentication.services.mobile_session_service import MobileSessionService
                if not MobileSessionService.is_session_valid(sid):
                    raise AuthenticationFailed("Session has been revoked or expired")

            user = self.get_user(validated_token)
            result = (user, validated_token)
            setattr(request, cache_attr, result)
            # Activate user timezone after successful authentication
            activate_request_timezone(request, user)
            return result
        except (TokenError, InvalidToken):
            raise AuthenticationFailed("Token is invalid or expired")

    def get_validated_token(self, raw_token):
        """
        Validates an encoded JSON web token and returns a validated token
        wrapper object.
        """
        messages = []
        for AuthToken in self.get_auth_token_classes():
            try:
                return AuthToken(raw_token)
            except TokenError as e:
                messages.append(
                    {
                        "token_class": AuthToken.__name__,
                        "token_type": AuthToken.token_type,
                        "message": e.args[0],
                    }
                )

        raise InvalidToken("Given token not valid for any token type")

    def get_auth_token_classes(self):
        """
        Get the token classes that should be used for validation.
        Ensures an iterable (tuple) is returned even if settings value is None.
        """
        from rest_framework_simplejwt.settings import api_settings

        auth_classes = api_settings.AUTH_TOKEN_CLASSES
        if not auth_classes:
            return ()
        if not isinstance(auth_classes, (list, tuple)):
            return (auth_classes,)
        return tuple(auth_classes)
