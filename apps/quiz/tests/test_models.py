from django.test import TestCase

from apps.quiz.models import (
    QuizType,
    Quiz,
    Question,
    AnswerChoice,
    CareerOption,
    QuizResult,
)
from apps.authentication.models import Candidate
from apps.skills.models import Skill, SkillCategory


class QuizTypeModelTests(TestCase):
    """Test suite for QuizType model."""

    def test_create_quiz_type_successfully(self):
        """Test creating a quiz type with valid data."""
        quiz_type = QuizType.objects.create(
            name="Career Guidance", description="Helps users find suitable career paths"
        )

        self.assertEqual(quiz_type.name, "Career Guidance")
        self.assertEqual(
            quiz_type.description, "Helps users find suitable career paths"
        )
        self.assertTrue(quiz_type.is_active)
        self.assertIsNotNone(quiz_type.created_at)

    def test_quiz_type_string_representation(self):
        """Test the string representation of QuizType."""
        quiz_type = QuizType.objects.create(name="Skill Assessment")

        self.assertEqual(str(quiz_type), "QuizType: Skill Assessment")

    def test_quiz_type_default_is_active(self):
        """Test that quiz type is active by default."""
        quiz_type = QuizType.objects.create(name="Active Quiz Type")

        self.assertTrue(quiz_type.is_active)

    def test_quiz_type_inactive_status(self):
        """Test creating an inactive quiz type."""
        quiz_type = QuizType.objects.create(name="Inactive Quiz Type", is_active=False)

        self.assertFalse(quiz_type.is_active)


class QuizModelTests(TestCase):
    """Test suite for Quiz model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.quiz_type = QuizType.objects.create(name="Career Guidance")

    def test_create_quiz_successfully(self):
        """Test creating a quiz with valid data."""
        quiz = Quiz.objects.create(
            name="Main Career Quiz",
            quiz_type=self.quiz_type,
            description="Find your career path",
        )

        self.assertEqual(quiz.name, "Main Career Quiz")
        self.assertEqual(quiz.quiz_type, self.quiz_type)
        self.assertEqual(quiz.description, "Find your career path")
        self.assertTrue(quiz.is_active)

    def test_quiz_string_representation(self):
        """Test the string representation of Quiz."""
        quiz = Quiz.objects.create(name="Test Quiz", quiz_type=self.quiz_type)

        expected_str = f"Quiz: Test Quiz ({self.quiz_type.name})"
        self.assertEqual(str(quiz), expected_str)

    def test_quiz_default_is_active(self):
        """Test that quiz is active by default."""
        quiz = Quiz.objects.create(name="Active Quiz", quiz_type=self.quiz_type)

        self.assertTrue(quiz.is_active)

    def test_quiz_relationship_with_type(self):
        """Test the relationship between Quiz and QuizType."""
        quiz1 = Quiz.objects.create(name="Quiz 1", quiz_type=self.quiz_type)
        quiz2 = Quiz.objects.create(name="Quiz 2", quiz_type=self.quiz_type)

        self.assertEqual(quiz1.quiz_type, self.quiz_type)
        self.assertEqual(quiz2.quiz_type, self.quiz_type)
        self.assertEqual(self.quiz_type.quizzes.count(), 2)


class QuestionModelTests(TestCase):
    """Test suite for Question model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.quiz_type = QuizType.objects.create(name="Career Guidance")
        cls.quiz = Quiz.objects.create(name="Main Quiz", quiz_type=cls.quiz_type)

    def test_create_question_successfully(self):
        """Test creating a question with valid data."""
        question = Question.objects.create(
            quiz=self.quiz, title="What is your favorite programming language?"
        )

        self.assertEqual(question.quiz, self.quiz)
        self.assertEqual(question.title, "What is your favorite programming language?")
        self.assertTrue(question.is_active)

    def test_question_string_representation(self):
        """Test the string representation of Question."""
        question = Question.objects.create(quiz=self.quiz, title="Test Question")

        expected_str = f"Question: Test Question ({self.quiz.name})"
        self.assertEqual(str(question), expected_str)

    def test_question_without_quiz(self):
        """Test creating a question without a quiz (nullable)."""
        question = Question.objects.create(title="Standalone Question")

        self.assertIsNone(question.quiz)
        self.assertEqual(str(question), "Question: Standalone Question (No Quiz)")

    def test_question_default_is_active(self):
        """Test that question is active by default."""
        question = Question.objects.create(quiz=self.quiz, title="Active Question")

        self.assertTrue(question.is_active)


