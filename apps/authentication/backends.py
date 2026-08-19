from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from utils.phone import InvalidPhoneNumber, normalize_uz_phone

UserModel = get_user_model()


class EmailOrPhoneBackend(ModelBackend):
    """
    Authenticates against email (as before) or a verified phone number, when
    the submitted identifier normalizes to one. This is the single place
    email-or-phone login is decided — every authenticate() caller (login
    views, Django admin, allauth) gets both for free, instead of each call
    site re-implementing its own lookup.

    Timing safety: every failure path — unknown identifier, unverified
    phone, wrong password — runs the same password hash cost via a dummy
    check, mirroring Django's own ModelBackend mitigation for "user does not
    exist". Without this, resolving the identifier before hashing (e.g. "no
    such verified phone" returning immediately) would let response timing
    leak which phones/emails are registered.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username if username is not None else kwargs.get(UserModel.USERNAME_FIELD)
        if identifier is None or password is None:
            return None

        user = self._resolve_user(identifier)

        if user is None:
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    @staticmethod
    def _resolve_user(identifier):
        try:
            phone = normalize_uz_phone(identifier)
        except InvalidPhoneNumber:
            phone = None

        try:
            if phone:
                return UserModel.objects.get(phone=phone, phone_verified_at__isnull=False)
            return UserModel.objects.get(email__iexact=identifier)
        except UserModel.DoesNotExist:
            return None
        except UserModel.MultipleObjectsReturned:
            return None
