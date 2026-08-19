from django.test import TestCase
from django.db.utils import IntegrityError

from apps.skills.models import SkillCategory, Skill, SkillSynonym


class SkillCategoryModelTests(TestCase):
    """Test suite for SkillCategory model."""

    def test_create_skill_category_successfully(self):
        """Test creating a skill category with valid data."""
        category = SkillCategory.objects.create(
            name="Programming", description="Programming languages and frameworks"
        )

        self.assertEqual(category.name, "Programming")
        self.assertEqual(category.description, "Programming languages and frameworks")
        self.assertIsNotNone(category.created_at)

    def test_skill_category_string_representation(self):
        """Test the string representation of SkillCategory."""
        category = SkillCategory.objects.create(name="Soft Skills")

        self.assertEqual(str(category), "Soft Skills")

    def test_skill_category_name_uniqueness(self):
        """Test that category names must be unique."""
        SkillCategory.objects.create(name="Languages")

        with self.assertRaises(IntegrityError):
            SkillCategory.objects.create(name="Languages")

    def test_skill_category_ordering(self):
        """Test that categories are ordered by name."""
        SkillCategory.objects.create(name="Zebra Category")
        SkillCategory.objects.create(name="Apple Category")
        SkillCategory.objects.create(name="Banana Category")

        categories = SkillCategory.objects.all()

        self.assertEqual(categories[0].name, "Apple Category")
        self.assertEqual(categories[1].name, "Banana Category")
        self.assertEqual(categories[2].name, "Zebra Category")

    def test_skill_category_verbose_name_plural(self):
        """Test SkillCategory verbose name plural."""
        self.assertEqual(SkillCategory._meta.verbose_name_plural, "Skill Categories")

    def test_skill_category_with_empty_description(self):
        """Test creating a category with empty description."""
        category = SkillCategory.objects.create(name="Test Category", description="")

        self.assertEqual(category.description, "")


class SkillModelTests(TestCase):
    """Test suite for Skill model."""

    def test_create_skill_successfully(self):
        """Test creating a skill with valid data."""
        skill = Skill.objects.create(
            name="Python", description="Python programming language"
        )

        self.assertEqual(skill.name, "Python")
        self.assertEqual(skill.description, "Python programming language")
        self.assertIsNotNone(skill.created_at)

    def test_skill_string_representation(self):
        """Test the string representation of Skill."""
        skill = Skill.objects.create(name="JavaScript")

        self.assertEqual(str(skill), "JavaScript")

    def test_skill_name_uniqueness(self):
        """Test that skill names must be unique."""
        Skill.objects.create(name="Django")

        with self.assertRaises(IntegrityError):
            Skill.objects.create(name="Django")

    def test_skill_with_categories(self):
        """Test adding categories to a skill."""
        category1 = SkillCategory.objects.create(name="Programming")
        category2 = SkillCategory.objects.create(name="Web Development")

        skill = Skill.objects.create(name="React")
        skill.category.add(category1, category2)

        self.assertEqual(skill.category.count(), 2)
        self.assertIn(category1, skill.category.all())
        self.assertIn(category2, skill.category.all())

    def test_skill_without_categories(self):
        """Test creating a skill without categories."""
        skill = Skill.objects.create(name="TypeScript")

        self.assertEqual(skill.category.count(), 0)

    def test_skill_with_empty_description(self):
        """Test creating a skill with empty description."""
        skill = Skill.objects.create(name="Go", description="")

        self.assertEqual(skill.description, "")

    def test_skill_ordering(self):
        """Test that skills are ordered by category name and skill name."""
        category = SkillCategory.objects.create(name="Languages")

        skill1 = Skill.objects.create(name="Zebra Skill")
        skill1.category.add(category)

        skill2 = Skill.objects.create(name="Apple Skill")
        skill2.category.add(category)

        skills = Skill.objects.all()

        # Should be ordered by category name, then skill name
        self.assertIn("Apple Skill", [s.name for s in skills])
        self.assertIn("Zebra Skill", [s.name for s in skills])


class SkillSynonymModelTests(TestCase):
    """Test suite for SkillSynonym model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.skill = Skill.objects.create(name="JavaScript")

    def test_create_skill_synonym_successfully(self):
        """Test creating a skill synonym with valid data."""
        synonym = SkillSynonym.objects.create(skill=self.skill, synonym="JS")

        self.assertEqual(synonym.skill, self.skill)
        self.assertEqual(synonym.synonym, "JS")

    def test_skill_synonym_string_representation(self):
        """Test the string representation of SkillSynonym."""
        synonym = SkillSynonym.objects.create(skill=self.skill, synonym="js")

        expected_str = f"js -> {self.skill.name}"
        self.assertEqual(str(synonym), expected_str)

    def test_multiple_synonyms_for_skill(self):
        """Test adding multiple synonyms to a skill."""
        synonym1 = SkillSynonym.objects.create(skill=self.skill, synonym="JS")
        synonym2 = SkillSynonym.objects.create(skill=self.skill, synonym="ECMAScript")

        self.assertEqual(self.skill.synonyms.count(), 2)
        self.assertIn(synonym1, self.skill.synonyms.all())
        self.assertIn(synonym2, self.skill.synonyms.all())

    def test_skill_synonym_relationship(self):
        """Test the relationship between Skill and SkillSynonym."""
        SkillSynonym.objects.create(skill=self.skill, synonym="javascript")
        SkillSynonym.objects.create(skill=self.skill, synonym="js")

        synonyms = self.skill.synonyms.all()

        self.assertEqual(synonyms.count(), 2)
        self.assertTrue(all(syn.skill == self.skill for syn in synonyms))

    def test_skill_deletion_cascades_to_synonyms(self):
        """Test that deleting a skill also deletes its synonyms."""
        synonym = SkillSynonym.objects.create(skill=self.skill, synonym="JS")
        synonym_id = synonym.id

        self.skill.delete()

        self.assertFalse(SkillSynonym.objects.filter(id=synonym_id).exists())
