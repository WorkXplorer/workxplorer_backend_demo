from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.authentication.models import Candidate, Recruiter
from apps.skills.models import Skill


class SkillCreateAPIViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("skill-create")

    def test_candidate_can_create_pending_skill(self):
        candidate = Candidate.objects.create_user(
            email="candidate-skill-create@test.com",
            password="testpass123",
            is_candidate=True,
        )
        self.client.force_authenticate(user=candidate)

        response = self.client.post(
            self.url,
            {"name": "Candidate Created Skill"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        skill = Skill.objects.get(name="Candidate Created Skill")
        # Stored immediately but pending AI approval, and attributed to the user.
        self.assertFalse(skill.is_active)
        self.assertEqual(skill.created_by_id, candidate.id)

    def test_recruiter_can_create_pending_skill(self):
        recruiter = Recruiter.objects.create_user(
            email="recruiter-skill-create@test.com",
            password="testpass123",
            is_recruiter=True,
        )
        self.client.force_authenticate(user=recruiter)

        response = self.client.post(
            self.url,
            {"name": "Recruiter Created Skill"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        skill = Skill.objects.get(name="Recruiter Created Skill")
        self.assertFalse(skill.is_active)

    def test_anonymous_cannot_create_skill(self):
        response = self.client.post(
            self.url,
            {"name": "Anonymous Skill"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Skill.objects.filter(name="Anonymous Skill").exists())

    def test_hourly_creation_limit_enforced(self):
        candidate = Candidate.objects.create_user(
            email="candidate-rate-limit@test.com",
            password="testpass123",
            is_candidate=True,
        )
        # Pre-create the maximum allowed within the current hour.
        for i in range(5):
            Skill.objects.create(
                name=f"Existing Skill {i}",
                is_active=False,
                created_by=candidate,
            )

        self.client.force_authenticate(user=candidate)
        response = self.client.post(
            self.url,
            {"name": "One Too Many"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(Skill.objects.filter(name="One Too Many").exists())


class SkillListNamesAPIViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("skill-list-names")

    def test_pending_skills_are_listed_and_flagged(self):
        Skill.objects.create(name="Python", is_active=True)
        Skill.objects.create(name="Pytest Pending", is_active=False)

        response = self.client.get(self.url, {"search": "Py"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.json()["data"]
        by_name = {item["name"]: item for item in results}

        # Both approved and pending skills are discoverable by other candidates.
        self.assertIn("Python", by_name)
        self.assertIn("Pytest Pending", by_name)
        self.assertFalse(by_name["Python"]["is_pending"])
        self.assertTrue(by_name["Pytest Pending"]["is_pending"])

        # Approved skills rank ahead of pending ones within the same relevance.
        names = [item["name"] for item in results]
        self.assertLess(names.index("Python"), names.index("Pytest Pending"))
