"""
Hardcoded demo data for unapproved companies.

All demo API responses are served directly from these constants — zero DB queries.
The frontend receives is_demo=True in the response and knows not to navigate to
individual records (they have no real DB rows behind them).
"""

DEMO_COMPANY_NAME = "WorkXplorer Demo"

# Stable fake UUIDs — no real DB rows exist for these
_V1 = "d0000001-0000-0000-0000-000000000000"
_V2 = "d0000002-0000-0000-0000-000000000000"
_V3 = "d0000003-0000-0000-0000-000000000000"
_V4 = "d0000004-0000-0000-0000-000000000000"

_A1  = "a0000001-0000-0000-0000-000000000000"
_A2  = "a0000002-0000-0000-0000-000000000000"
_A3  = "a0000003-0000-0000-0000-000000000000"
_A4  = "a0000004-0000-0000-0000-000000000000"
_A5  = "a0000005-0000-0000-0000-000000000000"
_A6  = "a0000006-0000-0000-0000-000000000000"
_A7  = "a0000007-0000-0000-0000-000000000000"
_A8  = "a0000008-0000-0000-0000-000000000000"
_A9  = "a0000009-0000-0000-0000-000000000000"
_A10 = "a0000010-0000-0000-0000-000000000000"
_A11 = "a0000011-0000-0000-0000-000000000000"
_A12 = "a0000012-0000-0000-0000-000000000000"

_DEMO_AI_EVALUATION = {
    "status": "COMPLETED",
    "overall_score": 74.0,
    "average_rating": 7.0,
    "recommendation": "RECOMMENDED",
}

