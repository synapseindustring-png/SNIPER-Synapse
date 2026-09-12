from django.contrib import admin

from .models import (
    DiscoveryQuery,
    GeographicRegion,
    Initiative,
    MarketSegment,
    Municipality,
    OpportunitySearch,
    QueryResult,
    QueryRun,
    SourceCoverage,
)


@admin.register(DiscoveryQuery)
class DiscoveryQueryAdmin(admin.ModelAdmin):
    list_display = ("name", "entity_target", "created_by", "active", "created_at")
    list_filter = ("entity_target", "active")
    search_fields = ("name", "fingerprint")
    readonly_fields = ("normalized_filters", "fingerprint", "schema_version", "created_at", "updated_at")


@admin.register(QueryRun)
class QueryRunAdmin(admin.ModelAdmin):
    list_display = ("id", "query", "status", "records_processed", "records_matched", "created_at")
    list_filter = ("status",)
    readonly_fields = ("id", "created_at")


admin.site.register(QueryResult)


@admin.register(SourceCoverage)
class SourceCoverageAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "dataset_reference",
        "record_count",
        "query_run",
        "completed_at",
        "expires_at",
    )
    list_filter = ("source", "dataset_reference")
    search_fields = ("scope_hash",)
    readonly_fields = tuple(field.name for field in SourceCoverage._meta.fields)


@admin.register(GeographicRegion)
class GeographicRegionAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "kind", "active")
    list_filter = ("state", "kind", "active")
    search_fields = ("name", "code")
    filter_horizontal = ("municipalities",)


@admin.register(Municipality)
class MunicipalityAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "ibge_code", "intermediate_name")
    list_filter = ("state",)
    search_fields = ("name", "ibge_code")


admin.site.register(MarketSegment)
admin.site.register(Initiative)
admin.site.register(OpportunitySearch)