class CareerOptionModelTests(TestCase):
    """Test suite for CareerOption model."""

    def test_create_career_option_successfully(self):
        """Test creating a career option with valid data."""
        career_option = CareerOption.objects.create(
            title="Software Engineer", description="Develop software applications"
        )

        self.assertEqual(career_option.title, "Software Engineer")
        self.assertEqual(career_option.description, "Develop software applications")

    def test_career_option_string_representation(self):
        """Test the string representation of CareerOption."""
        career_option = CareerOption.objects.create(title="Data Scientist")

        self.assertEqual(str(career_option), "CareerOption: Data Scientist")

    def test_career_option_with_empty_description(self):
        """Test creating a career option with empty description."""
        career_option = CareerOption.objects.create(title="Manager", description="")

        self.assertEqual(career_option.description, "")

    def test_career_option_with_skills(self):
        """Test creating a career option with skills."""
        category = SkillCategory.objects.create(name="Programming")
        skill1 = Skill.objects.create(name="Python")
        skill1.category.add(category)
        skill2 = Skill.objects.create(name="Django")

        career_option = CareerOption.objects.create(
            title="Backend Developer", description="Develop backend systems"
        )
        career_option.skills.add(skill1, skill2)

        self.assertEqual(career_option.skills.count(), 2)
        self.assertIn(skill1, career_option.skills.all())
        self.assertIn(skill2, career_option.skills.all())

    def test_career_option_skills_relationship_bidirectional(self):
        """Test the bidirectional relationship between CareerOption and Skill."""
        skill = Skill.objects.create(name="JavaScript")
        career_option = CareerOption.objects.create(title="Frontend Developer")

        career_option.skills.add(skill)

        # Test reverse relationship from Skill
        self.assertIn(career_option, skill.career_options.all())


class AnswerChoiceModelTests(TestCase):
    """Test suite for AnswerChoice model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.quiz_type = QuizType.objects.create(name="Career Guidance")
        cls.quiz = Quiz.objects.create(name="Main Quiz", quiz_type=cls.quiz_type)
        cls.question = Question.objects.create(
            quiz=cls.quiz, title="What do you prefer?"
        )
        cls.career_option = CareerOption.objects.create(title="Developer")

    def test_create_answer_choice_successfully(self):
        """Test creating an answer choice with valid data."""
        answer = AnswerChoice.objects.create(
            question=self.question,
            text="Working with code",
            point=80,
            career_option=self.career_option,
        )

        self.assertEqual(answer.question, self.question)
        self.assertEqual(answer.text, "Working with code")
        self.assertEqual(answer.point, 80)
        self.assertEqual(answer.career_option, self.career_option)

    def test_answer_choice_string_representation(self):
        """Test the string representation of AnswerChoice."""
        answer = AnswerChoice.objects.create(
            question=self.question,
            text="This is a long answer text that should be truncated in the string representation",
            point=50,
            career_option=self.career_option,
        )

        # String representation should show first 50 characters
        self.assertIn("Answer to", str(answer))
        self.assertIn(self.question.title, str(answer))

    def test_answer_choice_default_point(self):
        """Test default point value for answer choice."""
        answer = AnswerChoice.objects.create(
            question=self.question,
            text="Default points",
            career_option=self.career_option,
        )

        self.assertEqual(answer.point, 0)

    def test_answer_choice_point_validation(self):
        """Test point validation (should be between 0 and 100)."""
        # Valid point values
        for point in [0, 50, 100]:
            answer = AnswerChoice.objects.create(
                question=self.question,
                text=f"Answer with {point} points",
                point=point,
                career_option=self.career_option,
            )
            self.assertEqual(answer.point, point)


class QuizResultModelTests(TestCase):
    """Test suite for QuizResult model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123"
        )
        cls.quiz_type = QuizType.objects.create(name="Career Guidance")
        cls.quiz = Quiz.objects.create(name="Main Quiz", quiz_type=cls.quiz_type)

    def test_create_quiz_result_successfully(self):
        """Test creating a quiz result with valid data."""
        career_options = [
            {"title": "Software Engineer", "score": 85},
            {"title": "Data Scientist", "score": 75},
        ]

        result = QuizResult.objects.create(
            candidate=self.candidate, quiz=self.quiz, career_options=career_options
        )

        self.assertEqual(result.candidate, self.candidate)
        self.assertEqual(result.quiz, self.quiz)
        self.assertEqual(result.career_options, career_options)

    def test_quiz_result_string_representation(self):
        """Test the string representation of QuizResult."""
        result = QuizResult.objects.create(candidate=self.candidate, quiz=self.quiz)

        expected_str = f"Quiz Result for {self.candidate.email} - {self.quiz.name} at {result.created_at}"
        self.assertEqual(str(result), expected_str)

    def test_quiz_result_default_career_options(self):
        """Test default value for career_options field."""
        result = QuizResult.objects.create(candidate=self.candidate, quiz=self.quiz)

        self.assertEqual(result.career_options, [])

    def test_quiz_result_without_quiz(self):
        """Test creating a quiz result without a quiz (nullable)."""
        result = QuizResult.objects.create(candidate=self.candidate)

        self.assertIsNone(result.quiz)
        expected_str = (
            f"Quiz Result for {self.candidate.email} - No Quiz at {result.created_at}"
        )
        self.assertEqual(str(result), expected_str)

    def test_quiz_result_relationship_with_candidate(self):
        """Test the relationship between QuizResult and Candidate."""
        result1 = QuizResult.objects.create(candidate=self.candidate, quiz=self.quiz)
        result2 = QuizResult.objects.create(candidate=self.candidate, quiz=self.quiz)

        self.assertEqual(self.candidate.quiz_results.count(), 2)
        self.assertIn(result1, self.candidate.quiz_results.all())
        self.assertIn(result2, self.candidate.quiz_results.all())
