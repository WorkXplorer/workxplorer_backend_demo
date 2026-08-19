from django.contrib import admin
from .models import (
    Resume,
    ResumeSkill,
    ResumeExperience,
    ResumeContact,
    ResumeCertificate,
    ResumeLanguageCertificate,
)


class ResumeCertificateInline(admin.TabularInline):
    model = ResumeCertificate
    extra = 1
    fields = ["name", "issuing_organization", "issue_date", "credential_url"]


class ResumeSkillInline(admin.TabularInline):
    model = ResumeSkill
    extra = 1
    autocomplete_fields = ["skill"]
    fields = ["skill", "proficiency_level", "minimum_years"]


class ResumeExperienceInline(admin.TabularInline):
    model = ResumeExperience
    extra = 1
    fields = ["company", "role", "start_date", "end_date", "description"]
    show_change_link = True


class ResumeContactInline(admin.TabularInline):
    model = ResumeContact
    extra = 1
    fields = ["type", "value"]


@admin.register(ResumeSkill)
class ResumeSkillAdmin(admin.ModelAdmin):
    list_display = ("resume", "skill", "minimum_years", "proficiency_level")
    search_fields = ("resume__title", "skill__name")
    list_filter = ("proficiency_level",)  # fixed tuple


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ("title", "candidate", "is_main", "created_at", "display_skills")
    list_filter = ("created_at", "is_main", "candidate")
    search_fields = ("title", "description", "candidate__email")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [
        ResumeContactInline,
        ResumeExperienceInline,
        ResumeSkillInline,
        ResumeCertificateInline,
    ]

    def display_skills(self, obj):
        skills = obj.resume_skills.select_related("skill")[:5]
        return (
                ", ".join(
                    f"{rs.skill.name} ({rs.get_proficiency_level_display()})"
                    for rs in skills
                )
                or "No skills"
        )

    display_skills.short_description = "Skills"


@admin.register(ResumeExperience)
class ResumeExperienceAdmin(admin.ModelAdmin):
    list_display = ("resume", "company", "role", "start_date", "end_date")
    search_fields = ("company", "role", "resume__title")
    list_filter = ("company", "start_date")


@admin.register(ResumeContact)
class ResumeContactAdmin(admin.ModelAdmin):
    list_display = ("resume", "type", "value")
    search_fields = ("value", "resume__title")
    list_filter = ("type",)


@admin.register(ResumeCertificate)
class ResumeCertificateAdmin(admin.ModelAdmin):
    list_display = (
        "resume",
        "name",
        "issuing_organization",
        "issue_date",
        "expiration_date",
        "credential_id",
        "credential_url",
    )
    search_fields = ("name", "issuing_organization", "credential_id")
    list_filter = ("issuing_organization", "issue_date")


@admin.register(ResumeLanguageCertificate)
class ResumeLanguageCertificateAdmin(admin.ModelAdmin):
    list_display = ("resume", "language", "level", "file")
    search_fields = ("language__name", "resume__title")
    list_filter = ("level", "language")