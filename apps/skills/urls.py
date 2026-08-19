from django.urls import path

from .views import (
    skill_list_names_view,
    skill_create_view,
    skill_learning_materials_view,
)

urlpatterns = [
    path("list-names/", skill_list_names_view, name="skill-list-names"),
    path("create/", skill_create_view, name="skill-create"),
    path("<int:skill_id>/learning-materials/", skill_learning_materials_view, name="skill-learning-materials"),
]
