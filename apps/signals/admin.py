from django.contrib import admin

from .models import Signal


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ("signal_type", "company", "product", "observed_at", "active")
    list_filter = ("signal_type", "product", "active")
    search_fields = ("company__cnpj", "company__legal_name", "title", "evidence_excerpt")
    readonly_fields = ("id", "detected_at", "updated_at")
