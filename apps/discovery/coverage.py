from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.sources.models import Source

from .models import DiscoveryQuery, QueryResult, QueryRun, SourceCoverage, fingerprint_filters


def coverage_scope(query: DiscoveryQuery) -> dict:
    return {
        "entity_target": query.entity_target,
        "filters": query.normalized_filters,
        "schema_version": query.schema_version,
    }


def coverage_scope_hash(query: DiscoveryQuery) -> str:
    return fingerprint_filters(coverage_scope(query))


def find_valid_coverage(
    *,
    source: Source,
    dataset_reference: str,
    query: DiscoveryQuery,
    at=None,
) -> SourceCoverage | None:
    at = at or timezone.now()
    return (
        SourceCoverage.objects.select_related("query_run")
        .filter(
            source=source,
            dataset_reference=dataset_reference,
            scope_hash=coverage_scope_hash(query),
            query_run__status=QueryRun.Status.SUCCEEDED,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=at))
        .first()
    )


@transaction.atomic
def record_source_coverage(
    *,
    source: Source,
    query_run: QueryRun,
    expires_at=None,
) -> SourceCoverage:
    if query_run.status != QueryRun.Status.SUCCEEDED or not query_run.dataset_reference:
        raise ValueError("Only successful runs with a dataset can become source coverage")
    scope = coverage_scope(query_run.query)
    coverage, _ = SourceCoverage.objects.update_or_create(
        source=source,
        dataset_reference=query_run.dataset_reference,
        scope_hash=coverage_scope_hash(query_run.query),
        defaults={
            "query_run": query_run,
            "scope": scope,
            "record_count": query_run.results.count(),
            "completed_at": query_run.finished_at or timezone.now(),
            "expires_at": expires_at,
        },
    )
    return coverage


@transaction.atomic
def materialize_cached_run(
    *,
    query: DiscoveryQuery,
    created_by,
    coverage: SourceCoverage,
    max_results: int,
) -> QueryRun:
    if max_results < 1 or not coverage.query_run_id:
        raise ValueError("Valid coverage and a positive result limit are required")
    source_results = list(
        coverage.query_run.results.select_related("company", "source")[: max_results + 1]
    )
    selected = source_results[:max_results]
    limit_reached = len(source_results) > max_results
    now = timezone.now()
    run = QueryRun.objects.create(
        query=query,
        created_by=created_by,
        status=QueryRun.Status.PARTIAL if limit_reached else QueryRun.Status.SUCCEEDED,
        dataset_reference=coverage.dataset_reference,
        records_processed=0,
        records_matched=len(selected),
        records_failed=0,
        started_at=now,
        finished_at=now,
        coverage={
            "complete": not limit_reached,
            "mode": "CACHE",
            "cache_hit": True,
            "source_coverage_id": coverage.pk,
            "source_record_count": coverage.record_count,
            "max_results": max_results,
            "limit_reached": limit_reached,
        },
    )
    QueryResult.objects.bulk_create(
        [
            QueryResult(
                query_run=run,
                company=result.company,
                source=result.source,
                rank=result.rank,
                matched_filters=result.matched_filters,
                is_new_company=False,
            )
            for result in selected
        ]
    )
    return run
