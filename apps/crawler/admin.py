from django.contrib import admin

from .models import JobPosting, JobPostingReview, WebsitePage


@admin.register(WebsitePage)
class WebsitePageAdmin(admin.ModelAdmin):
    list_display = ("company", "page_type", "title", "http_status", "current", "observed_at")
    list_filter = ("page_type", "current", "http_status")
    search_fields = ("company__cnpj", "company__legal_name", "title", "url", "extracted_text")
    readonly_fields = ("id", "source_record", "content_hash", "collected_at", "last_seen_at")


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ("company", "title", "location", "published_on", "active", "last_seen_at")
    list_filter = ("active", "employment_type", "published_on")
    search_fields = ("company__cnpj", "company__legal_name", "title", "location", "description")
    readonly_fields = ("id", "source_record", "fingerprint", "first_seen_at", "last_seen_at")


@admin.register(JobPostingReview)
class JobPostingReviewAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "company_name",
        "source",
        "status",
        "suggested_company",
        "reviewed_by",
        "last_seen_at",
    )
    list_filter = ("status", "source")
    search_fields = ("title", "company_name", "company_domain", "external_id")
    readonly_fields = (
        "id",
        "source",
        "candidate_fingerprint",
        "status",
        "external_id",
        "company_name",
        "company_domain",
        "title",
        "location",
        "employment_type",
        "url",
        "published_on",
        "valid_through",
        "reason",
        "suggested_company",
        "metadata",
        "job_posting",
        "reviewed_by",
        "reviewed_at",
        "resolution_note",
        "first_seen_at",
        "last_seen_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
