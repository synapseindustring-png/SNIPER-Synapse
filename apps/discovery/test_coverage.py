from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company
from apps.sources.models import Source

from .coverage import (
    find_valid_coverage,
    materialize_cached_run,
    record_source_coverage,
)
from .models import DiscoveryQuery, QueryResult, QueryRun


class SourceCoverageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="coverage-user")
        self.query = DiscoveryQuery.objects.create(
            name="Indústrias MG",
            entity_target=DiscoveryQuery.EntityTarget.INDUSTRY,
            filters={"states": ["MG"], "cnae_prefixes": ["10"]},
            created_by=self.user,
        )
        self.source = Source.objects.get(key="receita-cnpj")
        self.covered_run = QueryRun.objects.create(
            query=self.query,
            created_by=self.user,
            status=QueryRun.Status.SUCCEEDED,
            dataset_reference="2026-08",
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        self.companies = [
            Company.objects.create(
                cnpj=f"11111111000{index}9{index}",
                trade_name=f"INDÚSTRIA {index}",
                company_type=Company.Type.INDUSTRY,
                state="MG",
            )
            for index in (1, 2)
        ]
        for rank, company in enumerate(self.companies, start=1):
            QueryResult.objects.create(
                query_run=self.covered_run,
                company=company,
                source=self.source,
                rank=rank,
            )
        self.covered_run.records_matched = 2
        self.covered_run.save(update_fields=("records_matched",))
        self.coverage = record_source_coverage(
            source=self.source,
            query_run=self.covered_run,
        )

    def test_exact_equivalent_query_reuses_coverage_across_users(self):
        other_user = get_user_model().objects.create_user(username="other-coverage-user")
        equivalent = DiscoveryQuery.objects.create(
            name="Mesma busca",
            entity_target=DiscoveryQuery.EntityTarget.INDUSTRY,
            filters={"cnae_prefixes": ["10"], "states": ["mg"]},
            created_by=other_user,
        )

        found = find_valid_coverage(
            source=self.source,
            dataset_reference="2026-08",
            query=equivalent,
        )

        self.assertEqual(found, self.coverage)

    def test_expired_or_different_scope_is_not_reused(self):
        self.coverage.expires_at = timezone.now() - timedelta(seconds=1)
        self.coverage.save(update_fields=("expires_at",))
        different = DiscoveryQuery.objects.create(
            name="Outro CNAE",
            entity_target=DiscoveryQuery.EntityTarget.INDUSTRY,
            filters={"states": ["MG"], "cnae_prefixes": ["20"]},
            created_by=self.user,
        )

        self.assertIsNone(
            find_valid_coverage(
                source=self.source,
                dataset_reference="2026-08",
                query=self.query,
            )
        )
        self.coverage.expires_at = None
        self.coverage.save(update_fields=("expires_at",))
        self.assertIsNone(
            find_valid_coverage(
                source=self.source,
                dataset_reference="2026-08",
                query=different,
            )
        )

    def test_cached_materialization_respects_limit_without_copying_source_data(self):
        cached_run = materialize_cached_run(
            query=self.query,
            created_by=self.user,
            coverage=self.coverage,
            max_results=1,
        )

        self.assertEqual(cached_run.status, QueryRun.Status.PARTIAL)
        self.assertEqual(cached_run.records_processed, 0)
        self.assertEqual(cached_run.records_matched, 1)
        self.assertTrue(cached_run.coverage["cache_hit"])
        self.assertEqual(cached_run.results.get().company, self.companies[0])
