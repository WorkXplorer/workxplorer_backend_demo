from django.urls import path
from .views import language_list_view

urlpatterns = [
    path("", language_list_view, name="language-list"),
]
