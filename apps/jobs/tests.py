from django.test import TestCase

from .models import Job
from .services import claim_next_job, mark_succeeded


class JobServicesTests(TestCase):
    def test_claim_and_complete_job(self):
        queued = Job.objects.create(type=Job.Type.NOOP)

        claimed = claim_next_job("test-worker", 30)

        self.assertEqual(claimed.id, queued.id)
        self.assertEqual(claimed.status, Job.Status.RUNNING)
        self.assertEqual(claimed.attempt_count, 1)
        self.assertEqual(claimed.attempts.count(), 1)

        mark_succeeded(claimed.id)
        queued.refresh_from_db()
        self.assertEqual(queued.status, Job.Status.SUCCEEDED)
        self.assertIsNotNone(queued.finished_at)

