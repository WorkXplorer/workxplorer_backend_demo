import logging
import random
from django.db import models
from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import BannerSlide, BannerClick
from apps.subscriptions.models import CompanySubscription
from apps.vacancies.models import Vacancy
from apps.applications.models import JobApplication

logger = logging.getLogger(__name__)

# Max partner vacancies shown per company in the auto section
MAX_VACANCIES_PER_PARTNER = 2


def _build_vacancy_slide(vacancy, request, is_favourite=False, duration=3,
                         total_vacancies=None, applications_count=None):
    """Convert a Vacancy ORM object into the unified slide dict."""
    profile = None
    try:
        profiles = vacancy.company.companyprofile.all()
        profile = profiles[0] if profiles else None
    except (AttributeError, IndexError, TypeError):
        profile = None

    logo_url = None
    if profile and profile.photo:
        try:
            logo_url = request.build_absolute_uri(profile.photo.url)
        except Exception:
            logo_url = profile.photo.url

    font_url = None
    if profile and profile.brand_font_file:
        try:
            font_url = request.build_absolute_uri(profile.brand_font_file.url)
        except Exception:
            font_url = profile.brand_font_file.url

    name_image_url = None
    if profile and profile.brand_name_image:
        try:
            name_image_url = request.build_absolute_uri(profile.brand_name_image.url)
        except Exception:
            name_image_url = profile.brand_name_image.url

    if total_vacancies is None:
        total_vacancies = Vacancy.objects.filter(company=vacancy.company, is_active=True).count()
    if applications_count is None:
        applications_count = vacancy.applications.count()

    return {
        "slide_type": "PARTNER_VACANCY",
        "duration": duration,
        "brand_color_from": profile.brand_color_from or "" if profile else "",
        "brand_color_to": profile.brand_color_to or "" if profile else "",
        "brand_accent_color": profile.brand_accent_color or "" if profile else "",
        "brand_text_color": profile.brand_text_color or "" if profile else "",
        "brand_border_color": profile.brand_border_color or "" if profile else "",
        "brand_dark_color": profile.brand_dark_color if profile else None,
        "brand_button_text_color": profile.brand_button_text_color if profile else None,
        "vacancy_id": str(vacancy.id),
        "title": vacancy.title,
        "company_name": vacancy.company.name if vacancy.company else "",
        "company_logo_url": logo_url,
        "company_tagline": profile.tagline if profile else None,
        "company_font": profile.brand_font if profile else None,
        "company_font_url": font_url,
        "company_name_image_url": name_image_url,
        "company_total_vacancies": total_vacancies if total_vacancies is not None else 0,
        "salary_min": str(vacancy.salary_min or ""),
        "salary_max": str(vacancy.salary_max or ""),
        "salary_currency": vacancy.salary_currency or "",
        "location": vacancy.location or "",
        "employment_type_display": vacancy.get_employment_type_display(),
        "employment_format_display": vacancy.get_employment_format_display(),
        "responsibilities": vacancy.responsibilities or "",
        "requirements": vacancy.requirements or "",
        "applications_count": applications_count,
        "created_at": vacancy.created_at.isoformat() if vacancy.created_at else None,
        "is_favourite": is_favourite,
        "headline": "",
        "body": "",
        "image_url": None,
        "image_desktop_url": None,
        "image_mobile_url": None,
        "cta_label": "",
        "cta_url": "",
        "html_content": "",
    }


