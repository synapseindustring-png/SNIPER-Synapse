import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.sources.cnpj import (
    CnpjEstablishmentFilter,
    CnpjEstablishmentReader,
    CnpjLayoutError,
)


FIXTURE = Path(__file__).parent / "fixtures" / "establishments.csv"


class CnpjEstablishmentReaderTests(SimpleTestCase):
    def make_zip(self, source: Path = FIXTURE) -> Path:
        temporary = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        temporary.close()
        path = Path(temporary.name)
        self.addCleanup(path.unlink, missing_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(source, arcname="K3241.K03200Y0.D60810.ESTABELE")
        return path

    def test_filters_active_mg_food_manufacturers_while_streaming_zip(self):
        reader = CnpjEstablishmentReader(
            self.make_zip(),
            CnpjEstablishmentFilter(
                registration_statuses=frozenset({"02"}),
                states=frozenset({"mg"}),
                cnae_prefixes=("10",),
            ),
        )

        matches = list(reader)

        self.assertEqual([item.cnpj for item in matches], ["11111111000191"])
        self.assertEqual(matches[0].email, "contato@example.com")
        self.assertEqual(reader.stats.rows_read, 4)
        self.assertEqual(reader.stats.rows_matched, 1)
        self.assertEqual(reader.stats.rows_invalid, 0)

    def test_can_include_secondary_cnaes(self):
        reader = CnpjEstablishmentReader(
            self.make_zip(),
            CnpjEstablishmentFilter(
                registration_statuses=frozenset({"02"}),
                states=frozenset({"MG"}),
                cnae_codes=frozenset({"1091102"}),
                include_secondary_cnaes=True,
            ),
        )

        self.assertEqual(
            [item.cnpj for item in reader],
            ["11111111000191", "44444444000134"],
        )

    def test_rejects_unbounded_scan_by_default(self):
        with self.assertRaisesMessage(ValueError, "selective"):
            CnpjEstablishmentReader(self.make_zip(), CnpjEstablishmentFilter())

    def test_reports_invalid_layout(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as malformed:
            malformed.write(b'"too";"short"\n')
            source = Path(malformed.name)
        self.addCleanup(source.unlink, missing_ok=True)
        reader = CnpjEstablishmentReader(
            self.make_zip(source),
            CnpjEstablishmentFilter(states=frozenset({"MG"})),
        )

        with self.assertRaisesMessage(CnpjLayoutError, "expected 30 columns"):
            list(reader)