_VACANCIES_RAW = [
    {
        "id": _V1,
        "title": "Python Backend Developer",
        "employment_type": "FULL_TIME",
        "employment_type_display": "Full-time",
        "employment_format": "HYBRID",
        "employment_format_display": "Hybrid",
        "salary_min": "5000000.00",
        "salary_max": "12000000.00",
        "salary_currency": "UZS",
        "salary_currency_display": "UZS",
        "experience": 2,
        "about_us": {
            "uz": "Biz innovatsion raqamli mahsulotlar yaratayotgan tez rivojlanayotgan texnologiya kompaniyamiz.",
            "ru": "Мы быстрорастущая технологическая компания, создающая инновационные цифровые продукты.",
            "en": "We are a fast-growing tech company building innovative digital products.",
        },
        "requirements": {
            "uz": "3+ yil Python tajribasi, Django REST Framework, PostgreSQL.",
            "ru": "3+ года опыта Python, Django REST Framework, PostgreSQL.",
            "en": "3+ years of Python experience, Django REST Framework, PostgreSQL.",
        },
        "responsibilities": {
            "uz": "Backend API'larni ishlab chiqish va qo'llab-quvvatlash, unit testlar yozish, frontend jamoa bilan hamkorlik qilish.",
            "ru": "Разработка и поддержка backend API, написание модульных тестов, взаимодействие с frontend командой.",
            "en": "Develop and maintain backend APIs, write unit tests, collaborate with frontend team.",
        },
        "applications_count": 3,
        "applied_applications_count": 1,
    },
    {
        "id": _V2,
        "title": "Frontend React Developer",
        "employment_type": "FULL_TIME",
        "employment_type_display": "Full-time",
        "employment_format": "REMOTE",
        "employment_format_display": "Remote",
        "salary_min": "4000000.00",
        "salary_max": "10000000.00",
        "salary_currency": "UZS",
        "salary_currency_display": "UZS",
        "experience": 1,
        "about_us": {
            "uz": "Foydalanuvchi tajribasiga e'tibor qaratadigan mahsulot jamoasi.",
            "ru": "Продуктовая команда, ориентированная на отличный пользовательский опыт.",
            "en": "A product team focused on great user experiences.",
        },
        "requirements": {
            "uz": "React, TypeScript, REST API integratsiya tajribasi.",
            "ru": "React, TypeScript, опыт интеграции REST API.",
            "en": "React, TypeScript, REST API integration experience.",
        },
        "responsibilities": {
            "uz": "Responsive UI komponentlar yaratish, dizayn tizimini qo'llab-quvvatlash, dizayn jamoasi bilan hamkorlik.",
            "ru": "Создание адаптивных UI компонентов, поддержка дизайн-системы, координация с командой дизайна.",
            "en": "Build responsive UI components, maintain design system, coordinate with design team.",
        },
        "applications_count": 3,
        "applied_applications_count": 1,
    },
    {
        "id": _V3,
        "title": "UX/UI Designer",
        "employment_type": "FULL_TIME",
        "employment_type_display": "Full-time",
        "employment_format": "ON_SITE",
        "employment_format_display": "On-site",
        "salary_min": "3500000.00",
        "salary_max": "8000000.00",
        "salary_currency": "UZS",
        "salary_currency_display": "UZS",
        "experience": 1,
        "about_us": {
            "uz": "Biz yaratgan har bir mahsulotda foydalanuvchiga yo'naltirilgan dizaynni qadrlaymiz.",
            "ru": "Мы ценим пользовательский дизайн в каждом создаваемом продукте.",
            "en": "We value user-centred design in every product we build.",
        },
        "requirements": {
            "uz": "Figma, foydalanuvchi tadqiqotlari, prototiplash, dizayn tizimlari.",
            "ru": "Figma, исследование пользователей, прототипирование, дизайн-системы.",
            "en": "Figma, user research, prototyping, design systems.",
        },
        "responsibilities": {
            "uz": "Wireframe va prototiplarni loyihalash, foydalanuvchanlik testlarini o'tkazish, fikr-mulohazalar asosida takrorlash.",
            "ru": "Проектирование макетов и прототипов, проведение юзабилити-тестов, итерация на основе обратной связи.",
            "en": "Design wireframes and prototypes, conduct usability tests, iterate on feedback.",
        },
        "applications_count": 2,
        "applied_applications_count": 1,
    },
    {
        "id": _V4,
        "title": "DevOps Engineer",
        "employment_type": "FULL_TIME",
        "employment_type_display": "Full-time",
        "employment_format": "HYBRID",
        "employment_format_display": "Hybrid",
        "salary_min": "6000000.00",
        "salary_max": "15000000.00",
        "salary_currency": "UZS",
        "salary_currency_display": "UZS",
        "experience": 3,
        "about_us": {
            "uz": "Ishonchlilik va miqyoslanishni ta'minlovchi infratuzilma jamoasi.",
            "ru": "Команда инфраструктуры, обеспечивающая надёжность и масштабируемость.",
            "en": "Infrastructure team ensuring reliability and scalability.",
        },
        "requirements": {
            "uz": "Docker, Kubernetes, CI/CD pipeline'lar, Linux tizim boshqaruvi.",
            "ru": "Docker, Kubernetes, CI/CD пайплайны, администрирование Linux.",
            "en": "Docker, Kubernetes, CI/CD pipelines, Linux system administration.",
        },
        "responsibilities": {
            "uz": "Bulutli infratuzilmani boshqarish, deploy pipeline'larni yaratish, tizim holatini monitoring qilish.",
            "ru": "Управление облачной инфраструктурой, создание пайплайнов развёртывания, мониторинг состояния систем.",
            "en": "Manage cloud infrastructure, build deployment pipelines, monitor system health.",
        },
        "applications_count": 4,
        "applied_applications_count": 1,
    },
]

_COMMON_VACANCY_FIELDS = {
    "address": None, "latitude": None, "longitude": None,
    "is_active": True, "is_demo": True,
    "created_by": None,
    "company_id": None,
    "company_name": DEMO_COMPANY_NAME,
    "company_is_active": False,
    "recruiter_email": "demo-system@workxplorer.demo",
    "domain": None, "domain_name": None,
    "application_status": None,
    "is_favourite": False, "skill_match": None,
    "contact_email": None, "contact_phone": None,
    "number_of_positions": None, "minimum_ai_score": None,
    "additional_info": None, "expire": None,
    "vacancy_skills": [], "skills_data": {},
    "vacancy_languages": [], "languages_data": {},
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z",
    "similarity_score": None,
    "company_logo_url": None, "company_tagline": None,
    "company_total_vacancies": 4, "company_font": None,
    "brand_color_from": None, "brand_color_to": None,
    "brand_accent_color": None, "brand_text_color": None,
    "brand_border_color": None, "brand_page_type": None,
    "company_employees_count": None, "company_locations_count": None,
    "company_founded_year": None, "company_rating": None,
    "company_reviews_count": 0,
}

_TRANSLATABLE_FIELDS = ("about_us", "requirements", "responsibilities")


def _resolve_lang(value, language):
    if isinstance(value, dict):
        return value.get(language) or value.get("en", "")
    return value


