from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import Job
from .services import JobLeaseLost, claim_next_job, mark_succeeded, renew_job_lease


class JobServicesTests(TestCase):
    def test_claim_and_complete_job(self):
        queued = Job.objects.create(type=Job.Type.NOOP)

        claimed = claim_next_job("test-worker", 30)

        self.assertEqual(claimed.id, queued.id)
        self.assertEqual(claimed.status, Job.Status.RUNNING)
        self.assertEqual(claimed.attempt_count, 1)
        self.assertEqual(claimed.attempts.count(), 1)

        mark_succeeded(claimed.id, "test-worker")
        queued.refresh_from_db()
        self.assertEqual(queued.status, Job.Status.SUCCEEDED)
        self.assertIsNotNone(queued.finished_at)

    def test_heartbeat_renews_only_the_current_workers_lease(self):
        queued = Job.objects.create(type=Job.Type.NOOP)
        claimed = claim_next_job("worker-a", 30)
        original_expiration = claimed.lock_expires_at

        with self.assertRaisesMessage(ValueError, "positive"):
            renew_job_lease(claimed.id, "worker-a", 0)
        self.assertFalse(renew_job_lease(claimed.id, "worker-b", 60))
        self.assertTrue(renew_job_lease(claimed.id, "worker-a", 60))

        queued.refresh_from_db()
        self.assertGreater(queued.lock_expires_at, original_expiration)
        self.assertGreater(queued.heartbeat_at, claimed.heartbeat_at - timedelta(seconds=1))

    def test_stale_worker_cannot_complete_job_owned_by_another_worker(self):
        queued = Job.objects.create(type=Job.Type.NOOP)
        claimed = claim_next_job("worker-a", 30)
        Job.objects.filter(pk=claimed.pk).update(
            lock_owner="worker-b",
            lock_expires_at=timezone.now() + timedelta(seconds=30),
        )

        with self.assertRaises(JobLeaseLost):
            mark_succeeded(claimed.id, "worker-a")

        queued.refresh_from_db()
        self.assertEqual(queued.status, Job.Status.RUNNING)

    def test_worker_command_completes_job_while_maintaining_lease(self):
        queued = Job.objects.create(type=Job.Type.NOOP)

        call_command("run_worker", once=True, stdout=StringIO(), stderr=StringIO())

        queued.refresh_from_db()
        self.assertEqual(queued.status, Job.Status.SUCCEEDED)
        self.assertEqual(queued.attempt_count, 1)
