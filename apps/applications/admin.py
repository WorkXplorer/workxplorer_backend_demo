# apps/applications/admin.py
import csv
import logging
from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponse
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    JobApplication,
    ApplicationDocument,
    ApplicationStatus,
    ApplicationAIEvaluation,
    EvaluationStatus,
)

logger = logging.getLogger(__name__)


def _reevaluate_ai_evaluations(request, modeladmin, evaluations):
    """Reset the given ApplicationAIEvaluation rows to PENDING and re-enqueue
    process_candidate_ai_evaluation, mirroring reevaluate_failed_applications."""
    from apps.general.models import JobQueue
    from apps.applications.tasks import process_candidate_ai_evaluation
    import django_rq

    reevaluated = 0
    failed = 0

    for evaluation in evaluations:
        try:
            with transaction.atomic():
                evaluation.status = EvaluationStatus.PENDING
                evaluation.error_message = None
                evaluation.save(update_fields=["status", "error_message", "updated_at"])

                if evaluation.job_queue_id:
                    JobQueue.objects.filter(id=evaluation.job_queue_id).update(
                        status=JobQueue.JobStatus.PENDING,
                        retry_count=0,
                        error_message=None,
                    )
                    job_queue_id = str(evaluation.job_queue_id)
                else:
                    job_queue_id = None

            queue = django_rq.get_queue("default")
            queue.enqueue(
                process_candidate_ai_evaluation,
                application_id=str(evaluation.application_id),
                job_queue_id=job_queue_id,
                retry_attempt=0,
                job_timeout=300,
            )
            reevaluated += 1
        except Exception:
            logger.exception(
                "admin reevaluate: failed to re-enqueue evaluation %s", evaluation.pk
            )
            failed += 1

    if reevaluated:
        modeladmin.message_user(request, f"{reevaluated} evaluation(s) re-enqueued for AI re-evaluation.")
    if failed:
        modeladmin.message_user(
            request, f"{failed} evaluation(s) failed to re-enqueue. Check server logs.", level=messages.ERROR
        )


class ApplicationDocumentInline(admin.TabularInline):
    model = ApplicationDocument
    extra = 0
    readonly_fields = ["created_at", "file_size", "file_size_display"]
    fields = ["document_type", "title", "file", "file_size_display", "created_at"]

    def file_size_display(self, obj):
        if not obj.file_size:
            return "Unknown"
        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    file_size_display.short_description = "File Size"


