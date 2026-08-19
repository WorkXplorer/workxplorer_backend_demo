from django.db import models

from utils import AbstractBaseModel


class QuizType(AbstractBaseModel):
    """
    Defines categories of quizzes available in the system.
    Each quiz type groups related quizzes together.
    Can be linked to a specific domain for domain-based quiz filtering.
    """

    name = models.CharField(
        max_length=100,
        verbose_name="Quiz Type Name",
        help_text="Type identifier (e.g., 'WORKXPLORER Career Guidance', 'Python Skill Assessment')",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description",
        help_text="Explanation of quiz type purpose",
    )
    domains = models.ManyToManyField(
        "domain.Domain",
        blank=True,
        related_name="quiz_types",
        verbose_name="Domains",
        help_text="The domains/fields this quiz type belongs to (e.g., IT, Healthcare)",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Is Active",
        help_text="Controls visibility of this quiz type",
    )

    class Meta:
        verbose_name = "Quiz Type"
        verbose_name_plural = "Quiz Types"
        ordering = ["-created_at"]

    def __str__(self):
        return f"QuizType: {self.name}"


class Quiz(AbstractBaseModel):
    """
    Represents individual quiz instances within a type.
    Each quiz belongs to a quiz type and contains questions.
    """

    name = models.CharField(
        max_length=255,
        verbose_name="Quiz Name",
        help_text="Quiz title (e.g., 'Main Career Guidance Quiz')",
    )
    quiz_type = models.ForeignKey(
        QuizType,
        related_name="quizzes",
        on_delete=models.CASCADE,
        verbose_name="Quiz Type",
        help_text="Category classification",
    )
    description = models.TextField(
        blank=True, verbose_name="Description", help_text="Quiz instructions/overview"
    )
    is_active = models.BooleanField(
        default=True, verbose_name="Is Active", help_text="Publication status"
    )

    class Meta:
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quiz: {self.name} ({self.quiz_type.name})"


class Question(AbstractBaseModel):
    """
    Represents a quiz question.
    Each question is linked to a specific quiz and has answers.
    """

    quiz = models.ForeignKey(
        "quiz.Quiz",
        related_name="questions",
        on_delete=models.CASCADE,
        verbose_name="Quiz",
        null=True,  # Temporarily nullable for migration
        blank=True,
    )
    title = models.CharField(max_length=255, verbose_name="Question Title")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")

    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        ordering = ["id"]

    def __str__(self):
        quiz_name = self.quiz.name if self.quiz else "No Quiz"
        return f"Question: {self.title} ({quiz_name})"
