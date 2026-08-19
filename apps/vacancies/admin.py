import json
import logging

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.translation import gettext_lazy as _
from django_rq import enqueue

from apps.authentication.models import Company, Recruiter
from apps.matching.services.embedding_tasks import generate_vacancy_embedding_task
from .models.vacancy import (
    FavouriteVacancy,
    VacancySkill,
    Vacancy,
    VacancyView,
    VacancyLanguage,
)
from .serializers.vacancy import VacancySerializer


logger = logging.getLogger(__name__)


class VacancyTxtUploadForm(forms.Form):
    company = forms.ModelChoiceField(
        queryset=Company.objects.order_by("name"),
        label=_("Company"),
    )
    recruiter = forms.ModelChoiceField(
        queryset=Recruiter.objects.select_related("company").order_by("email"),
        label=_("Recruiter"),
    )
    vacancies_file = forms.FileField(
        label=_("Vacancies file"),
        help_text=_(
            "Upload a .txt file containing a JSON object or a JSON array of vacancy objects."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        company_id = None
        if self.is_bound:
            company_id = self.data.get("company")

        recruiter_queryset = Recruiter.objects.select_related("company").order_by("email")
        if company_id:
            recruiter_queryset = recruiter_queryset.filter(company_id=company_id)

        self.fields["recruiter"].queryset = recruiter_queryset

    def clean_vacancies_file(self):
        uploaded_file = self.cleaned_data["vacancies_file"]
        if not uploaded_file.name.lower().endswith(".txt"):
            raise forms.ValidationError(_("Only .txt files are supported."))
        return uploaded_file

    def clean(self):
        cleaned_data = super().clean()
        company = cleaned_data.get("company")
        recruiter = cleaned_data.get("recruiter")

        if company and recruiter and recruiter.company_id != company.id:
            raise forms.ValidationError(
                _("The selected recruiter is not associated with the selected company.")
            )

        return cleaned_data


@admin.register(VacancyLanguage)
class VacancyLanguageAdmin(admin.ModelAdmin):
    list_display = ("vacancy", "language", "level", "created_at")
    search_fields = ("vacancy__title", "language__name")
    list_filter = ("level", "language")
    autocomplete_fields = ["vacancy", "language"]


class VacancyViewAdmin(admin.ModelAdmin):
    list_display = (
        "vacancy",
        "candidate",
        "session_start",
        "session_end",
        "duration_seconds",
    )
    search_fields = (
        "vacancy__title",
        "candidate__candidateprofile__full_name",
        "candidate__email",
    )
    list_filter = ("session_start", "session_end")


admin.site.register(VacancyView, VacancyViewAdmin)


@admin.register(FavouriteVacancy)
class FavouriteVacancyAdmin(admin.ModelAdmin):
    list_display = ("candidate", "vacancy", "created_at")
    search_fields = ("candidate__email", "vacancy__title", "vacancy__company__name")
    list_filter = ("created_at",)


class VacancySkillInline(admin.TabularInline):
    model = VacancySkill
    extra = 1
    autocomplete_fields = ["skill"]
    fields = ["skill", "is_required", "proficiency_level", "minimum_years"]


@admin.register(VacancySkill)
class VacancySkillAdmin(admin.ModelAdmin):
    list_display = (
        "vacancy",
        "skill",
        "is_required",
        "minimum_years",
        "proficiency_level",
    )
    search_fields = ("vacancy__title", "skill__name")
    list_filter = ("is_required", "proficiency_level")


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    change_list_template = "admin/vacancies/vacancy_changelist.html"
    list_display = [
        "title",
        "company",
        "created_by",
        "employment_type",
        "get_salary_range",
        "get_required_skills",
        "is_active",
        "created_at",
    ]

    list_filter = [
        "employment_type",
        "is_active",
        "created_at",
        "company",
        "required_skills__category",
    ]

    search_fields = [
        "title",
        "about_us",
        "requirements",
        "responsibilities",
        "company__name",
        "required_skills__name",
    ]

    actions = ["export_json", "export_xlsx"]

    def _vacancy_rows(self, queryset):
        qs = queryset.prefetch_related("vacancyskill_set__skill", "vacancy_languages__language")
        rows = []
        for v in qs:
            skills = ", ".join(
                f"{vs.skill.name} ({'Req' if vs.is_required else 'Opt'})"
                for vs in v.vacancyskill_set.all()
            )
            languages = ", ".join(
                f"{vl.language.name} ({vl.level})"
                for vl in v.vacancy_languages.all()
            )
            salary = ""
            if v.salary_min and v.salary_max:
                salary = f"{v.salary_min} - {v.salary_max}"
            elif v.salary_min:
                salary = f"From {v.salary_min}"
            elif v.salary_max:
                salary = f"Up to {v.salary_max}"
            rows.append({
                "ID": str(v.id),
                "Title": v.title,
                "Company": v.company.name,
                "Created by": str(v.created_by),
                "Employment type": v.employment_type,
                "Salary": salary,
                "Location": v.location or "",
                "Experience (years)": v.experience or 0,
                "Format": v.employment_format or "",
                "Active": "Yes" if v.is_active else "No",
                "Skills": skills,
                "Languages": languages,
                "Created at": str(v.created_at),
            })
        return rows

    EXPORT_COLUMNS = [
        "ID", "Title", "Company", "Created by",
        "Employment type", "Salary", "Location", "Experience (years)",
        "Format", "Active", "Skills", "Languages", "Created at",
    ]

    def export_json(self, request, queryset):
        qs = queryset.prefetch_related("vacancyskill_set__skill", "vacancy_languages__language")
        data = VacancySerializer(qs, many=True).data
        response = HttpResponse(
            json.dumps(data, ensure_ascii=False, indent=2),
            content_type="application/json",
        )
        response["Content-Disposition"] = 'attachment; filename="vacancies.json"'
        return response
    export_json.short_description = _("Export selected as JSON")

    def export_xlsx(self, request, queryset):
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = "Vacancies"
        ws.append(self.EXPORT_COLUMNS)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in self._vacancy_rows(queryset):
            ws.append([row[h] for h in self.EXPORT_COLUMNS])
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="vacancies.xlsx"'
        wb.save(response)
        return response
    export_xlsx.short_description = _("Export selected as XLSX")



    inlines = [VacancySkillInline]
    date_hierarchy = "created_at"
    list_select_related = ["company", "created_by"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-txt/",
                self.admin_site.admin_view(self.import_txt_view),
                name="vacancies_vacancy_import_txt",
            ),
        ]
        return custom_urls + urls

    def import_txt_view(self, request):
        if request.method == "POST":
            form = VacancyTxtUploadForm(request.POST, request.FILES)
            if form.is_valid():
                company = form.cleaned_data["company"]
                recruiter = form.cleaned_data["recruiter"]
                uploaded_file = form.cleaned_data["vacancies_file"]

                try:
                    payloads = self._parse_uploaded_payloads(uploaded_file)
                    created_vacancies = self._import_vacancies(payloads, company, recruiter)
                except DjangoValidationError as exc:
                    form.add_error("vacancies_file", exc)
                except Exception as exc:
                    logger.exception("Vacancy admin import failed")
                    messages.error(
                        request,
                        _("Vacancy import failed: %(error)s") % {"error": str(exc)},
                    )
                    return redirect("..")
                else:
                    failed_enqueues = self._enqueue_embeddings(created_vacancies)
                    messages.success(
                        request,
                        _("Successfully imported %(count)s vacancies.")
                        % {"count": len(created_vacancies)},
                    )

                    if failed_enqueues:
                        messages.warning(
                            request,
                            _(
                                "Imported vacancies, but failed to enqueue embedding generation for %(count)s vacancies."
                            )
                            % {"count": len(failed_enqueues)},
                        )

                    return redirect("..")
        else:
            form = VacancyTxtUploadForm()

        context = {
            **self.admin_site.each_context(request),
            "form": form,
            "title": _("Import vacancies from TXT"),
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request,
            "admin/vacancies/import_txt.html",
            context,
        )

    def _parse_uploaded_payloads(self, uploaded_file):
        try:
            content = uploaded_file.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DjangoValidationError(
                _("The uploaded file must be UTF-8 encoded text.")
            ) from exc

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise DjangoValidationError(
                _("Invalid JSON in uploaded file: %(error)s") % {"error": exc.msg}
            ) from exc

        if isinstance(payload, dict):
            payloads = [payload]
        elif isinstance(payload, list):
            payloads = payload
        else:
            raise DjangoValidationError(
                _("The uploaded file must contain a JSON object or an array of objects.")
            )

        if not payloads:
            raise DjangoValidationError(_("The uploaded file does not contain any vacancies."))

        for index, item in enumerate(payloads, start=1):
            if not isinstance(item, dict):
                raise DjangoValidationError(
                    _("Vacancy entry %(index)s must be a JSON object.")
                    % {"index": index}
                )

        return payloads

    def _import_vacancies(self, payloads, company, recruiter):
        created_vacancies = []

        with transaction.atomic():
            for index, payload in enumerate(payloads, start=1):
                self._validate_import_payload(payload, index)

                serializer = VacancySerializer(data=payload)
                try:
                    serializer.is_valid(raise_exception=True)
                    vacancy = serializer.save(created_by=recruiter, company=company)
                except IntegrityError as exc:
                    raise DjangoValidationError(
                        _("Vacancy %(index)s could not be saved: %(error)s")
                        % {"index": index, "error": str(exc)}
                    ) from exc
                except Exception as exc:
                    title = payload.get("title") or _("Untitled vacancy")
                    raise DjangoValidationError(
                        _("Vacancy %(index)s (%(title)s) is invalid: %(error)s")
                        % {"index": index, "title": title, "error": exc}
                    ) from exc

                created_vacancies.append(vacancy)

        return created_vacancies

    def _validate_import_payload(self, payload, index):
        duplicate_skill_ids = self._get_duplicate_ids(payload.get("skills_data", []), "skill_id")
        if duplicate_skill_ids:
            raise DjangoValidationError(
                _("Vacancy %(index)s contains duplicate skill IDs: %(ids)s")
                % {"index": index, "ids": ", ".join(str(value) for value in duplicate_skill_ids)}
            )

        duplicate_language_ids = self._get_duplicate_ids(
            payload.get("languages_data", []),
            "language_id",
        )
        if duplicate_language_ids:
            raise DjangoValidationError(
                _("Vacancy %(index)s contains duplicate language IDs: %(ids)s")
                % {"index": index, "ids": ", ".join(str(value) for value in duplicate_language_ids)}
            )

    @staticmethod
    def _get_duplicate_ids(items, field_name):
        seen_values = set()
        duplicate_values = []

        for item in items:
            if not isinstance(item, dict):
                continue

            value = item.get(field_name)
            if value in seen_values and value not in duplicate_values:
                duplicate_values.append(value)
            seen_values.add(value)

        return duplicate_values

    def _enqueue_embeddings(self, vacancies):
        failed_vacancy_ids = []

        for vacancy in vacancies:
            try:
                enqueue(generate_vacancy_embedding_task, vacancy.id)
            except Exception:
                logger.exception(
                    "Failed to enqueue vacancy embedding task for vacancy %s",
                    vacancy.id,
                )
                failed_vacancy_ids.append(vacancy.id)

        return failed_vacancy_ids

    def get_required_skills(self, obj):
        vacancy_skills = obj.vacancyskill_set.all()[:5]
        skills_info = []

        for vs in vacancy_skills:
            requirement_type = "Required" if vs.is_required else "Optional"
            level = vs.get_proficiency_level_display()
            skills_info.append(f"{vs.skill.name} ({level}, {requirement_type})")

        return ", ".join(skills_info) if skills_info else "No skills specified"

    get_required_skills.short_description = "Required Skills"

    def get_salary_range(self, obj):
        if obj.salary_min and obj.salary_max:
            return f"${obj.salary_min:,.0f} - ${obj.salary_max:,.0f}"
        if obj.salary_min:
            return f"From ${obj.salary_min:,.0f}"
        if obj.salary_max:
            return f"Up to ${obj.salary_max:,.0f}"
        return "Not specified"

    get_salary_range.short_description = "Salary Range"
