from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

urlpatterns = [
    path("dashboard-admin-wxplr/", admin.site.urls),
    path("api/v1/", include("config.urls.api_v1")),
    path("api/v2/", include("config.urls.api_v2")),
]

# Serve media files in production
urlpatterns += [
    re_path(
        r"^mediafiles/(?P<path>.*)$",
        serve,
        {
            "document_root": settings.MEDIA_ROOT,
        },
    ),
]
