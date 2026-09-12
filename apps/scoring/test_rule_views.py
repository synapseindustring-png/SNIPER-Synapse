from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company

from .engine import ScoringConfigurationError
from .models import RuleSet, ScoreSnapshot
from .services import clone_active_rule_set, publish_rule_set, simulate_rule_set


class RuleManagementTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="rules-admin", password="secret", is_staff=True
        )
        self.regular = get_user_model().objects.create_user(
            username="sales-rules", password="secret"
        )
        self.company = Company.objects.create(
            legal_name="Indústria de Simulação",
            company_type=Company.Type.INDUSTRY,
            registration_status=Company.RegistrationStatus.ACTIVE,
        )

    def test_management_pages_are_staff_only(self):
        self.client.force_login(self.regular)
        self.assertEqual(self.client.get(reverse("rule-set-list")).status_code, 404)

        self.client.force_login(self.staff)
        response = self.client.get(reverse("rule-set-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Regras de scoring")

    def test_clone_copies_rules_without_changing_published_version(self):
        active = RuleSet.objects.get(target=RuleSet.Target.INDUSTRY, active=True)
        original_rule_ids = set(active.rules.values_list("id", flat=True))

        draft, created = clone_active_rule_set(
            target=RuleSet.Target.INDUSTRY, user=self.staff
        )
        same_draft, created_again = clone_active_rule_set(
            target=RuleSet.Target.INDUSTRY, user=self.staff
        )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(same_draft, draft)
        self.assertEqual(draft.version, active.version + 1)
        self.assertEqual(draft.rules.count(), active.rules.count())
        self.assertFalse(
            original_rule_ids.intersection(draft.rules.values_list("id", flat=True))
        )
        active.refresh_from_db()
        self.assertTrue(active.active)
        self.assertEqual(active.status, RuleSet.Status.PUBLISHED)

    def test_invalid_draft_cannot_be_published(self):
        draft, _ = clone_active_rule_set(
            target=RuleSet.Target.INDUSTRY, user=self.staff
        )
        draft.formula = {"ICP": "0.25"}
        draft.save(update_fields=("formula",))

        with self.assertRaises(ScoringConfigurationError):
            publish_rule_set(draft, user=self.staff)

        draft.refresh_from_db()
        self.assertEqual(draft.status, RuleSet.Status.DRAFT)
        self.assertFalse(draft.active)

    def test_publish_retires_old_version_but_preserves_its_snapshot(self):
        active = RuleSet.objects.get(target=RuleSet.Target.INDUSTRY, active=True)
        snapshot = ScoreSnapshot.objects.create(
            company=self.company,
            rule_set=active,
            as_of=timezone.now(),
            dimensions={},
            priority="0",
            calculated_classification="COLD",
        )
        draft, _ = clone_active_rule_set(
            target=RuleSet.Target.INDUSTRY, user=self.staff
        )

        published = publish_rule_set(draft, user=self.staff)

        active.refresh_from_db()
        snapshot.refresh_from_db()
        self.assertEqual(active.status, RuleSet.Status.RETIRED)
        self.assertFalse(active.active)
        self.assertEqual(published.status, RuleSet.Status.PUBLISHED)
        self.assertTrue(published.active)
        self.assertEqual(snapshot.rule_set, active)

    def test_simulation_uses_draft_without_persisting_snapshot(self):
        draft, _ = clone_active_rule_set(
            target=RuleSet.Target.INDUSTRY, user=self.staff
        )
        before = ScoreSnapshot.objects.count()

        result = simulate_rule_set(draft, self.company)

        self.assertGreaterEqual(result.priority, 0)
        self.assertEqual(ScoreSnapshot.objects.count(), before)
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("rule-set-simulate", args=[draft.pk]),
            {"company": self.company.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resultado não persistido")
        self.assertEqual(ScoreSnapshot.objects.count(), before)
