from django.db import models
from django.utils.translation import gettext_lazy as _

from utils import AbstractBaseModel
from utils.fields import UUIDField


class SkillTest(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)

    skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.CASCADE,
        related_name="tests",
    )
    candidate = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.CASCADE,
        related_name="generated_tests",
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Candidate who generated this test"),
    )
    target_level = models.CharField(
        max_length=20,
        default="INTERMEDIATE",
        help_text=_("Target proficiency level for this test"),
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("AI-generated test title"),
    )
    time_limit_minutes = models.PositiveIntegerField(
        default=10,
        help_text=_("Time limit in minutes"),
    )
    total_questions = models.PositiveIntegerField(
        default=0,
        help_text=_("Total number of questions"),
    )
    passing_score = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=70.0,
        help_text=_("Minimum score percentage to pass"),
    )
    ai_model = models.CharField(
        max_length=30,
        default="default",
        help_text=_("AI model used to generate this test"),
    )
    input_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("AI input tokens used for test generation"),
    )
    output_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("AI output tokens used for test generation"),
    )
    thinking_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("AI thinking/reasoning tokens used for test generation"),
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = _("Skill Test")
        verbose_name_plural = _("Skill Tests")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["skill", "target_level"]),
        ]

    def __str__(self):
        return f"Test({self.skill.name}) level={self.target_level}"


class TestQuestion(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)

    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "MULTIPLE_CHOICE", _("Multiple Choice")
        OPEN_ENDED = "OPEN_ENDED", _("Open-ended")

    test = models.ForeignKey(
        SkillTest,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text=_("Question order within the test"),
    )
    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.MULTIPLE_CHOICE,
    )
    question_text = models.TextField(
        help_text=_("The question text"),
    )
    options = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Array of options for MC questions: [{id, text}, ...]"),
    )
    correct_answer = models.JSONField(
        default=dict,
        help_text=_("Correct answer: {option_id} for MC, {keywords, rubric, sample_answer} for open-ended"),
    )
    points = models.PositiveIntegerField(
        default=1,
        help_text=_("Points for this question"),
    )
    category = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=_("Sub-competency category"),
    )
    explanation = models.TextField(
        blank=True,
        default="",
        help_text=_("Explanation of the correct answer"),
    )

    class Meta:
        verbose_name = _("Test Question")
        verbose_name_plural = _("Test Questions")
        ordering = ["test", "order"]
        indexes = [
            models.Index(fields=["test", "order"]),
        ]

    def __str__(self):
        return f"Q{self.order}: {str(self.question_text)[:50]}"


class TestAttempt(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In Progress")
        COMPLETED = "completed", _("Completed")
        EXPIRED = "expired", _("Expired")

    test = models.ForeignKey(
        SkillTest,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    candidate = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.CASCADE,
        related_name="test_attempts",
    )
    resume = models.ForeignKey(
        "resumes.Resume",
        on_delete=models.CASCADE,
        related_name="test_attempts",
    )
    roadmap_item = models.ForeignKey(
        "student_analytics.RoadmapItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_attempts",
    )
    vacancy_roadmap_item = models.ForeignKey(
        "student_analytics.VacancyRoadmapItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_attempts",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
        help_text=_("Final score percentage"),
    )
    total_points = models.PositiveIntegerField(default=0)
    earned_points = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
    )
    passed = models.BooleanField(default=False)
    input_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("Total AI input tokens used for this attempt"),
    )
    output_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("Total AI output tokens used for this attempt"),
    )
    thinking_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("Total AI thinking/reasoning tokens used for this attempt"),
    )
    result_message = models.TextField(
        blank=True,
        default="",
        help_text=_("AI-generated result message"),
    )
    strengths = models.JSONField(
        default=list,
        blank=True,
        help_text=_("AI-analyzed strengths: [{category, description}]"),
    )
    weaknesses = models.JSONField(
        default=list,
        blank=True,
        help_text=_("AI-analyzed weaknesses: [{category, description}]"),
    )

    class Meta:
        verbose_name = _("Test Attempt")
        verbose_name_plural = _("Test Attempts")
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["candidate", "test"]),
            models.Index(fields=["candidate", "status"]),
        ]

    def __str__(self):
        return f"Attempt({self.candidate_id}) {self.test.skill.name} - {self.status}"


class TestAnswer(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)

    attempt = models.ForeignKey(
        TestAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        TestQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    selected_option_id = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text=_("Selected option ID for MC questions"),
    )
    open_ended_text = models.TextField(
        blank=True,
        default="",
        help_text=_("Candidate's text answer for open-ended questions"),
    )
    is_correct = models.BooleanField(default=False)
    points_earned = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
    )
    ai_evaluation = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("AI evaluation result for open-ended: {score, feedback, matched_keywords, missing_keywords}"),
    )
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Test Answer")
        verbose_name_plural = _("Test Answers")
        ordering = ["attempt", "question__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_attempt_question_answer",
            )
        ]

    def __str__(self):
        return f"Answer(Q{self.question.order}) correct={self.is_correct}"
