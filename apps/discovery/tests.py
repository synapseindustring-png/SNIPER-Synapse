from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import DiscoveryQuery, fingerprint_filters, normalize_filters


class DiscoveryQueryFingerprintTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="admin")

    def test_equivalent_filters_have_same_fingerprint(self):
        first = {"states": ["mg", "SP"], "cnaes": ["10.91-1-02", "22"], "keyword": "  pcm   industrial "}
        second = {"keyword": "pcm industrial", "cnaes": ["22", "1091102"], "states": ["SP", "MG"]}

        self.assertEqual(normalize_filters(first), normalize_filters(second))
        self.assertEqual(fingerprint_filters(first), fingerprint_filters(second))

    def test_same_user_cannot_duplicate_equivalent_query(self):
        DiscoveryQuery.objects.create(
            name="Alimentos MG",
            entity_target=DiscoveryQuery.EntityTarget.INDUSTRY,
            filters={"states": ["MG"], "cnaes": ["10"]},
            created_by=self.user,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            DiscoveryQuery.objects.create(
                name="Consulta equivalente",
                entity_target=DiscoveryQuery.EntityTarget.INDUSTRY,
                filters={"cnaes": ["10"], "states": ["mg"]},
                created_by=self.user,
            )
