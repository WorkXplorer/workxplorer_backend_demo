from modeltranslation.translator import translator, TranslationOptions

from .models import EduPartner, EduPartnersType


class EduPartnerTranslationOptions(TranslationOptions):
    fields = ("name", "description")


class EduPartnersTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


translator.register(EduPartner, EduPartnerTranslationOptions)
translator.register(EduPartnersType, EduPartnersTypeTranslationOptions)
