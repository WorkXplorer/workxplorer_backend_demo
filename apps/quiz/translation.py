from modeltranslation.translator import translator, TranslationOptions
from .models import QuizType, Quiz, Question, AnswerChoice, CareerOption


class QuizTypeTranslationOptions(TranslationOptions):
    fields = ("name", "description")


class QuizTranslationOptions(TranslationOptions):
    fields = ("name", "description")


class QuestionTranslationOptions(TranslationOptions):
    fields = ("title",)


class AnswerChoiceTranslationOptions(TranslationOptions):
    fields = ("text",)


class CareerOptionTranslationOptions(TranslationOptions):
    fields = ("title", "description")


translator.register(QuizType, QuizTypeTranslationOptions)
translator.register(Quiz, QuizTranslationOptions)
translator.register(Question, QuestionTranslationOptions)
translator.register(AnswerChoice, AnswerChoiceTranslationOptions)
translator.register(CareerOption, CareerOptionTranslationOptions)
