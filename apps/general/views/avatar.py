from rest_framework import generics
from rest_framework.permissions import AllowAny
from apps.general.models import Avatar
from apps.general.serializers import ProfilePictureSerializer


class ProfilePictureListAPIView(generics.ListAPIView):
    queryset = Avatar.objects.filter(is_active=True)
    serializer_class = ProfilePictureSerializer
    permission_classes = (AllowAny,)


profile_picture_view = ProfilePictureListAPIView.as_view()
