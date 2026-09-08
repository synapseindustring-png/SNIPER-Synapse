from django.contrib import admin

from .models import Signal, SignalDetection, SignalRule


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ("signal_type", "company", "product", "observed_at", "active")
    list_filter = ("signal_type", "product", "active")
    search_fields = ("company__cnpj", "company__legal_name", "title", "evidence_excerpt")
    readonly_fields = ("id", "detected_at", "updated_at")


@admin.register(SignalRule)
class SignalRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "signal_type", "product", "version", "match_mode", "active")
    list_filter = ("product", "match_mode", "active")
    search_fields = ("name", "key", "signal_type")


@admin.register(SignalDetection)
class SignalDetectionAdmin(admin.ModelAdmin):
    list_display = ("signal", "rule", "source_record", "field_name", "detected_at")
    search_fields = ("signal__company__cnpj", "signal__company__legal_name", "evidence_excerpt")
    readonly_fields = ("signal", "rule", "source_record", "field_name", "matched_terms", "evidence_excerpt", "detected_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
