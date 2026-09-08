from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company, CompanyCnae
from apps.signals.models import Signal
from apps.jobs.models import Job
from apps.jobs.services import execute_job

from .engine import ScoringConfigurationError, calculate_score, condition_matches, decay_multiplier
from .models import RuleSet, ScoreOverride, ScoreSnapshot, ScoringRule


class ScoringEngineTests(TestCase):
    def setUp(self):
        self.as_of = timezone.now().replace(microsecond=0)
        self.company = Company.objects.create(
            legal_name="Indústria Alfa",
            company_type=Company.Type.INDUSTRY,
            registration_status=Company.RegistrationStatus.ACTIVE,
            state="MG",
        )
        CompanyCnae.objects.create(company=self.company, code="1011201", is_primary=True, observed_at=self.as_of)
        self.rule_set = RuleSet.objects.get(target=RuleSet.Target.INDUSTRY, active=True)
        self.rule_set.rules.all().delete()

    def add_rule(self, *, key, dimension="ICP", points="20", condition=None, **kwargs):
        return ScoringRule.objects.create(
            rule_set=self.rule_set,
            key=key,
            name=key,
            dimension=dimension,
            points=points,
            condition=condition or {"field": "registration_status", "op": "EQ", "value": "ACTIVE"},
            **kwargs,
        )

    def test_compound_conditions_and_invalid_fields(self):
        facts = {"state": "MG", "cnaes": ["1011201"], "signal_types": set()}
        self.assertTrue(condition_matches({"all": [{"field": "state", "op": "EQ", "value": "MG"}, {"field": "cnaes", "op": "HAS_CNAE_PREFIX", "value": "10"}]}, facts))
        with self.assertRaises(ScoringConfigurationError):
            condition_matches({"field": "password", "op": "EQ", "value": "x"}, facts)

    def test_decay_boundaries(self):
        rule = self.add_rule(key="decay", decay_policy=ScoringRule.DecayPolicy.AGE_BUCKETS)
        expected = {30: "1.00", 31: "0.80", 60: "0.80", 61: "0.60", 91: "0.30", 181: "0.10"}
        for age, multiplier in expected.items():
            with self.subTest(age=age):
                self.assertEqual(decay_multiplier(rule, self.as_of - timedelta(days=age), self.as_of), Decimal(multiplier))

    def test_score_is_deterministic_explainable_and_uses_signal_decay(self):
        self.add_rule(key="active", points="40")
        self.add_rule(key="cmms", dimension="CMMS", points="50", condition={"field": "signal_types", "op": "HAS_SIGNAL", "value": "pcm"}, decay_policy=ScoringRule.DecayPolicy.AGE_BUCKETS)
        Signal.objects.create(company=self.company, signal_type="pcm", product=Signal.Product.CMMS, title="Vaga de PCM", evidence_excerpt="Planejador de manutenção", evidence_hash="a" * 64, observed_at=self.as_of - timedelta(days=45))

        first = calculate_score(self.company, as_of=self.as_of, rule_set=self.rule_set)
        second = calculate_score(self.company, as_of=self.as_of, rule_set=self.rule_set)

        self.assertEqual(first.priority, Decimal("28.000"))
        self.assertEqual(first.priority, second.priority)
        self.assertEqual(first.dimensions, second.dimensions)
        self.assertEqual(first.best_product, "CMMS")
        contribution = first.contributions.get(rule__key="cmms")
        self.assertEqual(contribution.decay_multiplier, Decimal("0.80000"))
        self.assertEqual(contribution.effective_points, Decimal("40.000"))
        self.assertEqual(contribution.evidence["title"], "Vaga de PCM")

    def test_group_cap_and_dimension_clamp(self):
        self.add_rule(key="one", points="80", group_key="structure", group_cap="100")
        self.add_rule(key="two", points="80", group_key="structure", group_cap="100")
        snapshot = calculate_score(self.company, as_of=self.as_of, rule_set=self.rule_set)
        self.assertEqual(snapshot.dimensions["ICP"], "100.000")
        self.assertEqual(list(snapshot.contributions.values_list("effective_points", flat=True)), [Decimal("80.000"), Decimal("20.000")])

    def test_critical_rule_precedes_numeric_classification(self):
        self.company.registration_status = Company.RegistrationStatus.INACTIVE
        self.company.save(update_fields=("registration_status", "updated_at"))
        self.add_rule(key="inactive", points="100", condition={"field": "registration_status", "op": "EQ", "value": "INACTIVE"}, critical_outcome=ScoringRule.CriticalOutcome.DISQUALIFIED)
        snapshot = calculate_score(self.company, as_of=self.as_of, rule_set=self.rule_set)
        self.assertEqual(snapshot.calculated_classification, "DISQUALIFIED")

    def test_snapshot_is_immutable_and_override_survives_recalculation(self):
        self.add_rule(key="active")
        snapshot = calculate_score(self.company, as_of=self.as_of, rule_set=self.rule_set)
        user = get_user_model().objects.create_user(username="reviewer")
        override = ScoreOverride.objects.create(company=self.company, snapshot=snapshot, classification="WATCH", reason="Revisão comercial", created_by=user)
        calculate_score(self.company, as_of=self.as_of + timedelta(minutes=1), rule_set=self.rule_set)
        self.assertTrue(ScoreOverride.objects.get(pk=override.pk).active)
        snapshot.priority = 99
        with self.assertRaises(ValidationError):
            snapshot.save()

    def test_calculate_score_job_creates_snapshot(self):
        self.add_rule(key="active")
        job = Job.objects.create(
            type=Job.Type.CALCULATE_SCORE,
            payload={
                "company_id": str(self.company.pk),
                "rule_set_id": str(self.rule_set.pk),
                "as_of": self.as_of.isoformat(),
            },
        )

        execute_job(job)

        self.assertEqual(ScoreSnapshot.objects.filter(company=self.company).count(), 1)
        job.refresh_from_db()
        self.assertEqual(job.records_success, 1)
