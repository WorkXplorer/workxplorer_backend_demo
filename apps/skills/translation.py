from modeltranslation.translator import translator, TranslationOptions
from .models import Skill, SkillCategory


class SkillTranslationOptions(TranslationOptions):
    fields = ("name", "description")


class SkillCategoryTranslationOptions(TranslationOptions):
    fields = ("name", "description")


translator.register(Skill, SkillTranslationOptions)
translator.register(SkillCategory, SkillCategoryTranslationOptions)
