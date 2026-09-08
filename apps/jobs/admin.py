from django.contrib import admin

from .models import Job, JobAttempt


class JobAttemptInline(admin.TabularInline):
    model = JobAttempt
    extra = 0
    readonly_fields = (
        "attempt_number",
        "worker_id",
        "started_at",
        "finished_at",
        "succeeded",
        "error_detail",
        "metrics",
    )
    can_delete = False


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "status", "priority", "attempt_count", "run_after")
    list_filter = ("type", "status")
    search_fields = ("id", "idempotency_key", "error_summary")
    readonly_fields = ("created_at", "updated_at", "started_at", "finished_at")
    inlines = (JobAttemptInline,)

