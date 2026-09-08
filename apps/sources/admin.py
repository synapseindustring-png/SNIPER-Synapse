from django.contrib import admin

from .models import CnpjDataset, CnpjDatasetFile, FieldObservation, Source, SourceRecord


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "enabled", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("key", "name", "adapter_path")


@admin.register(SourceRecord)
class SourceRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "external_id", "company", "observed_at")
    list_filter = ("source", "dataset_reference")
    search_fields = ("external_id", "company__cnpj", "company__legal_name")
    readonly_fields = tuple(field.name for field in SourceRecord._meta.fields)


@admin.register(FieldObservation)
class FieldObservationAdmin(admin.ModelAdmin):
    list_display = ("company", "field_name", "source_record", "observed_at", "is_current")
    list_filter = ("field_name", "is_current", "source_record__source")
    search_fields = ("company__cnpj", "normalized_value")
    readonly_fields = tuple(field.name for field in FieldObservation._meta.fields)


class CnpjDatasetFileInline(admin.TabularInline):
    model = CnpjDatasetFile
    extra = 0


@admin.register(CnpjDataset)
class CnpjDatasetAdmin(admin.ModelAdmin):
    list_display = ("reference", "source", "status", "is_current", "discovered_at")
    list_filter = ("status", "is_current", "source")
    inlines = (CnpjDatasetFileInline,)
