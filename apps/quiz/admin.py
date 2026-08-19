from django.contrib import admin
from import_export import resources
from import_export.fields import Field
from import_export.admin import ExportActionMixin
from apps.quiz.models import (
    AnswerChoice,
    Question,
    CareerOption,
    QuizResult,
    Quiz,
    QuizType,
)

# --- Resources ---

class QuestionResource(resources.ModelResource):
    class Meta:
        model = Question
        fields = ("id", "title", "created_at", "updated_at")
        export_order = fields

class AnswerChoiceResource(resources.ModelResource):
    class Meta:
        model = AnswerChoice
        fields = ("id", "question__title", "text", "point", "career_option__title", "created_at")
        export_order = fields

class CareerOptionResource(resources.ModelResource):
    class Meta:
        model = CareerOption
        fields = ("id", "title", "created_at", "updated_at")
        export_order = fields

class QuizResultResource(resources.ModelResource):
    career_options_display = Field(column_name="Career Options")

    def dehydrate_career_options_display(self, obj):
        # Converts ["Option A", "Option B"] → "Option A, Option B"
        if isinstance(obj.career_options, list):
            return ", ".join(str(x) for x in obj.career_options)
        return str(obj.career_options)

    class Meta:
        model = QuizResult
        fields = ("id", "candidate__email", "quiz__name", "domain__name", "career_options_display", "created_at")
        export_order = fields

class QuizResource(resources.ModelResource):
    class Meta:
        model = Quiz
        fields = ("id", "name", "quiz_type__name", "is_active", "created_at")
        export_order = fields

class QuizTypeResource(resources.ModelResource):
    class Meta:
        model = QuizType
        fields = ("id", "name", "is_active", "created_at")
        export_order = fields


# --- Inlines ---

class AnswerChoiceInline(admin.TabularInline):
    model = AnswerChoice
    extra = 1
    min_num = 1
    show_change_link = True


# --- Admin classes ---

@admin.register(Question)
class QuestionAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_classes = [QuestionResource]
    list_display = ("id", "title", "created_at", "updated_at")
    search_fields = ("text",)
    inlines = [AnswerChoiceInline]

@admin.register(AnswerChoice)
class AnswerChoiceAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_classes = [AnswerChoiceResource]
    list_display = ("id", "question", "text", "point", "career_option", "created_at", "updated_at")
    list_filter = ("career_option",)
    search_fields = ("text",)
    autocomplete_fields = ("career_option",)
    filter_horizontal = ("domains",)

@admin.register(CareerOption)
class CareerOptionAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_classes = [CareerOptionResource]
    list_display = ("id", "title", "created_at", "updated_at")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    filter_horizontal = ("skills",)

@admin.register(QuizResult)
class QuizResultAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_classes = [QuizResultResource]
    list_display = ("id", "candidate", "quiz", "domain", "get_career_options", "created_at")
    search_fields = ("candidate__email",)
    ordering = ("-created_at",)

    @admin.display(description="Career Options")
    def get_career_options(self, obj):
        if isinstance(obj.career_options, list):
            return ", ".join(str(x) for x in obj.career_options)
        return str(obj.career_options)

@admin.register(QuizType)
class QuizTypeAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_classes = [QuizTypeResource]
    list_display = ("id", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    filter_horizontal = ("domains",)

@admin.register(Quiz)
class QuizAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_classes = [QuizResource]
    list_display = ("id", "name", "quiz_type", "is_active", "created_at")
    list_filter = ("is_active", "quiz_type")
    search_fields = ("name", "description")