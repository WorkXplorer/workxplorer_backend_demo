from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.banners.models import BannerSlide, BannerClick
from apps.authentication.models import Candidate


class BannerSlideModelTests(TestCase):
    def test_create_slide(self):
        slide = BannerSlide.objects.create(
            slide_type=BannerSlide.SlideType.NEWS,
            title="Test Slide",
            body="Test body",
        )
        self.assertEqual(str(slide), "[NEWS] Test Slide (order=0)")

    def test_is_visible_active(self):
        slide = BannerSlide.objects.create(is_active=True)
        self.assertTrue(slide.is_visible)

    def test_is_visible_inactive(self):
        slide = BannerSlide.objects.create(is_active=False)
        self.assertFalse(slide.is_visible)


class BannerClickModelTests(TestCase):
    def test_create_click(self):
        click = BannerClick.objects.create(
            slide_type="NEWS", cta_url="https://example.com",
        )
        self.assertIsNotNone(click.clicked_at)


class BannerListAPITests(APITestCase):
    def test_accessible_without_auth(self):
        url = reverse("banner-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_returns_list(self):
        BannerSlide.objects.create(
            slide_type=BannerSlide.SlideType.NEWS,
            title="Welcome", is_active=True,
        )
        url = reverse("banner-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)


class BannerClickAPITests(APITestCase):
    def test_click_without_auth(self):
        url = reverse("banner-click")
        response = self.client.post(url, {"slide_type": "NEWS"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_click_with_auth(self):
        user = Candidate.objects.create_user(
            email="cand@test.com", password="pass", is_candidate=True,
        )
        self.client.force_authenticate(user=user)
        url = reverse("banner-click")
        response = self.client.post(url, {"slide_type": "NEWS"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(BannerClick.objects.count(), 1)