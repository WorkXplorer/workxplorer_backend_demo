"""
Hardcoded demo AI evaluation result.

Used as a preview of the AI evaluation feature for companies whose
account has not been approved yet (Company.is_active is False).
Recruiters at such companies see this static, tri-language result
instead of a real AI-generated evaluation, so they can see what
the feature looks like before their company is verified.
"""

DEMO_AI_EVALUATION_RESULT = {
    "overall_score": 74.0,
    "average_rating": 7.0,
    "recommendation": "RECOMMENDED",
    "match_breakdown": {
        "skills_match": {
            "score": 7.0,
            "details": [
                {
                    "uz": "Nomzodning ko'nikmalari vakansiya talablariga umuman mos keladi.",
                    "ru": "Навыки кандидата в целом соответствуют требованиям вакансии.",
                    "en": "The candidate's skills generally match the vacancy requirements.",
                },
                {
                    "uz": "Asosiy texnik va dasturiy vositalardan foydalanish tajribasi mavjud.",
                    "ru": "Имеется опыт работы с основными техническими и программными инструментами.",
                    "en": "Experience using core technical and software tools is present.",
                },
            ],
        },
        "experience_match": {
            "score": 7.0,
            "details": [
                {
                    "uz": "Ish tajribasi vakansiya talab qilgan lavozimga mos keladi.",
                    "ru": "Опыт работы соответствует требованиям данной позиции.",
                    "en": "Work experience matches the requirements of this position.",
                },
                {
                    "uz": "Jamoada ishlash va vazifalarni bajarish ko'nikmalari namoyon bo'ladi.",
                    "ru": "Продемонстрированы навыки командной работы и выполнения задач.",
                    "en": "Demonstrates teamwork and task-execution skills.",
                },
            ],
        },
        "education_match": {
            "score": 7.0,
            "details": [
                {
                    "uz": "Ta'lim darajasi vakansiya talablariga mos keladi.",
                    "ru": "Уровень образования соответствует требованиям вакансии.",
                    "en": "Education level matches the vacancy requirements.",
                },
            ],
        },
        "activity_score": {
            "score": 7.0,
            "details": [
                {
                    "uz": "Nomzod profili faol va muntazam yangilanib boradi.",
                    "ru": "Профиль кандидата активен и регулярно обновляется.",
                    "en": "The candidate's profile is active and regularly updated.",
                },
            ],
        },
    },
    "skills_analysis": {
        "matched_skills": ["Communication", "Teamwork", "MS Office", "Time Management"],
        "missing_skills": ["Advanced certifications relevant to the role"],
        "bonus_skills": ["English proficiency"],
    },
    "experience_summary": {
        "uz": "Bu - намунавий AI baholash natijasi. Kompaniyangiz tasdiqlangandan so'ng, har bir nomzod uchun haqiqiy AI tahlili avtomatik tarzda yaratiladi.",
        "ru": "Это пример результата AI-оценки. После подтверждения вашей компании для каждого кандидата будет автоматически создаваться реальный AI-анализ.",
        "en": "This is a sample AI evaluation result. Once your company is approved, a real AI analysis will be generated automatically for each candidate.",
    },
    "education_summary": {
        "uz": "Namunaviy ta'lim tahlili. Haqiqiy nomzod ma'lumotlari asosida AI tahlili kompaniya tasdiqlangach ko'rinadi.",
        "ru": "Пример анализа образования. Реальный AI-анализ на основе данных кандидата появится после подтверждения компании.",
        "en": "Sample education analysis. The real AI analysis based on the candidate's data will appear once the company is approved.",
    },
    "activity_summary": {
        "uz": "Namunaviy faoliyat tahlili. Bu bo'lim haqiqiy nomzod profili asosida AI tomonidan to'ldiriladi.",
        "ru": "Пример анализа активности. Этот раздел будет заполнен AI на основе реального профиля кандидата.",
        "en": "Sample activity analysis. This section will be filled in by the AI based on the candidate's real profile.",
    },
    "summary": {
        "uz": "Bu AI review funksiyasining namunaviy ko'rinishi. Kompaniyangiz tasdiqlangandan so'ng, har bir ariza uchun haqiqiy nomzod ma'lumotlari asosida to'liq AI tahlili avtomatik ravishda tayyorlanadi.",
        "ru": "Это демонстрационный вид функции AI-обзора. После подтверждения вашей компании для каждой заявки будет автоматически подготовлен полноценный AI-анализ на основе реальных данных кандидата.",
        "en": "This is a preview of the AI review feature. Once your company is approved, a full AI analysis based on the candidate's real data will be prepared automatically for each application.",
    },
    "red_flags": {
        "uz": [
            "Bu namunaviy ma'lumot — haqiqiy nomzod tahlili emas.",
        ],
        "ru": [
            "Это демонстрационные данные — не реальный анализ кандидата.",
        ],
        "en": [
            "This is sample data — not a real candidate analysis.",
        ],
    },
    "strengths": {
        "uz": [
            "Kompaniya tasdiqlangach, har bir nomzod uchun AI tahlili avtomatik ishlaydi",
            "Natijalar uz/ru/en tillarida taqdim etiladi",
        ],
        "ru": [
            "После подтверждения компании AI-анализ будет работать автоматически для каждого кандидата",
            "Результаты предоставляются на узбекском, русском и английском языках",
        ],
        "en": [
            "Once the company is approved, AI analysis runs automatically for every candidate",
            "Results are provided in Uzbek, Russian, and English",
        ],
    },
}
