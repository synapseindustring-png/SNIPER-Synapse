from django.contrib import admin

from .models import Company, CompanyCnae, CompanyCorrection


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

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return tuple(field.name for field in self.model._meta.fields)
        return self.readonly_fields


@admin.register(CompanyCorrection)
class CompanyCorrectionAdmin(admin.ModelAdmin):
    list_display = ("company", "field_name", "corrected_by", "created_at")
    list_filter = ("field_name", "created_at")
    search_fields = ("company__cnpj", "company__legal_name", "justification")
    readonly_fields = tuple(field.name for field in CompanyCorrection._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