def get_demo_vacancies(language: str = "en") -> list[dict]:
    result = []
    for v in _VACANCIES_RAW:
        entry = {**_COMMON_VACANCY_FIELDS, **v}
        for field in _TRANSLATABLE_FIELDS:
            entry[field] = _resolve_lang(entry.get(field), language)
        result.append(entry)
    return result


DEMO_VACANCIES = get_demo_vacancies("en")

# ---------------------------------------------------------------------------
# Candidates list (CompanyCandidatesListView)
# ---------------------------------------------------------------------------

_CANDIDATES = [
    ("Alibek Toshmatov",   "demo-candidate-1@workxplorer.demo"),
    ("Mohira Yusupova",    "demo-candidate-2@workxplorer.demo"),
    ("Jasur Karimov",      "demo-candidate-3@workxplorer.demo"),
    ("Nilufar Rahimova",   "demo-candidate-4@workxplorer.demo"),
    ("Bobur Ergashev",     "demo-candidate-5@workxplorer.demo"),
    ("Sarvinoz Mirzayeva", "demo-candidate-6@workxplorer.demo"),
    ("Doniyor Nazarov",    "demo-candidate-7@workxplorer.demo"),
    ("Zulfiya Khasanova",  "demo-candidate-8@workxplorer.demo"),
]

_RESUME_IDS = [
    "f0000001-0000-0000-0000-000000000000",
    "f0000002-0000-0000-0000-000000000000",
    "f0000003-0000-0000-0000-000000000000",
    "f0000004-0000-0000-0000-000000000000",
    "f0000005-0000-0000-0000-000000000000",
    "f0000006-0000-0000-0000-000000000000",
    "f0000007-0000-0000-0000-000000000000",
    "f0000008-0000-0000-0000-000000000000",
]

