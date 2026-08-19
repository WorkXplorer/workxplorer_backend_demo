from django.db import models


class ApplicationStatus(models.TextChoices):
    """
    Represents the various stages of a job application process.

    This enum-like structure helps maintain consistency across your application
    and makes it easy to add new statuses or modify existing ones.
    """

    APPLIED = "APPLIED", "Applied"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED", "Interview Scheduled"
    INTERVIEWED = "INTERVIEWED", "Interviewed"
    OFFERED = "OFFERED", "Offered"
    OFFER_ACCEPTED = "OFFER_ACCEPTED", "Offer Accepted"
    OFFER_REJECTED = "OFFER_REJECTED", "Offer Rejected"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
    REJECTED = "REJECTED", "Rejected"
    AI_FAILED = "AI_FAILED", "AI Rejected"

    @classmethod
    def get_translations(cls):
        """
        Returns translations for all application statuses.
        Supported languages: en (English), ru (Russian), uz (Uzbek).
        """
        return {
            cls.APPLIED: {
                "en": "Applied",
                "ru": "Подано",
                "uz": "Topshirildi",
            },
            cls.REJECTED: {
                "en": "Rejected",
                "ru": "Отклонено",
                "uz": "Rad etildi",
            },
            cls.INTERVIEW_SCHEDULED: {
                "en": "Interview Scheduled",
                "ru": "Собеседование назначено",
                "uz": "Suhbat belgilandi",
            },
            cls.INTERVIEWED: {
                "en": "Interviewed",
                "ru": "Собеседование пройдено",
                "uz": "Suhbat o'tkazildi",
            },
            cls.OFFERED: {
                "en": "Offered",
                "ru": "Предложение сделано",
                "uz": "Taklif berildi",
            },
            cls.OFFER_ACCEPTED: {
                "en": "Offer Accepted",
                "ru": "Предложение принято",
                "uz": "Taklif qabul qilindi",
            },
            cls.OFFER_REJECTED: {
                "en": "Offer Rejected",
                "ru": "Предложение отклонено",
                "uz": "Taklif rad etildi",
            },
            cls.WITHDRAWN: {
                "en": "Withdrawn",
                "ru": "Отозвано",
                "uz": "Qaytarib olindi",
            },
            cls.AI_FAILED: {
                "en": "AI Rejected",
                "ru": "Отклонено ИИ",
                "uz": "AI rad etdi",
            },
        }

    @classmethod
    def get_localized_statuses(cls, language: str = "en") -> list:
        """
        Returns list of statuses with localized labels.
        
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
        return [
            {
                "key": status.value,
                "label": translations[status].get(language, translations[status]["en"])
            }
            for status in cls
        ]


class ApplicationDocumentTypes(models.TextChoices):
    RESUME = "RESUME", "Resume"
    CERTIFICATE = "CERTIFICATE", "Certificate"
    PORTFOLIO = "PORTFOLIO", "Portfolio"
    REFERENCE = "REFERENCE", "Reference Letter"
    COVER_LETTER = "COVER_LETTER", "Cover Letter"
    TRANSCRIPT = "TRANSCRIPT", "Academic Transcript"
    OTHER = "OTHER", "Other"
