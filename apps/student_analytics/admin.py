from django.contrib import admin, messages

from apps.student_analytics.models import (
    StudentAnalytics,
    SkillRoadmap,
    RoadmapItem,
    VacancySkillRoadmap,
    VacancyRoadmapItem,
)


class RoadmapItemInline(admin.TabularInline):
    model = RoadmapItem
    extra = 0
    fields = ("order", "skill_name", "skill", "status", "is_critical", "impact_percentage")
    readonly_fields = ("skill",)
    ordering = ("order",)


class SkillRoadmapInline(admin.StackedInline):
    model = SkillRoadmap
    extra = 0
    show_change_link = True
    fields = ("target_role", "ai_model", "generated_at")
    readonly_fields = ("generated_at",)


@admin.register(StudentAnalytics)
class StudentAnalyticsAdmin(admin.ModelAdmin):
    list_display = ("candidate", "target_role", "market_match_percentage", "track_progress_percentage", "input_tokens", "output_tokens", "thinking_tokens", "last_computed_at")
    list_filter = ("target_role",)
    search_fields = ("candidate__email", "target_role")
    readonly_fields = ("last_computed_at",)
    inlines = (SkillRoadmapInline,)


@admin.register(SkillRoadmap)
class SkillRoadmapAdmin(admin.ModelAdmin):
    list_display = ("__str__", "target_role", "ai_model", "input_tokens", "output_tokens", "thinking_tokens", "generated_at")
    list_filter = ("ai_model",)
    search_fields = ("analytics__candidate__email", "target_role")
    readonly_fields = ("generated_at",)
    inlines = (RoadmapItemInline,)
    actions = ("regenerate_materials",)

    @admin.action(description="Re-generate learning materials for selected roadmaps")
    def regenerate_materials(self, request, queryset):
        from apps.skills.tasks import enqueue_learning_materials_generation
        from apps.skills.models import SkillLearningMaterial

        count = 0
        for roadmap in queryset:
            skill_ids = roadmap.items.filter(skill__isnull=False).values_list("skill_id", flat=True)
            SkillLearningMaterial.objects.filter(skill_id__in=skill_ids).delete()
            enqueue_learning_materials_generation(str(roadmap.id), ai_model=roadmap.ai_model)
            count += 1

        self.message_user(request, f"Queued material regeneration for {count} roadmap(s).", messages.SUCCESS)


@admin.register(RoadmapItem)
class RoadmapItemAdmin(admin.ModelAdmin):
    list_display = ("skill_name", "roadmap", "order", "status", "is_critical", "impact_percentage")
    list_filter = ("status", "is_critical")
    search_fields = ("skill_name", "roadmap__analytics__candidate__email")
    ordering = ("roadmap", "order")


class VacancyRoadmapItemInline(admin.TabularInline):
    model = VacancyRoadmapItem
    extra = 0
    fields = ("order", "skill_name", "skill", "status", "is_critical", "impact_percentage")
    readonly_fields = ("skill",)
    ordering = ("order",)


@admin.register(VacancySkillRoadmap)
class VacancySkillRoadmapAdmin(admin.ModelAdmin):
    list_display = ("__str__", "application", "ai_model", "input_tokens", "output_tokens", "thinking_tokens", "generated_at")
    list_filter = ("ai_model",)
    search_fields = ("application__candidate__email", "application__vacancy__title")
    readonly_fields = ("generated_at",)
    inlines = (VacancyRoadmapItemInline,)
    actions = ("regenerate_materials",)

    @admin.action(description="Re-generate learning materials for selected vacancy roadmaps")
    def regenerate_materials(self, request, queryset):
        from apps.skills.tasks import enqueue_vacancy_learning_materials_generation
        from apps.skills.models import SkillLearningMaterial

        count = 0
        for roadmap in queryset:
            skill_ids = roadmap.items.filter(skill__isnull=False).values_list("skill_id", flat=True)
            SkillLearningMaterial.objects.filter(skill_id__in=skill_ids).delete()
            enqueue_vacancy_learning_materials_generation(str(roadmap.id), ai_model=roadmap.ai_model)
            count += 1

        self.message_user(request, f"Queued material regeneration for {count} vacancy roadmap(s).", messages.SUCCESS)


@admin.register(VacancyRoadmapItem)
class VacancyRoadmapItemAdmin(admin.ModelAdmin):
    list_display = ("skill_name", "roadmap", "order", "status", "is_critical", "impact_percentage")
    list_filter = ("status", "is_critical")
    search_fields = ("skill_name", "roadmap__application__candidate__email")
    ordering = ("roadmap", "order")
