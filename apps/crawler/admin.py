from django.contrib import admin

from .models import WebsitePage


@admin.register(WebsitePage)
class WebsitePageAdmin(admin.ModelAdmin):
    list_display = ("company", "page_type", "title", "http_status", "current", "observed_at")
    list_filter = ("page_type", "current", "http_status")
    search_fields = ("company__cnpj", "company__legal_name", "title", "url", "extracted_text")
    readonly_fields = ("id", "source_record", "content_hash", "collected_at", "last_seen_at")
