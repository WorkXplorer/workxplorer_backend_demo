from django.urls import path, include

urlpatterns = [
    # Applications v2 — flexible status system
    path("applications/", include("apps.applications.urls_v2")),
]
