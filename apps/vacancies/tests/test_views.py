from uuid import uuid4

from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.authentication.models import Company, Recruiter, Candidate
from apps.vacancies.models import FavouriteVacancy, Vacancy, VacancySkill, VacancyLanguage
from apps.skills.models import Skill, SkillCategory
from apps.languages.models import Language
from apps.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionFeature,
    PlanFeature,
    CompanySubscription,
)
from apps.subscriptions.services import FEATURE_VACANCY_LIMIT


def _setup_pro_subscription(company):
    """Create a Pro plan with generous vacancy limits for test isolation."""
    plan, _ = SubscriptionPlan.objects.get_or_create(
        slug="company-pro",
        defaults={
            "name": "Pro",
            "plan_type": "company",
            "max_admins": 3,
            "max_recruiters": 10,
            "price": 0,
            "display_order": 3,
        },
    )
    feature, _ = SubscriptionFeature.objects.get_or_create(
        code=FEATURE_VACANCY_LIMIT,
        defaults={"name": "Vacancy Limit", "feature_type": "company"},
    )
    PlanFeature.objects.get_or_create(
        plan=plan,
        feature=feature,
        defaults={
            "is_enabled": True,
            "configuration": {
                "max_active_vacancies": 10,
                "max_expire_days": 180,
            },
        },
    )
    CompanySubscription.objects.get_or_create(
        company=company,
        status=CompanySubscription.Status.ACTIVE,
        defaults={"plan": plan},
    )


class VacancyListViewTests(APITestCase):
    """
    Test suite for the VacancyListView API.

    This endpoint should:
    - Return only active vacancies
    - Include related company, recruiter, and skills data
    - Provide formatted salary ranges
    - Support pagination (results inside "results" key)
    """

    def setUp(self):
        """
        Prepare initial data:
        - Company + Recruiter
        - Skills and categories
        - One active and one inactive vacancy
        """
        # Company
        self.company = Company.objects.create(name="Test Company", tin="123456789")

        # Recruiter
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=self.company,
        )

        # Skill categories + skills
        self.cat_prog = SkillCategory.objects.create(name="Programming")
        self.cat_soft = SkillCategory.objects.create(name="Soft Skills")

        self.skill_python = Skill.objects.create(name="Python")
        self.skill_python.category.add(self.cat_prog)

        self.skill_comm = Skill.objects.create(name="Communication")
        self.skill_comm.category.add(self.cat_soft)

        # Active vacancy
        self.vacancy = Vacancy.objects.create(
            id=uuid4(),
            created_by=self.recruiter,
            title="Backend Developer",
            employment_type="FULL_TIME",
            salary_min=2000,
            salary_max=4000,
            company=self.company,
            is_active=True,
        )

        # Skills for vacancy
        VacancySkill.objects.create(
            vacancy=self.vacancy,
            skill=self.skill_python,
            is_required=True,
            minimum_years=2,
            proficiency_level="INTERMEDIATE",
        )
        VacancySkill.objects.create(
            vacancy=self.vacancy,
            skill=self.skill_comm,
            is_required=False,
            minimum_years=0,
            proficiency_level="BEGINNER",
        )

        # Inactive vacancy
        self.inactive_vacancy = Vacancy.objects.create(
            id=uuid4(),
            created_by=self.recruiter,
            title="Frontend Developer",
            employment_type="FULL_TIME",
            salary_min=1500,
            salary_max=2500,
            company=self.company,
            is_active=False,
        )

        self.url = reverse("vacancy-list")  # The URL name must match `VacancyListView`

    def test_list_active_vacancies_successfully(self):
        """
        API should return only active vacancies with all required fields.
        """
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Extract results (StandardJSONRenderer wraps paginated data in "data")
        results = data["data"]

        # Only 1 active vacancy
        assert len(results) == 1
        vacancy = results[0]

        # Validate main fields
        assert vacancy["title"] == "Backend Developer"
        assert vacancy["company_name"] == self.company.name
        assert vacancy["recruiter_email"] == self.recruiter.email

        # Validate skills
        skills = vacancy["vacancy_skills"]
        assert len(skills) == 2
        skill_names = [s["skill_name"] for s in skills]
        assert "Python" in skill_names
        assert "Communication" in skill_names

    def test_no_active_vacancies(self):
        """
        API should return an empty list if no active vacancies exist.
        """
        self.vacancy.is_active = False
        self.vacancy.save()

        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        results = data["data"]
        assert results == []