def _build_manual_slide(slide, request, locale="ru",
                        company_vacancy_counts=None, vacancy_app_counts=None):
    """Convert a BannerSlide model into the unified slide dict."""
    if company_vacancy_counts is None:
        company_vacancy_counts = {}
    if vacancy_app_counts is None:
        vacancy_app_counts = {}

    def _absolute_url(field):
        if not field:
            return None
        try:
            return request.build_absolute_uri(field.url)
        except Exception:
            return field.url

    if slide.slide_type == BannerSlide.SlideType.VACANCY and slide.vacancy:
        v = slide.vacancy
        return _build_vacancy_slide(
            v, request, duration=slide.duration,
            total_vacancies=company_vacancy_counts.get(v.company_id, 0),
            applications_count=vacancy_app_counts.get(v.id, 0),
        )

    locale_html_file = {
        "uz": slide.html_file_uz or slide.html_file,
        "ru": slide.html_file_ru or slide.html_file,
        "en": slide.html_file_en or slide.html_file,
    }
    html_file = locale_html_file.get(locale, slide.html_file)

    return {
        "slide_type": slide.slide_type,
        "duration": slide.duration,
        "brand_color_from": slide.brand_color_from,
        "brand_color_to": slide.brand_color_to,
        "brand_accent_color": slide.brand_accent_color,
        "brand_text_color": slide.brand_text_color,
        "brand_border_color": slide.brand_border_color,
        "brand_dark_color": None,
        "brand_button_text_color": None,
        "vacancy_id": None,
        "title": "",
        "company_name": "",
        "company_logo_url": None,
        "company_tagline": None,
        "company_font": None,
        "company_font_url": None,
        "company_name_image_url": None,
        "company_total_vacancies": None,
        "salary_min": "",
        "salary_max": "",
        "salary_currency": "",
        "location": "",
        "employment_type_display": "",
        "employment_format_display": "",
        "responsibilities": "",
        "requirements": "",
        "applications_count": None,
        "created_at": None,
        "is_favourite": None,
        "headline": slide.title,
        "body": slide.body,
        "image_url": _absolute_url(slide.image),
        "image_desktop_url": _absolute_url(slide.image_desktop),
        "image_mobile_url": _absolute_url(slide.image_mobile),
        "image_desktop_uz_url": _absolute_url(slide.image_desktop_uz),
        "image_desktop_ru_url": _absolute_url(slide.image_desktop_ru),
        "image_desktop_en_url": _absolute_url(slide.image_desktop_en),
        "image_mobile_uz_url": _absolute_url(slide.image_mobile_uz),
        "image_mobile_ru_url": _absolute_url(slide.image_mobile_ru),
        "image_mobile_en_url": _absolute_url(slide.image_mobile_en),
        "cta_label": slide.cta_label,
        "cta_url": slide.cta_url,
        "html_file_url": _absolute_url(html_file),
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def banner_list_view(request):
    """
    Returns an ordered list of banner slides for the vacancies page carousel.

    Composition:
      1. Auto partner-vacancy slides (shuffled per request).
      2. Manual BannerSlide rows placed at their `order` position.

    A manual slide with order=k lands at index k in the combined list
    (e.g. order=2 means "after the first two vacancy slides"). Out-of-range
    orders fall to the end. Manual slides sharing the same order keep their
    queryset order. Built in a single O(n+m) pass over both lists.
    """
    now = timezone.now()

    # 1. Manual slides (sorted by order, then created_at)
    manual_qs = BannerSlide.objects.filter(
        is_active=True,
    ).filter(
        models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now),
    ).filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=now),
    ).order_by("order", "created_at")

    locale = request.query_params.get("locale", "ru")

    # Evaluate queryset once; pull FK values without extra DB hits
    manual_qs_list = list(manual_qs)
    manual_vacancy_ids = [
        s.vacancy_id for s in manual_qs_list
        if s.slide_type == BannerSlide.SlideType.VACANCY and s.vacancy_id
    ]
    if manual_vacancy_ids:
        company_ids = list(
            Vacancy.objects.filter(id__in=manual_vacancy_ids)
            .values_list('company_id', flat=True).distinct()
        )
        company_total_vacancies = dict(
            Vacancy.objects.filter(company_id__in=company_ids, is_active=True)
            .values('company_id').annotate(total=Count('id'))
            .values_list('company_id', 'total')
        )
        vacancy_app_counts = dict(
            JobApplication.objects.filter(vacancy_id__in=manual_vacancy_ids)
            .values('vacancy_id').annotate(total=Count('id'))
            .values_list('vacancy_id', 'total')
        )
    else:
        company_total_vacancies = {}
        vacancy_app_counts = {}

    manual_slides = [
        (s.order, _build_manual_slide(
            s, request, locale=locale,
            company_vacancy_counts=company_total_vacancies,
            vacancy_app_counts=vacancy_app_counts,
        ))
        for s in manual_qs_list
    ]

    # 2. Auto partner vacancy slides
    active_design_subs = CompanySubscription.objects.filter(
        status=CompanySubscription.Status.ACTIVE,
        has_design=True,
    ).filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=now),
    ).select_related("company")

    # Collect favourite vacancy IDs for the current user (candidates only)
    favourite_ids = set()
    if (
        request.user.is_authenticated
        and hasattr(request.user, "is_candidate")
        and request.user.is_candidate
    ):
        try:
            from apps.vacancies.models import FavouriteVacancy
            favourite_ids = set(
                FavouriteVacancy.objects.filter(
                    candidate=request.user.candidate
                ).values_list("vacancy_id", flat=True)
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load favourite vacancy IDs: %s", exc)

    companies = list({sub.company for sub in active_design_subs})
    company_ids = [c.id for c in companies]

    vacancy_slides = []
    if company_ids:
        all_partner_vacancies = list(
            Vacancy.objects.filter(company_id__in=company_ids, is_active=True)
            .select_related("company")
            .prefetch_related("company__companyprofile")
            .annotate(applications_total=Count("applications", distinct=True))
        )
        random.shuffle(all_partner_vacancies)

        # ponytail: derive counts from the single query instead of a second DB hit
        company_vacancy_counts = {}
        for v in all_partner_vacancies:
            company_vacancy_counts[v.company_id] = company_vacancy_counts.get(v.company_id, 0) + 1

        seen: dict[int, int] = {}
        for v in all_partner_vacancies:
            cid = v.company_id
            if seen.get(cid, 0) >= MAX_VACANCIES_PER_PARTNER:
                continue
            seen[cid] = seen.get(cid, 0) + 1
            vacancy_slides.append(
                _build_vacancy_slide(
                    v, request,
                    is_favourite=v.id in favourite_ids,
                    total_vacancies=company_vacancy_counts.get(cid),
                    applications_count=v.applications_total,
                )
            )

    # Single-pass merge. manual_slides is already sorted by order ascending,
    # so walk both lists once: emit a manual slide as soon as the output has
    # reached its target position, otherwise emit the next vacancy slide.
    # Leftover manuals (order beyond the list length) append at the end.
    slides = []
    vi = mi = 0
    while vi < len(vacancy_slides) or mi < len(manual_slides):
        if mi < len(manual_slides) and manual_slides[mi][0] <= len(slides):
            slides.append(manual_slides[mi][1])
            mi += 1
        elif vi < len(vacancy_slides):
            slides.append(vacancy_slides[vi])
            vi += 1
        else:
            slides.append(manual_slides[mi][1])
            mi += 1

    return Response(slides)


@api_view(["POST"])
@permission_classes([AllowAny])
def banner_click_view(request):
    """Records a banner click. User is captured if authenticated."""
    slide_type = request.data.get("slide_type", "")
    vacancy_id = request.data.get("vacancy_id") or None
    cta_url = request.data.get("cta_url", "")
    anon_id = request.data.get("anon_id", "")

    BannerClick.objects.create(
        user=request.user if request.user.is_authenticated else None,
        slide_type=slide_type,
        vacancy_id=vacancy_id,
        cta_url=cta_url,
        anon_id=anon_id,
    )
    return HttpResponse(status=204)