# Static resume content per demo candidate (c_idx aligned with _CANDIDATES).
# Shape mirrors ResumeSerializer's read-only fields so the existing resume
# detail page can render it without touching the real DB.
_RESUMES_RAW = [
    {
        "title": "Python Backend Developer",
        "position": "Backend Developer",
        "domain_name": "IT",
        "total_experience": "2 yil 3 oy",
        "resume_skills": [
            {"skill_name": "Python", "minimum_years": 2, "proficiency_level": "ADVANCED"},
            {"skill_name": "Django", "minimum_years": 2, "proficiency_level": "ADVANCED"},
            {"skill_name": "PostgreSQL", "minimum_years": 1, "proficiency_level": "INTERMEDIATE"},
        ],
        "experiences": [
            {"company": "WorkXplorer Demo LLC", "role": "Backend Developer",
             "country": "Uzbekistan", "city": "Tashkent",
             "start_date": "2023-02-01", "end_date": None,
             "description": "Django REST Framework yordamida backend API'larni ishlab chiqish.",
             "duration": "2 yil 3 oy"},
        ],
    },
    {
        "title": "Python Backend Developer",
        "position": "Backend Developer",
        "domain_name": "IT",
        "total_experience": "1 yil 8 oy",
        "resume_skills": [
            {"skill_name": "Python", "minimum_years": 1, "proficiency_level": "INTERMEDIATE"},
            {"skill_name": "Django", "minimum_years": 1, "proficiency_level": "INTERMEDIATE"},
        ],
        "experiences": [
            {"company": "WorkXplorer Demo LLC", "role": "Junior Backend Developer",
             "country": "Uzbekistan", "city": "Tashkent",
             "start_date": "2024-08-01", "end_date": None,
             "description": "REST API'larni qo'llab-quvvatlash va unit testlar yozish.",
             "duration": "1 yil 8 oy"},
        ],
    },
    {
        "title": "Python Backend Developer",
        "position": "Backend Developer",
        "domain_name": "IT",
        "total_experience": "3 yil 1 oy",
        "resume_skills": [
            {"skill_name": "Python", "minimum_years": 3, "proficiency_level": "ADVANCED"},
            {"skill_name": "PostgreSQL", "minimum_years": 2, "proficiency_level": "ADVANCED"},
        ],
        "experiences": [
            {"company": "WorkXplorer Demo LLC", "role": "Backend Developer",
             "country": "Uzbekistan", "city": "Samarkand",
             "start_date": "2022-05-01", "end_date": None,
             "description": "Mikroservislar va ma'lumotlar bazasi optimallashtirish.",
             "duration": "3 yil 1 oy"},
        ],
    },
    {
        "title": "Frontend React Developer",
        "position": "Frontend Developer",
        "domain_name": "IT",
        "total_experience": "1 yil 5 oy",
        "resume_skills": [
            {"skill_name": "React", "minimum_years": 1, "proficiency_level": "INTERMEDIATE"},
            {"skill_name": "TypeScript", "minimum_years": 1, "proficiency_level": "INTERMEDIATE"},
        ],
        "experiences": [
            {"company": "WorkXplorer Demo LLC", "role": "Frontend Developer",
             "country": "Uzbekistan", "city": "Tashkent",
             "start_date": "2024-11-01", "end_date": None,
             "description": "React komponentlarini yaratish va REST API bilan integratsiya.",
             "duration": "1 yil 5 oy"},
        ],
    },
    {
        "title": "Frontend React Developer",
        "position": "Frontend Developer",
        "domain_name": "IT",
        "total_experience": "2 yil 0 oy",
        "resume_skills": [
            {"skill_name": "React", "minimum_years": 2, "proficiency_level": "ADVANCED"},
            {"skill_name": "TypeScript", "minimum_years": 2, "proficiency_level": "ADVANCED"},
        ],
        "experiences": [
            {"company": "WorkXplorer Demo LLC", "role": "Frontend Developer",
             "country": "Uzbekistan", "city": "Tashkent",
             "start_date": "2023-04-01", "end_date": None,
             "description": "Dizayn tizimini qo'llab-quvvatlash va responsive UI yaratish.",
             "duration": "2 yil 0 oy"},
        ],
    },
    {
        "title": "Frontend React Developer",
        "position": "Frontend Developer",
        "domain_name": "IT",
        "total_experience": "0 yil 9 oy",
        "resume_skills": [
            {"skill_name": "React", "minimum_years": 0, "proficiency_level": "BEGINNER"},
            {"skill_name": "JavaScript", "minimum_years": 1, "proficiency_level": "INTERMEDIATE"},
        ],
        "experiences": [
            {"company": "WorkXplorer Demo LLC", "role": "Junior Frontend Developer",
             "country": "Uzbekistan", "city": "Bukhara",
             "start_date": "2025-06-01", "end_date": None,
             "description": "UI komponentlarini ishlab chiqishda yordam berish.",
             "duration": "0 yil 9 oy"},
        ],
    },
    {
        "title": "UX/UI Designer",
        "position": "Product Designer",
        "domain_name": "Design",
        "total_experience": "1 yil 6 oy",
        "resume_skills": [
            {"skill_name": "Figma", "minimum_years": 1, "proficiency_level": "ADVANCED"},
            {"skill_name": "Prototyping", "minimum_years": 1, "proficiency_level": "INTERMEDIATE"},
        ],
        "experiences": [
            {"company": "WorkXplorer Demo LLC", "role": "UX/UI Designer",
             "country": "Uzbekistan", "city": "Tashkent",
             "start_date": "2024-03-01", "end_date": None,
             "description": "Wireframe va prototiplar loyihalash, foydalanuvchanlik testlari.",
             "duration": "1 yil 6 oy"},
        ],
    },
    {
        "title": "UX/UI Designer",
        "position": "Product Designer",
        "domain_name": "Design",
        "total_experience": "2 yil 4 oy",
        "resume_skills": [
            {"skill_name": "Figma", "minimum_years": 2, "proficiency_level": "ADVANCED"},
            {"skill_name": "User Research", "minimum_years": 1, "proficiency_level": "INTERMEDIATE"},
        ],
        "experiences": [
            {"company": "WorkXplorer Demo LLC", "role": "Product Designer",
             "country": "Uzbekistan", "city": "Tashkent",
             "start_date": "2023-09-01", "end_date": None,
             "description": "Dizayn tizimini yaratish va fikr-mulohazalar asosida takrorlash.",
             "duration": "2 yil 4 oy"},
        ],
    },
]

_COMMON_RESUME_FIELDS = {
    "description": None,
    "domain": None,
    "work_status": "OPEN_TO_WORK",
    "work_status_display": "Open to work",
    "is_main": True,
    "candidate_img_url": None,
    "candidate_region": "Tashkent",
    "candidate_phone_number": None,
    "candidate_address": None,
    "candidate_edupartner_name": None,
    "candidate_date_of_birth": None,
    "candidate_citizenship": None,
    "candidate_edupartner_faculty": None,
    "candidate_edupartner_course": None,
    "current_salary": None,
    "salary_currency": None,
    "salary_hide": True,
    "certificates": [],
    "language_certificates": [],
    "conversation_id": None,
    "created_at": "2025-01-01T00:00:00Z",
    "created_by_type": "candidate_created",
    "is_embedded": False,
    "is_reviewed": True,
    "is_demo": True,
}


