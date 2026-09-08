from django.contrib import admin

from .models import Company, CompanyCnae


class CompanyCnaeInline(admin.TabularInline):
    model = CompanyCnae
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "trade_name",
        "legal_name",
        "cnpj",
        "company_type",
        "registration_status",
        "state",
        "commercial_status",
    )
    list_filter = ("company_type", "registration_status", "commercial_status", "state")
    search_fields = ("cnpj", "legal_name", "trade_name", "website_domain")
    readonly_fields = ("id", "created_at", "updated_at", "last_enriched_at", "deleted_at")
    inlines = (CompanyCnaeInline,)