class AIEvaluationInline(admin.StackedInline):
    model = ApplicationAIEvaluation
    extra = 0
    readonly_fields = ["status", "overall_score", "evaluated_at", "error_message", "job_queue_id", "result"]
    fields = ["status", "overall_score", "evaluated_at", "error_message", "job_queue_id", "result"]
    can_delete = False


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = [
        "candidate_name",
        "candidate_phone",
        "candidate_university",
        "vacancy_title",
        "company_name",
        "status_badge",
        "applied_at",
        "days_since_application",
        "is_active",
    ]

    list_filter = [
        "status",
        "applied_at",
        "is_active",
        "candidate__edupartner",
        "vacancy__company",
        "vacancy__employment_type",
        ("applied_at", admin.DateFieldListFilter),
    ]

    search_fields = [
        "candidate__email",
        "candidate__edupartner__name",
        "vacancy__title",
        "vacancy__company__name",
        "recruiter_notes",
    ]

    readonly_fields = [
        "id",
        "applied_at",
        "updated_at",
        "days_since_application",
        "is_recent",
        "can_withdraw",
    ]

    fieldsets = (
        (
            "Application Details",
            {
                "fields": (
                    "id",
                    "candidate",
                    "vacancy",
                    "status",
                    "applied_at",
                    "updated_at",
                )
            },
        ),
        (
            "Application Content",
            {
                "fields": (
                    "resume_used",
                    "cover_letter",
                    "portfolio_url",
                    "earliest_start_date",
                )
            },
        ),
        (
            "Internal Management",
            {
                "fields": (
                    "recruiter_notes",
                    "last_updated_by",
                    "is_active",
                    "additional_documents",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Computed Fields",
            {
                "fields": ("days_since_application", "is_recent", "can_withdraw"),
                "classes": ("collapse",),
            },
        ),
    )

    inlines = [ApplicationDocumentInline, AIEvaluationInline]

    date_hierarchy = "applied_at"
    ordering = ["-applied_at"]

    actions = [
        "export_as_csv",
        "mark_applied",
        "mark_interviewed",
        "mark_rejected",
        "mark_offered",
        "mark_active",
        "mark_inactive",
        "reevaluate_ai",
    ]

    def candidate_name(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:authentication_candidate_change", args=[obj.candidate.pk]),
            obj.candidate.email,
        )

    candidate_name.short_description = "Candidate"
    candidate_name.admin_order_field = "candidate__email"

    def candidate_phone(self, obj):
        try:
            return obj.candidate.candidateprofile.phone or "—"
        except Exception:
            return "—"

    candidate_phone.short_description = "Phone"

    def candidate_university(self, obj):
        return obj.candidate.edupartner.name if obj.candidate.edupartner_id else "—"

    candidate_university.short_description = "University"
    candidate_university.admin_order_field = "candidate__edupartner__name"

    def vacancy_title(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:vacancies_vacancy_change", args=[obj.vacancy.pk]),
            obj.vacancy.title,
        )

    vacancy_title.short_description = "Vacancy"
    vacancy_title.admin_order_field = "vacancy__title"

    def company_name(self, obj):
        return obj.vacancy.company.name

    company_name.short_description = "Company"
    company_name.admin_order_field = "vacancy__company__name"

    def status_badge(self, obj):
        colors = {
            ApplicationStatus.APPLIED: "#17a2b8",
            ApplicationStatus.INTERVIEW_SCHEDULED: "#fd7e14",
            ApplicationStatus.INTERVIEWED: "#6f42c1",
            ApplicationStatus.OFFERED: "#28a745",
            ApplicationStatus.OFFER_ACCEPTED: "#198754",
            ApplicationStatus.OFFER_REJECTED: "#ff69b4",
            ApplicationStatus.REJECTED: "#dc3545",
            ApplicationStatus.WITHDRAWN: "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def days_since_application(self, obj):
        days = obj.days_since_application
        if days <= 7:
            color = "#28a745"
        elif days <= 30:
            color = "#ffc107"
        else:
            color = "#dc3545"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} days</span>', color, days
        )

    days_since_application.short_description = "Days Since Applied"

    def can_withdraw(self, obj):
        if obj is None:
            return None
        return obj.can_be_withdrawn()

    can_withdraw.short_description = "Can Withdraw"
    can_withdraw.boolean = True

    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="job_applications.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "ID", "Candidate Email", "Candidate Phone", "University",
            "Vacancy", "Company", "Status",
            "Applied At", "Updated At", "Days Since Applied",
            "Cover Letter", "Portfolio URL", "Earliest Start Date",
            "Recruiter Notes", "Is Active",
        ])
        for obj in queryset.select_related(
            "candidate", "candidate__candidateprofile", "candidate__edupartner",
            "vacancy", "vacancy__company",
        ):
            try:
                phone = obj.candidate.candidateprofile.phone or ""
            except Exception:
                phone = ""
            writer.writerow([
                obj.id,
                obj.candidate.email,
                phone,
                obj.candidate.edupartner.name if obj.candidate.edupartner_id else "",
                obj.vacancy.title,
                obj.vacancy.company.name,
                obj.get_status_display(),
                obj.applied_at.strftime("%Y-%m-%d %H:%M:%S"),
                obj.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                obj.days_since_application,
                obj.cover_letter or "",
                obj.portfolio_url or "",
                obj.earliest_start_date or "",
                obj.recruiter_notes or "",
                obj.is_active,
            ])
        return response

    export_as_csv.short_description = "Export selected as CSV"

    def mark_applied(self, request, queryset):
        updated = queryset.update(status=ApplicationStatus.APPLIED, updated_at=timezone.now())
        self.message_user(request, f"{updated} applications marked as applied.")

    mark_applied.short_description = "Mark as Applied"

    def mark_interviewed(self, request, queryset):
        updated = queryset.update(status=ApplicationStatus.INTERVIEWED, updated_at=timezone.now())
        self.message_user(request, f"{updated} applications marked as interviewed.")

    mark_interviewed.short_description = "Mark as Interviewed"

    def mark_rejected(self, request, queryset):
        updated = queryset.update(status=ApplicationStatus.REJECTED, updated_at=timezone.now())
        self.message_user(request, f"{updated} applications marked as rejected.")

    mark_rejected.short_description = "Mark as Rejected"

    def mark_offered(self, request, queryset):
        updated = queryset.update(status=ApplicationStatus.OFFERED, updated_at=timezone.now())
        self.message_user(request, f"{updated} applications marked as offered.")

    mark_offered.short_description = "Mark as Offered"

    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} applications marked as active.")

    mark_active.short_description = "Mark as Active"

    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} applications marked as inactive.")

    mark_inactive.short_description = "Mark as Inactive"

    def reevaluate_ai(self, request, queryset):
        evaluations = ApplicationAIEvaluation.objects.filter(
            application__in=queryset
        ).select_related("application")
        missing = queryset.exclude(
            id__in=evaluations.values_list("application_id", flat=True)
        ).count()
        if missing:
            self.message_user(
                request,
                f"{missing} selected application(s) have no AI evaluation record and were skipped.",
                level=messages.WARNING,
            )
        _reevaluate_ai_evaluations(request, self, evaluations)

    reevaluate_ai.short_description = "Reevaluate AI evaluation (reset & re-run)"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "candidate", "candidate__candidateprofile", "candidate__edupartner",
            "vacancy", "vacancy__company", "resume_used", "last_updated_by",
        ).prefetch_related("documents")


