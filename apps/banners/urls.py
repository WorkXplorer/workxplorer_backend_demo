from django.urls import path
from .views import banner_list_view, banner_click_view

urlpatterns = [
    path("", banner_list_view, name="banner-list"),
    path("click/", banner_click_view, name="banner-click"),
]