class RetrieveVacancyViewTests(APITestCase):
    """
    Test suite for the RetrieveVacancyView API.

    This endpoint should:
    - Return a single vacancy by ID with all details and skills
    - Return 404 if vacancy does not exist
    """

    def setUp(self):
        """
        Prepare initial data:
        - Company + Recruiter
        - Two skills
        - One active vacancy with related skills
        """
        self.company = Company.objects.create(name="Test Company", tin="123456789")
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            company=self.company,
        )

        # Skills
        self.skill_python = Skill.objects.create(name="Python")
        self.skill_django = Skill.objects.create(name="Django")

        # Vacancy
        self.vacancy = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="Backend Developer",
            salary_min=1000,
            salary_max=2000,
            employment_type="FULL_TIME",
            is_active=True,
        )

        # Vacancy skills
        VacancySkill.objects.create(
            vacancy=self.vacancy,
            skill=self.skill_python,
            is_required=True,
            minimum_years=2,
            proficiency_level="INTERMEDIATE",
        )
        VacancySkill.objects.create(
            vacancy=self.vacancy,
            skill=self.skill_django,
            is_required=False,
            minimum_years=1,
            proficiency_level="BEGINNER",
        )

        self.url = reverse("retrieve-vacancy", kwargs={"id": str(self.vacancy.id)})

    def test_retrieve_vacancy_successfully(self):
        """
        API should return vacancy with all related fields and skills.
        """
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        data = body["data"]

        # Validate vacancy fields
        assert data["id"] == str(self.vacancy.id)
        assert data["title"] == "Backend Developer"
        assert data["company_name"] == "Test Company"
        assert data["recruiter_email"] == self.recruiter.email

        # Validate skills
        skills = data["vacancy_skills"]
        skill_names = [s["skill_name"] for s in skills]
        assert "Python" in skill_names
        assert "Django" in skill_names

    def test_retrieve_non_existent_vacancy(self):
        """
        API should return 404 if vacancy does not exist.
        """
        url = reverse(
            "retrieve-vacancy", kwargs={"id": "11111111-1111-1111-1111-111111111111"}
        )
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class CreateVacancyViewTests(APITestCase):
    """
    Test suite for the CreateVacancyView API.

    This endpoint should:
    - Allow only authenticated recruiters with a company to create vacancies
    - Attach provided skills to the vacancy
    - Return appropriate errors for invalid cases
    """

    def setUp(self):
        self.client = APIClient()

        # Company
        self.company = Company.objects.create(name="Test Company", tin="123456789")

        # Set up Pro subscription so limit checks don't interfere
        _setup_pro_subscription(self.company)

        # Recruiter user
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            company=self.company,
        )

        # Candidate (non-recruiter user)
        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123", is_candidate=True
        )

        # Skills
        self.skill_python = Skill.objects.create(name="Python")
        self.skill_django = Skill.objects.create(name="Django")

        self.url = reverse("create-vacancy")

        # Valid payload with two skills
        self.valid_payload = {
            "title": "Backend Developer",
            # "description": "We are hiring a backend developer",
            "salary_min": 1000,
            "salary_max": 2000,
            "employment_type": "FULL_TIME",
            "skills_data": [
                {
                    "skill_id": self.skill_python.id,
                    "is_required": True,
                    "minimum_years": 2,
                    "proficiency_level": "INTERMEDIATE",
                },
                {
                    "skill_id": self.skill_django.id,
                    "is_required": False,
                    "minimum_years": 1,
                    "proficiency_level": "BEGINNER",
                },
            ],
        }

    def test_create_vacancy_successfully(self):
        """
        Recruiter with company should be able to create vacancy successfully
        """
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.url, self.valid_payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # Response structure (APIResponse.created wraps data in "data" key)
        assert data["success"] is True
        assert "message" in data
        vacancy = data["data"]

        # Core fields
        assert vacancy["title"] == "Backend Developer"
        assert vacancy["company_name"] == self.company.name
        assert vacancy["recruiter_email"] == self.recruiter.email

        # Skills must be created
        skills = vacancy["vacancy_skills"]
        skill_names = [s["skill_name"] for s in skills]
        assert "Python" in skill_names
        assert "Django" in skill_names

    def test_create_vacancy_as_non_recruiter(self):
        """
        Non-recruiter user should not be able to create a vacancy
        """
        self.client.force_authenticate(user=self.candidate)
        response = self.client.post(self.url, self.valid_payload, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only recruiters can create vacancies" in response.json()["error"]["message"]

    def test_create_vacancy_without_company(self):
        """
        Recruiter without a company should not be able to create a vacancy
        """
        recruiter_no_company = Recruiter.objects.create_user(
            email="recruiter2@test.com",
            password="testpass123",
            company=None,
        )
        self.client.force_authenticate(user=recruiter_no_company)
        response = self.client.post(self.url, self.valid_payload, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Recruiter must be associated with a company" in response.json()["error"]["message"]

    def test_unauthenticated_user_cannot_create(self):
        """
        Unauthenticated users should not be able to create vacancies
        """
        response = self.client.post(self.url, self.valid_payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class RecruiterVacancyListViewTests(APITestCase):
    """
    Test suite for the RecruiterVacancyListView API.

    This endpoint should:
    - Allow recruiters to see only their own vacancies
    - Return empty list if recruiter has no vacancies
    - Prevent candidates and unauthenticated users from accessing recruiter vacancies
    """

    def setUp(self):
        self.client = APIClient()

        # Company
        self.company = Company.objects.create(name="Recruiter Co", tin="987654321")

        # Recruiter user
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            company=self.company,
        )

        # Candidate (non-recruiter user)
        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123", is_candidate=True
        )

        self.url = reverse("recruiter-vacancy-list")

    def test_list_recruiter_vacancies_successfully(self):
        """
        Recruiter should see only their own vacancies
        """
        Vacancy.objects.create(
            title="Backend Developer",
            company=self.company,
            created_by=self.recruiter,
            is_active=True,
        )
        Vacancy.objects.create(
            title="Frontend Developer",
            company=self.company,
            created_by=self.recruiter,
            is_active=True,
        )

        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # StandardJSONRenderer wraps paginated data in "data" key
        results = data["data"]
        assert len(results) == 2

        titles = [v["title"] for v in results]
        assert "Backend Developer" in titles
        assert "Frontend Developer" in titles

    def test_recruiter_with_no_vacancies(self):
        """
        Recruiter should get an empty list if they have no vacancies
        """
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["data"]
        assert results == []

    def test_candidate_cannot_see_vacancies(self):
        """
        Candidate should not see recruiter vacancies
        """
        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["data"]
        assert results == []

    def test_unauthenticated_user_cannot_access(self):
        """
        Unauthenticated users should not have access
        """
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class FavouriteVacancyViewTests(APITestCase):
    """Test candidate favourite vacancy endpoints and serializer fields."""

    def setUp(self):
        self.client = APIClient()

        self.company = Company.objects.create(name="Fav Company", tin="112233445")
        self.recruiter = Recruiter.objects.create_user(
            email="fav-recruiter@test.com",
            password="testpass123",
            company=self.company,
            is_recruiter=True,
        )
        self.candidate = Candidate.objects.create_user(
            email="fav-candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )
        self.other_candidate = Candidate.objects.create_user(
            email="other-candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        self.vacancy_1 = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="Python Developer",
            is_active=True,
        )
        self.vacancy_2 = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="QA Engineer",
            is_active=True,
        )

        self.toggle_url = lambda vacancy_id: reverse(
            "toggle-favourite-vacancy", kwargs={"id": str(vacancy_id)}
        )
        self.list_url = reverse("favourite-vacancy-list")
        self.vacancy_list_url = reverse("vacancy-list")
        self.vacancy_detail_url = lambda vacancy_id: reverse(
            "retrieve-vacancy", kwargs={"id": str(vacancy_id)}
        )

    def test_toggle_favourite_adds_and_removes(self):
        self.client.force_authenticate(user=self.candidate)

        add_response = self.client.post(self.toggle_url(self.vacancy_1.id), format="json")
        assert add_response.status_code == status.HTTP_200_OK
        assert add_response.json()["data"]["is_favourite"] is True
        assert add_response.json()["data"]["action"] == "added"
        assert FavouriteVacancy.objects.filter(
            candidate=self.candidate,
            vacancy=self.vacancy_1,
        ).exists()

        remove_response = self.client.post(self.toggle_url(self.vacancy_1.id), format="json")
        assert remove_response.status_code == status.HTTP_200_OK
        assert remove_response.json()["data"]["is_favourite"] is False
        assert remove_response.json()["data"]["action"] == "removed"
        assert not FavouriteVacancy.objects.filter(
            candidate=self.candidate,
            vacancy=self.vacancy_1,
        ).exists()

    def test_toggle_favourite_requires_candidate(self):
        unauthenticated_response = self.client.post(self.toggle_url(self.vacancy_1.id), format="json")
        assert unauthenticated_response.status_code == status.HTTP_401_UNAUTHORIZED

        self.client.force_authenticate(user=self.recruiter)
        recruiter_response = self.client.post(self.toggle_url(self.vacancy_1.id), format="json")
        assert recruiter_response.status_code == status.HTTP_403_FORBIDDEN

    def test_toggle_favourite_returns_not_found_for_invalid_vacancy(self):
        self.client.force_authenticate(user=self.candidate)
        response = self.client.post(
            self.toggle_url("11111111-1111-1111-1111-111111111111"),
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_favourites_returns_only_authenticated_candidate_favourites(self):
        FavouriteVacancy.objects.create(candidate=self.candidate, vacancy=self.vacancy_1)
        FavouriteVacancy.objects.create(candidate=self.other_candidate, vacancy=self.vacancy_2)

        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.list_url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == str(self.vacancy_1.id)
        assert data[0]["is_favourite"] is True

    def test_vacancy_list_and_detail_include_is_favourite_for_candidate(self):
        FavouriteVacancy.objects.create(candidate=self.candidate, vacancy=self.vacancy_1)

        self.client.force_authenticate(user=self.candidate)
        list_response = self.client.get(self.vacancy_list_url)
        assert list_response.status_code == status.HTTP_200_OK
        vacancy_items = list_response.json()["data"]
        vacancy_1_payload = next(item for item in vacancy_items if item["id"] == str(self.vacancy_1.id))
        assert vacancy_1_payload["is_favourite"] is True

        detail_response = self.client.get(self.vacancy_detail_url(self.vacancy_1.id))
        assert detail_response.status_code == status.HTTP_200_OK
        assert detail_response.json()["data"]["is_favourite"] is True

    def test_vacancy_detail_has_is_favourite_false_for_anonymous(self):
        response = self.client.get(self.vacancy_detail_url(self.vacancy_1.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["is_favourite"] is False


class VacancyLanguageTests(APITestCase):
    """
    Test suite for vacancy required languages feature.

    Covers:
    - Creating a vacancy with required languages
    - Updating a vacancy's required languages
    - Verifying vacancy list and detail responses include vacancy_languages
    - Duplicate language per vacancy is rejected
    - Invalid language ID is rejected
    - Invalid proficiency level is rejected
    """

    def setUp(self):
        self.client = APIClient()

        self.company = Company.objects.create(name="Lang Test Co", tin="555666777")
        _setup_pro_subscription(self.company)

        self.recruiter = Recruiter.objects.create_user(
            email="lang-recruiter@test.com",
            password="testpass123",
            company=self.company,
            is_recruiter=True,
        )

        self.lang_en = Language.objects.create(name="English", code="en")
        self.lang_ru = Language.objects.create(name="Russian", code="ru")

        self.create_url = reverse("create-vacancy")
        self.list_url = reverse("vacancy-list")

    def _create_vacancy_with_languages(self, languages_data=None):
        """Helper to create a vacancy via API with optional languages_data."""
        payload = {
            "title": "Software Engineer",
            "employment_type": "FULL_TIME",
            "salary_min": 1000,
            "salary_max": 3000,
        }
        if languages_data is not None:
            payload["languages_data"] = languages_data
        self.client.force_authenticate(user=self.recruiter)
        return self.client.post(self.create_url, payload, format="json")

    def test_create_vacancy_with_required_languages(self):
        """Creating a vacancy with languages_data stores and returns them."""
        response = self._create_vacancy_with_languages(
            languages_data=[
                {"language_id": str(self.lang_en.id), "level": "B2"},
                {"language_id": str(self.lang_ru.id), "level": "B1"},
            ]
        )

        assert response.status_code == status.HTTP_201_CREATED, response.json()
        data = response.json()["data"]

        langs = data["vacancy_languages"]
        assert len(langs) == 2
        lang_codes = {l["language_code"] for l in langs}
        assert lang_codes == {"en", "ru"}
        levels = {l["level"] for l in langs}
        assert levels == {"B2", "B1"}

        # DB check
        vacancy_id = data["id"]
        assert VacancyLanguage.objects.filter(vacancy_id=vacancy_id).count() == 2

    def test_create_vacancy_without_languages_returns_empty_list(self):
        """Vacancy created without languages_data has an empty vacancy_languages list."""
        response = self._create_vacancy_with_languages()

        assert response.status_code == status.HTTP_201_CREATED, response.json()
        data = response.json()["data"]
        assert data["vacancy_languages"] == []

    def test_retrieve_vacancy_includes_vacancy_languages(self):
        """GET /vacancies/<id>/ response includes vacancy_languages."""
        vacancy = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="DevOps Engineer",
            is_active=True,
        )
        VacancyLanguage.objects.create(vacancy=vacancy, language=self.lang_en, level="C1")

        url = reverse("retrieve-vacancy", kwargs={"id": str(vacancy.id)})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        langs = response.json()["data"]["vacancy_languages"]
        assert len(langs) == 1
        assert langs[0]["language_code"] == "en"
        assert langs[0]["level"] == "C1"

    def test_vacancy_list_includes_vacancy_languages(self):
        """GET /vacancies/ list response includes vacancy_languages for each vacancy."""
        vacancy = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="QA Engineer",
            is_active=True,
        )
        VacancyLanguage.objects.create(vacancy=vacancy, language=self.lang_ru, level="A2")

        response = self.client.get(self.list_url)

        assert response.status_code == status.HTTP_200_OK
        results = response.json()["data"]
        vacancy_data = next(v for v in results if v["id"] == str(vacancy.id))
        langs = vacancy_data["vacancy_languages"]
        assert len(langs) == 1
        assert langs[0]["language_code"] == "ru"
        assert langs[0]["level"] == "A2"

    def test_update_vacancy_replaces_languages(self):
        """PATCH /vacancies/<id>/update/ with languages_data replaces existing entries."""
        vacancy = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="Data Analyst",
            is_active=True,
        )
        VacancyLanguage.objects.create(vacancy=vacancy, language=self.lang_ru, level="B1")

        update_url = reverse("update-vacancy", kwargs={"id": str(vacancy.id)})
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            update_url,
            {"languages_data": [{"language_id": str(self.lang_en.id), "level": "C2"}]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.json()
        langs = response.json()["data"]["vacancy_languages"]
        assert len(langs) == 1
        assert langs[0]["language_code"] == "en"
        assert langs[0]["level"] == "C2"
        # Old entry deleted
        assert not VacancyLanguage.objects.filter(vacancy=vacancy, language=self.lang_ru).exists()

    def test_update_vacancy_without_languages_data_keeps_existing(self):
        """PATCH without languages_data field leaves existing languages unchanged."""
        vacancy = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="Product Manager",
            is_active=True,
        )
        VacancyLanguage.objects.create(vacancy=vacancy, language=self.lang_en, level="B2")

        update_url = reverse("update-vacancy", kwargs={"id": str(vacancy.id)})
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            update_url,
            {"title": "Senior Product Manager"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.json()
        # Languages unchanged
        assert VacancyLanguage.objects.filter(vacancy=vacancy).count() == 1
        langs = response.json()["data"]["vacancy_languages"]
        assert len(langs) == 1
        assert langs[0]["language_code"] == "en"

    def test_invalid_language_id_returns_400(self):
        """languages_data with a non-existent language_id returns 400."""
        response = self._create_vacancy_with_languages(
            languages_data=[{"language_id": 999999, "level": "B2"}]
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_proficiency_level_returns_400(self):
        """languages_data with an invalid level returns 400."""
        response = self._create_vacancy_with_languages(
            languages_data=[{"language_id": str(self.lang_en.id), "level": "INVALID"}]
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_language_id_returns_400(self):
        """languages_data entry without language_id returns 400."""
        response = self._create_vacancy_with_languages(
            languages_data=[{"level": "B2"}]
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_level_returns_400(self):
        """languages_data entry without level returns 400."""
        response = self._create_vacancy_with_languages(
            languages_data=[{"language_id": str(self.lang_en.id)}]
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
