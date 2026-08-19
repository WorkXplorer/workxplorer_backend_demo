from django.db import models


class ProficiencyLevel(models.TextChoices):
    UNDEFINED = "UNDEFINED", "Undefined"
    BEGINNER = "BEGINNER", "Beginner"
    INTERMEDIATE = "INTERMEDIATE", "Intermediate"
    ADVANCED = "ADVANCED", "Advanced"
    EXPERT = "EXPERT", "Expert"


class LanguageProficiencyLevel(models.TextChoices):
    """CEFR language proficiency levels."""

    A1 = "A1", "A1"
    A2 = "A2", "A2"
    B1 = "B1", "B1"
    B2 = "B2", "B2"
    C1 = "C1", "C1"
    C2 = "C2", "C2"


class WorkStatus(models.TextChoices):
    """Work status choices for resumes"""

    # Job seeking statuses
    ACTIVELY_LOOKING = "ACTIVELY_LOOKING", "Actively looking"
    OPEN_TO_OPPORTUNITIES = "OPEN_TO_OPPORTUNITIES", "Open to opportunities"
    NOT_LOOKING = "NOT_LOOKING", "Not looking"
    PART_TIME_CONSIDERING = "PART_TIME_CONSIDERING", "Considering part-time employment"

    # Employment statuses
    EMPLOYED = "EMPLOYED", "Employed"
    SELF_EMPLOYED = "SELF_EMPLOYED", "Self Employed"
    FREELANCER = "FREELANCER", "Freelancer"
    INTERNSHIP = "INTERNSHIP", "Internship"
    STUDENT = "STUDENT", "Student"
    UNEMPLOYED = "UNEMPLOYED", "Unemployed"

    @classmethod
    def employed_statuses(cls):
        """Return list of statuses considered as 'employed' for analytics."""
        return [cls.EMPLOYED, cls.SELF_EMPLOYED, cls.FREELANCER]

    @classmethod
    def is_employed(cls, status):
        """Check if a status is considered employed."""
        return status in cls.employed_statuses()

    @classmethod
    def get_translations(cls):
        """
        Returns translations for all work statuses.
        Supported languages: en (English), ru (Russian), uz (Uzbek).
        """
        return {
            # Job seeking statuses
            cls.ACTIVELY_LOOKING: {
                "en": "Actively looking",
                "ru": "Активно ищет работу",
                "uz": "Faol ish qidirmoqda",
            },
            cls.OPEN_TO_OPPORTUNITIES: {
                "en": "Open to opportunities",
                "ru": "Открыт для предложений",
                "uz": "Yangi imkoniyatlarga ochiq",
            },
            cls.NOT_LOOKING: {
                "en": "Not looking",
                "ru": "Не ищет работу",
                "uz": "Ish qidirmayapti",
            },
            cls.PART_TIME_CONSIDERING: {
                "en": "Considering part-time employment",
                "ru": "Рассматривает частичную занятость",
                "uz": "Yarim stavkaga qiziqmoqda",
            },
            # Employment statuses
            cls.EMPLOYED: {
                "en": "Employed",
                "ru": "Работает",
                "uz": "Ishlamoqda",
            },
            cls.SELF_EMPLOYED: {
                "en": "Self Employed",
                "ru": "Самозанятый",
                "uz": "O'z-o'zini band qilgan",
            },
            cls.FREELANCER: {
                "en": "Freelancer",
                "ru": "Фрилансер",
                "uz": "Frilanser",
            },
            cls.INTERNSHIP: {
                "en": "Internship",
                "ru": "Стажировка",
                "uz": "Amaliyot",
            },
            cls.STUDENT: {
                "en": "Student",
                "ru": "Студент",
                "uz": "Talaba",
            },
            cls.UNEMPLOYED: {
                "en": "Unemployed",
                "ru": "Безработный",
                "uz": "Ishsiz",
            },
        }

    @classmethod
    def get_localized_statuses(cls, language: str = "en") -> list:
        """
        Returns list of job seeking work statuses with localized labels.
        Only returns the 4 job-seeking statuses used in headhunting.
        
        Args:
            language: Language code ('en', 'ru', 'uz'). Defaults to 'en'.
            
        Returns:
            List of dicts with 'key' and 'label' for each status.
        """
        # Validate language, default to 'en' if invalid
        valid_languages = ["en", "ru", "uz"]
        if language not in valid_languages:
            language = "en"

        translations = cls.get_translations()
        job_seeking_statuses = [
            cls.ACTIVELY_LOOKING,
            cls.OPEN_TO_OPPORTUNITIES,
            cls.NOT_LOOKING,
            cls.PART_TIME_CONSIDERING,
        ]
        
        return [
            {
                "key": status.value,
                "label": translations[status].get(language, translations[status]["en"])
            }
            for status in job_seeking_statuses
        ]
