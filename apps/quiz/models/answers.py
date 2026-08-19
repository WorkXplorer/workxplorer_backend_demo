from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from utils import AbstractBaseModel


class AnswerChoice(AbstractBaseModel):
    """
    Represents an answer to a quiz question.
    Each answer is linked to a specific question via a ForeignKey and has a point value.
    Can be associated with a domain to help determine candidate's preferred field.
    """

    question = models.ForeignKey(
        "quiz.Question",
        related_name="answers",
        on_delete=models.CASCADE,
        verbose_name="Question",
    )
    text = models.CharField(max_length=500, verbose_name="Answer Text")
    point = models.SmallIntegerField(
        default=0,
        verbose_name="Points",
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    career_option = models.ForeignKey(
        "quiz.CareerOption",
        on_delete=models.CASCADE,
        related_name="answer_choices",
        null=True,
        blank=True,
    )
    domains = models.ManyToManyField(
        "domain.Domain",
        blank=True,
        related_name="answer_choices",
        verbose_name="Domains",
        help_text="The domains/fields this answer corresponds to for domain determination",
    )

    class Meta:
        verbose_name = "AnswerChoice"
        verbose_name_plural = "AnswerChoices"

    def __str__(self) -> str:
        text_preview = str(self.text)[:50] if self.text else ""
        return f"Answer to {self.question.title}: {text_preview}..."


class CareerOption(AbstractBaseModel):
    """
    Represents a position in a position, which can have multiple questions.
    Each position is linked to a specific position and contains its title.
    """

    title = models.CharField(max_length=240, verbose_name="Position Title")
    description = models.TextField(
        max_length=5000,
        blank=True,
        verbose_name="Position Description",
        help_text="A brief description of the position.",
    )
    skills = models.ManyToManyField(
        "skills.Skill",
        blank=True,
        related_name="career_options",
        verbose_name="Skills",
        help_text="Skills relevant to this career option",
    )

    class Meta:
        verbose_name = "CareerOption"
        verbose_name_plural = "CareerOptions"

    def __str__(self):
        return f"CareerOption: {self.title}"


class QuizResult(AbstractBaseModel):
    """
    Represents the result of a Quiz, including the user's answers.
    Each quiz result is linked to a specific candidate and quiz.
    """

    candidate = models.ForeignKey(
        "authentication.Candidate",
        on_delete=models.CASCADE,
        related_name="quiz_results",
        null=True,
        blank=True,
        help_text="The candidate who submitted the quiz result.",
    )
    quiz = models.ForeignKey(
        "quiz.Quiz",
        related_name="results",
        on_delete=models.CASCADE,
        verbose_name="Quiz",
        null=True,  # Temporarily nullable for migration
        blank=True,
    )
    domain = models.ForeignKey(
        "domain.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quiz_results",
        help_text="The domain determined for this candidate from the quiz.",
    )
    # Top career options sorted by recommendation
    career_options = models.JSONField(default=list)

    class Meta:
        verbose_name = "Quiz Result"
        verbose_name_plural = "Quiz Results"
        ordering = ["-created_at"]

    def __str__(self):
        quiz_name = self.quiz.name if self.quiz else "No Quiz"
        candidate_email = self.candidate.email if self.candidate else "Anonymous"
        return (
            f"Quiz Result for {candidate_email} - {quiz_name} at {self.created_at}"
        )
