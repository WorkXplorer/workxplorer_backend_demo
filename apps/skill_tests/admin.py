from django.contrib import admin

from apps.skill_tests.models import SkillTest, TestAttempt, TestQuestion, TestAnswer


class TestQuestionInline(admin.TabularInline):
    model = TestQuestion
    extra = 0
    fields = ("order", "question_type", "question_text", "points", "category")
    ordering = ("order",)


class TestAnswerInline(admin.TabularInline):
    model = TestAnswer
    extra = 0
    fields = ("question", "selected_option_id", "open_ended_text", "is_correct", "points_earned")
    readonly_fields = ("question", "is_correct", "points_earned", "ai_evaluation")
    ordering = ("question__order",)


@admin.register(SkillTest)
class SkillTestAdmin(admin.ModelAdmin):
    list_display = ("title", "skill", "target_level", "total_questions", "passing_score", "input_tokens", "output_tokens", "thinking_tokens", "is_active", "created_at")
    list_filter = ("is_active", "target_level", "ai_model")
    search_fields = ("title", "skill__name")
    readonly_fields = ("created_at", "updated_at")
    inlines = (TestQuestionInline,)


@admin.register(TestQuestion)
class TestQuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "test", "question_type", "order", "points", "category")
    list_filter = ("question_type",)
    search_fields = ("question_text", "test__title", "category")
    ordering = ("test", "order")


@admin.register(TestAttempt)
class TestAttemptAdmin(admin.ModelAdmin):
    list_display = ("__str__", "candidate", "test", "status", "score_percentage", "passed", "input_tokens", "output_tokens", "thinking_tokens", "started_at")
    list_filter = ("status", "passed")
    search_fields = ("candidate__email", "test__title")
    readonly_fields = ("started_at", "completed_at", "updated_at")
    inlines = (TestAnswerInline,)


@admin.register(TestAnswer)
class TestAnswerAdmin(admin.ModelAdmin):
    list_display = ("__str__", "attempt", "is_correct", "points_earned", "answered_at")
    list_filter = ("is_correct",)
    search_fields = ("attempt__candidate__email", "question__question_text")
    readonly_fields = ("answered_at",)
