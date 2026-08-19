from modeltranslation.translator import translator, TranslationOptions
from .models import Domain


class DomainTranslationOptions(TranslationOptions):
    fields = ("name", "description")


translator.register(Domain, DomainTranslationOptions)
