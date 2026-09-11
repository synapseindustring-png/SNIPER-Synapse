import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.sources.cnpj.complements import CnpjCompanyReader, CnpjSimplesReader


class CnpjComplementReaderTests(SimpleTestCase):
    def make_zip(self, content: str, member_name: str) -> Path:
        temporary = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        temporary.close()
        path = Path(temporary.name)
        self.addCleanup(path.unlink, missing_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member_name, content.encode("latin1"))
        return path

    def test_company_reader_keeps_only_target_basics(self):
        path = self.make_zip(
            '99999999;IGNORADA;0000;00;0,00;00;\n'
            '11111111;ALIMENTOS MINAS SA;2062;49;150000,50;05;\n',
            "K3241.K03200Y0.D60810.EMPRECSV",
        )

        reader = CnpjCompanyReader(path, frozenset({"11111111"}))
        records = list(reader)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].legal_name, "ALIMENTOS MINAS SA")
        self.assertEqual(records[0].share_capital, "150000,50")
        self.assertEqual(reader.stats.rows_read, 2)
        self.assertEqual(reader.stats.rows_matched, 1)

    def test_simples_reader_stops_after_all_targets_are_found(self):
        path = self.make_zip(
            '11111111;S;20200101;;N;;\n'
            '99999999;N;;20210101;N;;\n',
            "F.K03200$W.SIMPLES.CSV.D60810",
        )

        reader = CnpjSimplesReader(path, frozenset({"11111111"}))
        records = list(reader)

        self.assertEqual([record.cnpj_basico for record in records], ["11111111"])
        self.assertEqual(reader.stats.rows_read, 1)

    def test_reader_rejects_empty_or_invalid_targets(self):
        path = self.make_zip('11111111;S;20200101;;N;;\n', "simples.csv")

        with self.assertRaisesMessage(ValueError, "At least one"):
            CnpjSimplesReader(path, frozenset())
        with self.assertRaisesMessage(ValueError, "8 digits"):
            CnpjSimplesReader(path, frozenset({"111"}))
