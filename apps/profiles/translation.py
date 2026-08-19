from modeltranslation.translator import translator, TranslationOptions

from .models import Citizenship


class CitizenshipTranslationOptions(TranslationOptions):
    fields = ("name",)


translator.register(Citizenship, CitizenshipTranslationOptions)
