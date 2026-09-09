import uuid

from django.db import models


class WebsitePage(models.Model):
    class PageType(models.TextChoices):
        HOME = "HOME", "Inicial"
        ABOUT = "ABOUT", "Sobre"
        PRODUCT = "PRODUCT", "Produto/solução"
        CASE = "CASE", "Caso/cliente"
        NEWS = "NEWS", "Notícia/blog"
        CAREERS = "CAREERS", "Carreiras"
        OTHER = "OTHER", "Outra"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="website_pages"
    )
    source_record = models.OneToOneField(
        "sources.SourceRecord", on_delete=models.PROTECT, related_name="website_page"
    )
    url = models.URLField(max_length=1000)
    page_type = models.CharField(max_length=16, choices=PageType.choices, default=PageType.OTHER)
    title = models.CharField(max_length=500, blank=True)
    extracted_text = models.TextField()
    content_hash = models.CharField(max_length=64)
    http_status = models.PositiveSmallIntegerField()
    content_type = models.CharField(max_length=120)
    observed_at = models.DateTimeField()
    collected_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    current = models.BooleanField(default=True)

    class Meta:
        ordering = ("-observed_at", "url")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "url", "content_hash"),
                name="unique_company_page_content",
            )
        ]
        indexes = [
            models.Index(fields=("company", "current", "observed_at"), name="page_company_current_idx")
        ]

    def __str__(self):
        return f"{self.company} · {self.title or self.url}"


class JobPosting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="job_postings"
    )
    source_record = models.ForeignKey(
        "sources.SourceRecord", on_delete=models.PROTECT, related_name="job_postings"
    )
    fingerprint = models.CharField(max_length=64)
    external_id = models.CharField(max_length=500, blank=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=500, blank=True)
    employment_type = models.CharField(max_length=120, blank=True)
    url = models.URLField(max_length=1000, blank=True)
    published_on = models.DateField(null=True, blank=True)
    valid_through = models.DateField(null=True, blank=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-published_on", "-last_seen_at", "title")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "fingerprint"), name="unique_company_job_fingerprint"
            )
        ]
        indexes = [
            models.Index(
                fields=("company", "active", "published_on"), name="job_company_active_idx"
            )
        ]

    def __str__(self):
        return f"{self.company} · {self.title}"


class JobPostingReview(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        MATCHED = "MATCHED", "Vinculada"
        DISMISSED = "DISMISSED", "Descartada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(
        "sources.Source", on_delete=models.PROTECT, related_name="job_posting_reviews"
    )
    candidate_fingerprint = models.CharField(max_length=64)
    external_id = models.CharField(max_length=500, blank=True)
    company_name = models.CharField(max_length=500, blank=True)
    company_domain = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=500)
    location = models.CharField(max_length=500, blank=True)
    url = models.URLField(max_length=1000, blank=True)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    suggested_company = models.ForeignKey(
        "companies.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_posting_reviews",
    )
    metadata = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()

    class Meta:
        ordering = ("status", "-last_seen_at")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "candidate_fingerprint"),
                name="unique_source_job_review_candidate",
            )
        ]
        indexes = [
            models.Index(fields=("status", "last_seen_at"), name="job_review_status_idx")
        ]

    def __str__(self):
        return f"{self.title} · {self.company_name or 'empresa não identificada'}"