@admin.register(ApplicationDocument)
class ApplicationDocumentAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "document_type",
        "application_link",
        "candidate_name",
        "file_size_display",
        "created_at",
    ]

    list_filter = [
        "document_type",
        "created_at",
        ("created_at", admin.DateFieldListFilter),
    ]

    search_fields = [
        "title",
        "application__candidate__email",
        "application__vacancy__title",
    ]

    readonly_fields = ["id", "created_at", "file_size", "file_size_display"]

    fieldsets = (
        (
            "Document Details",
            {"fields": ("id", "application", "document_type", "title")},
        ),
        (
            "File Information",
            {"fields": ("file", "file_size", "file_size_display", "created_at")},
        ),
    )

    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    def created_at_display(self, obj):
        return obj.created_at

    created_at_display.short_description = "Uploaded at"

    def application_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:applications_jobapplication_change", args=[obj.application.pk]),
            f"{obj.application.candidate} → {obj.application.vacancy.title}",
        )

    application_link.short_description = "Application"
    application_link.admin_order_field = "application"

    def candidate_name(self, obj):
        return obj.application.candidate.email

    candidate_name.short_description = "Candidate"
    candidate_name.admin_order_field = "application__candidate__email"

    def file_size_display(self, obj):
        if not obj.file_size:
            return "Unknown"
        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    file_size_display.short_description = "File Size"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "application", "application__candidate", "application__vacancy"
        )


@admin.register(ApplicationAIEvaluation)
class ApplicationAIEvaluationAdmin(admin.ModelAdmin):
    list_display = [
        "application",
        "status",
        "overall_score",
        "detected_language",
        "input_tokens",
        "output_tokens",
        "thinking_tokens",
        "evaluated_at",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = [
        "application__candidate__email",
        "application__vacancy__title",
    ]
    actions = ["reevaluate_ai"]
    readonly_fields = [
        "id",
        "application",
        "status",
        "overall_score",
        "result",
        "detected_language",
        "input_tokens",
        "output_tokens",
        "thinking_tokens",
        "job_queue_id",
        "error_message",
        "evaluated_at",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    def reevaluate_ai(self, request, queryset):
        _reevaluate_ai_evaluations(request, self, queryset)

    reevaluate_ai.short_description = "Reevaluate AI evaluation (reset & re-run)"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "application",
            "application__candidate",
            "application__vacancy",
        )
