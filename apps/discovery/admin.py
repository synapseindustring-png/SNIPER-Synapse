from django.contrib import admin

from .models import DiscoveryQuery, QueryResult, QueryRun, SourceCoverage


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
admin.site.register(SourceCoverage)