def _build_demo_resumes():
    resumes = {}
    for c_idx, raw in enumerate(_RESUMES_RAW):
        c_name, c_email = _CANDIDATES[c_idx]
        resume_id = _RESUME_IDS[c_idx]
        resumes[resume_id] = {
            **_COMMON_RESUME_FIELDS,
            **raw,
            "id": resume_id,
            "candidate_full_name": c_name,
            "candidate_email": c_email,
        }
    return resumes


DEMO_RESUMES = _build_demo_resumes()


def get_demo_resume(resume_id: str) -> dict | None:
    return DEMO_RESUMES.get(str(resume_id))

_APPLICATIONS_PLAN = [
    (_A1,  0, 0, "APPLIED"),
    (_A2,  0, 1, "INTERVIEW_SCHEDULED"),
    (_A3,  0, 2, "INTERVIEWED"),
    (_A4,  1, 3, "APPLIED"),
    (_A5,  1, 4, "OFFERED"),
    (_A6,  1, 5, "REJECTED"),
    (_A7,  2, 6, "APPLIED"),
    (_A8,  2, 7, "INTERVIEW_SCHEDULED"),
    (_A9,  3, 0, "APPLIED"),
    (_A10, 3, 1, "INTERVIEWED"),
    (_A11, 3, 2, "OFFERED"),
    (_A12, 3, 3, "REJECTED"),
]

_COMMON_APP_FIELDS = {
    "applied_at": "2025-01-10T10:00:00Z",
    "updated_at": "2025-01-10T10:00:00Z",
    "vacancy_description": None,
    "assignee": None,
    "candidate_img_url": None,
    "cover_letter": None,
    "portfolio_url": None,
    "earliest_start_date": None,
    "resume_title": None,
    "resume_id": None,
    "expected_salary": None,
    "salary_currency": None,
    "status_category": None,
    "days_since_application": 10,
    "is_recent": False,
    "can_withdraw": False,
    "recruiter_notes": None,
    "responsible_recruiter": "WorkXplorer Demo System",
    "documents": [],
    "skill_match": None,
    "status_color": None,
    "discussion_count": 0,
    "employment_type": "FULL_TIME",
    "company_name": DEMO_COMPANY_NAME,
    "is_demo": True,
}


def _build_applications(language: str = "en"):
    apps = []
    for app_id, v_idx, c_idx, status in _APPLICATIONS_PLAN:
        v = _VACANCIES_RAW[v_idx]
        c_name, c_email = _CANDIDATES[c_idx]
        ai_eval = _DEMO_AI_EVALUATION
        resume_id = _RESUME_IDS[c_idx]
        resume_title = _RESUMES_RAW[c_idx]["title"]
        apps.append({
            **_COMMON_APP_FIELDS,
            "id": app_id,
            "vacancy_id": v["id"],
            "vacancy_title": v["title"],
            "company_id": None,
            "about_us": _resolve_lang(v["about_us"], language),
            "requirements": _resolve_lang(v["requirements"], language),
            "responsibilities": _resolve_lang(v["responsibilities"], language),
            "additional_info": None,
            "expire": None,
            "experience": v["experience"],
            "salary_min": v["salary_min"],
            "salary_max": v["salary_max"],
            "salary_currency": v["salary_currency"],
            "recruiter_email": "demo-system@workxplorer.demo",
            "status": status,
            "status_display": status.replace("_", " ").title(),
            "candidate_name": c_name,
            "candidate_email": c_email,
            "candidate_address": None,
            "resume_id": resume_id,
            "resume_title": resume_title,
            "ai_evaluation": ai_eval,
            "kanban_position": _APPLICATIONS_PLAN.index((app_id, v_idx, c_idx, status)),
        })
    return apps


def get_demo_applications(language: str = "en") -> list[dict]:
    return _build_applications(language)


DEMO_APPLICATIONS = _build_applications("en")

# ---------------------------------------------------------------------------
# Kanban
# ---------------------------------------------------------------------------

_KANBAN_STATUS_COLORS = {
    "APPLIED": "#3B82F6",
    "INTERVIEW_SCHEDULED": "#F59E0B",
    "INTERVIEWED": "#8B5CF6",
    "OFFERED": "#10B981",
    "REJECTED": "#EF4444",
}

