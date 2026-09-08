from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.companies.models import Company


class HealthViewsTests(TestCase):
    def test_live(self):
        response = Client().get(reverse("health-live"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ready(self):
        response = Client().get(reverse("health-ready"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_authentication(self):
        response = Client().get(reverse("dashboard"))
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("dashboard")}',
            fetch_redirect_response=False,
        )

    def test_dashboard_uses_persisted_company_count(self):
        user = get_user_model().objects.create_user(username="dashboard", password="secret")
        Company.objects.create(legal_name="Indústria teste", company_type=Company.Type.INDUSTRY)
        client = Client()
        client.force_login(user)

        response = client.get(reverse("dashboard"))

        self.assertEqual(response.context["industry_count"], 1)
        self.assertContains(response, "Indústria teste", count=0)
