from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company
from apps.jobs.models import Job
from apps.sources.models import Source

from .models import JobPosting, JobPostingReview
from .reviews import JobReviewResolutionError, approve_job_review, dismiss_job_review


class JobReviewTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="reviewer", password="secret", is_staff=True
        )
        self.regular_user = get_user_model().objects.create_user(
            username="sales", password="secret"
        )
        self.company = Company.objects.create(
            cnpj="11222333000144",
            legal_name="Indústria Alfa S.A.",
            trade_name="Indústria Alfa",
            company_type=Company.Type.INDUSTRY,
            registration_status=Company.RegistrationStatus.ACTIVE,
        )
        self.source = Source.objects.get(key="jobs-fixture")
        now = timezone.now()
        self.review = JobPostingReview.objects.create(
            source=self.source,
            candidate_fingerprint="a" * 64,
            external_id="external-42",
            company_name="Industria Alfa",
            company_domain="ambiguous.example",
            title="Analista de PCM",
            location="Campinas/SP",
            employment_type="FULL_TIME",
            url="https://jobs.example/vagas/42",
            published_on=timezone.localdate(),
            reason="Domínio divergente",
            suggested_company=self.company,
            first_seen_at=now,
            last_seen_at=now,
        )

    def test_approval_persists_job_audit_and_enqueues_detection(self):
        with self.captureOnCommitCallbacks(execute=True):
            posting = approve_job_review(
                self.review.pk,
                company=self.company,
                user=self.staff,
                note="Domínio confirmado manualmente.",
            )

        self.review.refresh_from_db()
        self.assertEqual(self.review.status, JobPostingReview.Status.MATCHED)
        self.assertEqual(self.review.reviewed_by, self.staff)
        self.assertEqual(self.review.job_posting, posting)
        self.assertEqual(posting.title, self.review.title)
        self.assertTrue(Job.objects.filter(type=Job.Type.DETECT_SIGNALS).exists())
        with self.assertRaises(JobReviewResolutionError):
            approve_job_review(
                self.review.pk, company=self.company, user=self.staff, note="Repetida"
            )

    def test_dismissal_requires_pending_review_and_does_not_create_job(self):
        dismiss_job_review(self.review.pk, user=self.staff, reason="Empresa incorreta")

        self.review.refresh_from_db()
        self.assertEqual(self.review.status, JobPostingReview.Status.DISMISSED)
        self.assertEqual(self.review.resolution_note, "Empresa incorreta")
        self.assertFalse(JobPosting.objects.exists())
        with self.assertRaises(JobReviewResolutionError):
            dismiss_job_review(self.review.pk, user=self.staff, reason="Repetida")

    def test_review_pages_require_authentication_and_staff(self):
        url = reverse("job-review-list")
        response = self.client.get(url)
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={url}',
            fetch_redirect_response=False,
        )
        self.client.force_login(self.regular_user)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_staff_can_view_paginated_queue_and_candidate(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("job-review-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analista de PCM")
        self.assertEqual(response.context["page"].paginator.per_page, 50)

        detail = self.client.get(reverse("job-review-detail", args=[self.review.pk]))
        self.assertContains(detail, "Domínio divergente")
        self.assertContains(detail, str(self.company.pk))

    def test_staff_can_match_by_cnpj_and_action_is_audited(self):
        self.client.force_login(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("job-review-match", args=[self.review.pk]),
                {
                    "company_reference": "11.222.333/0001-44",
                    "note": "CNPJ validado na fonte.",
                },
            )

        self.assertRedirects(response, reverse("company-detail", args=[self.company.pk]))
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, JobPostingReview.Status.MATCHED)
        self.assertEqual(self.review.resolution_note, "CNPJ validado na fonte.")

    def test_invalid_match_and_empty_dismissal_do_not_resolve_review(self):
        self.client.force_login(self.staff)
        match_response = self.client.post(
            reverse("job-review-match", args=[self.review.pk]),
            {"company_reference": "Empresa inexistente", "note": "Teste"},
        )
        self.assertEqual(match_response.status_code, 400)
        self.assertContains(match_response, "Empresa não encontrada", status_code=400)

        dismiss_response = self.client.post(
            reverse("job-review-dismiss", args=[self.review.pk]), {"reason": ""}
        )
        self.assertRedirects(
            dismiss_response, reverse("job-review-detail", args=[self.review.pk])
        )
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, JobPostingReview.Status.PENDING)
