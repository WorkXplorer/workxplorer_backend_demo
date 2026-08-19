from django.urls import path

from .views import ai_action_view

urlpatterns = [
    path("validate/", ai_action_view, name="ai-validate"),
]
