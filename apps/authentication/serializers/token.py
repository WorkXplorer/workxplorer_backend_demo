import os
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class EnvironmentAwareTokenSerializer(TokenObtainPairSerializer):
    """
    Standard email+password login, plus an optional 'phone' field so a user
    with a verified phone number can log in with phone+password instead of
    email+password. Shared by both the web (cookie) and mobile login views.

    Identifier resolution (is this an email or a verified phone, does it
    exist, timing-safe failure) all happens in EmailOrPhoneBackend — this
    serializer just picks whichever of 'email'/'phone' was sent and hands it
    to Django's authenticate() as-is.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field].required = False
        self.fields["phone"] = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        if not attrs.get(self.username_field):
            phone = attrs.pop("phone", None)
            if not phone:
                raise serializers.ValidationError(
                    {"email": "Email or phone is required."}
                )
            attrs[self.username_field] = phone
        else:
            attrs.pop("phone", None)

        return super().validate(attrs)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['env'] = os.environ.get('DJANGO_ENVIRONMENT', 'production')
        return token
