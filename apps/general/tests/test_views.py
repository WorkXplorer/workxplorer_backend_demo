from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.general.models import Avatar
from apps.authentication.models import Company


class ProfilePictureListAPIViewTests(APITestCase):
    def test_list_active_avatars_successfully(self):
        image_file1 = SimpleUploadedFile(
            "avatar1.png", b"image content", content_type="image/png"
        )
        image_file2 = SimpleUploadedFile(
            "avatar2.png", b"image content", content_type="image/png"
        )

        Avatar.objects.create(image=image_file1, is_active=True)
        Avatar.objects.create(image=image_file2, is_active=True)

        url = reverse("profile-avatars")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["data"]), 2)

    def test_list_excludes_inactive_avatars(self):
        active_avatar = SimpleUploadedFile(
            "active.png", b"image content", content_type="image/png"
        )
        inactive_avatar = SimpleUploadedFile(
            "inactive.png", b"image content", content_type="image/png"
        )

        Avatar.objects.create(image=active_avatar, is_active=True)
        Avatar.objects.create(image=inactive_avatar, is_active=False)

        url = reverse("profile-avatars")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["data"]), 1)

    def test_list_empty_avatars(self):
        url = reverse("profile-avatars")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["data"]), 0)


class InActiveCompanyAPIViewTests(APITestCase):
    def test_list_inactive_companies_successfully(self):
        Company.objects.create(
            name="Inactive Company 1", tin="111111111", is_active=False
        )
        Company.objects.create(
            name="Inactive Company 2", tin="222222222", is_active=False
        )

        url = reverse("inactive-companies")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["data"]), 2)

    def test_list_excludes_active_companies(self):
        Company.objects.create(name="Active Company", tin="333333333", is_active=True)
        Company.objects.create(
            name="Inactive Company", tin="444444444", is_active=False
        )

        url = reverse("inactive-companies")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["name"], "Inactive Company")

    def test_list_empty_inactive_companies(self):
        url = reverse("inactive-companies")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["data"]), 0)


class CompanyConfirmAPIViewTests(APITestCase):
    def test_get_method_not_allowed(self):
        url = reverse("confirm-company")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_confirm_companies_with_empty_ids(self):
        url = reverse("confirm-company")
        data = {"company_ids": [], "is_active": True}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()["data"]
        self.assertEqual(payload["sent_emails"], [])
        self.assertEqual(payload["failed_emails"], [])
        self.assertEqual(payload["not_found_company_ids"], [])
        self.assertEqual(payload["recruiters_missing_email"], [])

    def test_confirm_companies_missing_company_ids(self):
        url = reverse("confirm-company")
        data = {"is_active": True}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())

    def test_confirm_companies_missing_is_active(self):
        url = reverse("confirm-company")
        company = Company.objects.create(name="Test", tin="555555555")
        data = {"company_ids": [str(company.id)]}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())

    def test_confirm_companies_with_invalid_company_ids_type(self):
        url = reverse("confirm-company")
        data = {"company_ids": "not-a-list", "is_active": True}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_companies_with_nonexistent_ids(self):
        url = reverse("confirm-company")
        data = {
            "company_ids": ["11111111-1111-1111-1111-111111111111"],
            "is_active": True,
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()["data"]
        self.assertIn("not_found_company_ids", payload)
        self.assertEqual(len(payload["not_found_company_ids"]), 1)