_STATUS_LABELS = {
    "uz": {
        "APPLIED": "Ariza berildi",
        "INTERVIEW_SCHEDULED": "Suhbat belgilandi",
        "INTERVIEWED": "Suhbat o'tkazildi",
        "OFFERED": "Taklif yuborildi",
        "REJECTED": "Rad etildi",
    },
    "ru": {
        "APPLIED": "Заявка подана",
        "INTERVIEW_SCHEDULED": "Собеседование назначено",
        "INTERVIEWED": "Собеседование прошло",
        "OFFERED": "Предложение отправлено",
        "REJECTED": "Отказано",
    },
    "en": {
        "APPLIED": "Applied",
        "INTERVIEW_SCHEDULED": "Interview Scheduled",
        "INTERVIEWED": "Interviewed",
        "OFFERED": "Offered",
        "REJECTED": "Rejected",
    },
}

_DEMO_STATUS_ORDER = [
    "APPLIED", "INTERVIEW_SCHEDULED", "INTERVIEWED", "OFFERED", "REJECTED",
]


def _build_kanban_app(app_id, v_idx, c_idx, status, position):
    v = _VACANCIES_RAW[v_idx]
    c_name, c_email = _CANDIDATES[c_idx]
    ai_eval = _DEMO_AI_EVALUATION
    return {
        "id": app_id,
        "status": status,
        "status_display": status.replace("_", " ").title(),
        "kanban_position": position,
        "applied_at": "2025-01-10T10:00:00Z",
        "updated_at": "2025-01-10T10:00:00Z",
        "candidate_name": c_name,
        "candidate_email": c_email,
        "candidate_img_url": None,
        "candidate_address": None,
        "vacancy_id": v["id"],
        "vacancy_title": v["title"],
        "company_name": DEMO_COMPANY_NAME,
        "resume_title": _RESUMES_RAW[c_idx]["title"],
        "resume_id": _RESUME_IDS[c_idx],
        "expected_salary": None,
        "salary_currency": None,
        "assignee": None,
        "skill_match": None,
        "ai_evaluation": ai_eval,
    }


_DEMO_APPLICATION_IDS = {app_id for app_id, *_ in _APPLICATIONS_PLAN}


def get_demo_ai_evaluation(application_id: str) -> dict | None:
    """
    Return the full hardcoded AI evaluation for a demo application id.

    Demo applications (_A1.._A12) have no real DB row, so the dedicated
    ai-evaluation endpoint must serve this directly instead of looking up
    an ApplicationAIEvaluation record.
    """
    if str(application_id) not in _DEMO_APPLICATION_IDS:
        return None

    from apps.applications.services.demo_evaluation import DEMO_AI_EVALUATION_RESULT

    return DEMO_AI_EVALUATION_RESULT


def get_demo_kanban_response(language: str, page_size: int = 20, page: int = 1) -> dict:
    labels = _STATUS_LABELS.get(language, _STATUS_LABELS["en"])

    by_status: dict[str, list] = {s: [] for s in _DEMO_STATUS_ORDER}
    for position, (app_id, v_idx, c_idx, status) in enumerate(_APPLICATIONS_PLAN):
        if status in by_status:
            by_status[status].append(_build_kanban_app(app_id, v_idx, c_idx, status, position))

    offset = (page - 1) * page_size
    columns = []
    for status_key in _DEMO_STATUS_ORDER:
        apps = by_status[status_key]
        columns.append({
            "key": status_key,
            "label": labels.get(status_key, status_key),
            "color": _KANBAN_STATUS_COLORS.get(status_key, "#6B7280"),
            "count": len(apps),
            "applications": apps[offset: offset + page_size],
            "has_more": len(apps) > (offset + page_size),
        })

    return {
        "columns": columns,
        "page_size": page_size,
        "page": page,
        "is_demo": True,
    }


# ---------------------------------------------------------------------------
# Waiting recruiters (RecruiterApprovalView)
# ---------------------------------------------------------------------------

DEMO_WAITING_RECRUITERS = [
    {"id": f"r000000{i}-0000-0000-0000-000000000000", "email": f"demo-waiting-{i}@workxplorer.demo",
     "is_recruiter": True, "company": None,
     "profile_full_name": name, "agreed_to_all_consents": True}
    for i, name in enumerate([
        "Aziz Rahimov", "Madina Karimova", "Sherzod Aliyev",
        "Gulnora Usmanova", "Rustam Toshpulatov",
    ], start=1)
]
