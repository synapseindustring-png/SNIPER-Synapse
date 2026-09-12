import json
from pathlib import Path

from django.db import migrations


SEGMENTS = (
    ("alimentos-bebidas", "Alimentos e bebidas", "INDUSTRY", ["10", "11"]),
    ("textil-couro", "Têxtil, vestuário e couro", "INDUSTRY", ["13", "14", "15"]),
    ("madeira-papel", "Madeira, celulose e papel", "INDUSTRY", ["16", "17"]),
    ("quimica-farmaceutica", "Química e farmacêutica", "INDUSTRY", ["20", "21"]),
    ("plasticos-borracha", "Plásticos e borracha", "INDUSTRY", ["22"]),
    ("metalurgia-metal", "Metalurgia e produtos de metal", "INDUSTRY", ["24", "25"]),
    ("eletronicos-eletricos", "Eletrônicos e equipamentos elétricos", "INDUSTRY", ["26", "27"]),
    ("maquinas-equipamentos", "Máquinas e equipamentos", "INDUSTRY", ["28"]),
    ("automotivo-transportes", "Automotivo e outros transportes", "INDUSTRY", ["29", "30"]),
    ("moveis-diversos", "Móveis e manufaturas diversas", "INDUSTRY", ["31", "32"]),
    ("mineracao", "Mineração e extração", "INDUSTRY", ["05", "06", "07", "08", "09"]),
    ("saneamento-reciclagem", "Saneamento e reciclagem", "INDUSTRY", ["36", "37", "38", "39"]),
    ("consultoria-gestao", "Consultoria de gestão", "PARTNER", ["7020"]),
    ("engenharia", "Engenharia", "PARTNER", ["7112"]),
    ("tecnologia", "Tecnologia e software", "PARTNER", ["62"]),
    ("manutencao-instalacao", "Manutenção e instalação industrial", "PARTNER", ["33"]),
    ("automacao-equipamentos", "Automação e equipamentos", "PARTNER", ["4651", "4663"]),
)

INITIATIVES = (
    ("eficiencia-producao", "Aumentar eficiência da produção", "INDUSTRY", "MES", ["oee", "mes", "producao", "nova-linha"]),
    ("gestao-manutencao", "Estruturar a gestão da manutenção", "INDUSTRY", "CMMS", ["pcm", "manutencao", "cmms", "contratacao"]),
    ("monitoramento-processos", "Monitorar máquinas e processos", "INDUSTRY", "PULSE", ["telemetria", "sensores", "historian", "automacao"]),
    ("expansao-industrial", "Identificar expansão ou nova planta", "INDUSTRY", "", ["expansao", "nova-fabrica", "nova-linha", "contratacao"]),
    ("canal-comercial", "Encontrar canal comercial", "PARTNER", "", ["parceria", "vendas", "comercial", "contratacao"]),
    ("implantacao-suporte", "Encontrar implantação e suporte", "PARTNER", "", ["implantacao", "automacao", "manutencao", "contratacao"]),
)


def seed_catalog(apps, schema_editor):
    Municipality = apps.get_model("discovery", "Municipality")
    GeographicRegion = apps.get_model("discovery", "GeographicRegion")
    MarketSegment = apps.get_model("discovery", "MarketSegment")
    Initiative = apps.get_model("discovery", "Initiative")
    catalog_path = Path(__file__).resolve().parents[1] / "data" / "geography_catalog.json"
    catalog = json.loads(catalog_path.read_text())

    Municipality.objects.bulk_create(
        [Municipality(**row) for row in catalog["municipalities"]], batch_size=500
    )
    GeographicRegion.objects.bulk_create(
        [
            GeographicRegion(
                code=row["code"],
                name=row["name"],
                state=row["state"],
                state_name=row["state_name"],
                kind=row["kind"],
                source_version=catalog["source_version"],
                source_region_codes=row["source_region_codes"],
                display_order=10 if row["kind"] == "COMMERCIAL" else 100,
            )
            for row in catalog["regions"]
        ]
    )
    through = GeographicRegion.municipalities.through
    through.objects.bulk_create(
        [
            through(geographicregion_id=row["code"], municipality_id=municipality_code)
            for row in catalog["regions"]
            for municipality_code in row["municipality_ibge_codes"]
        ],
        batch_size=1000,
    )
    MarketSegment.objects.bulk_create(
        [
            MarketSegment(
                key=key,
                name=name,
                target=target,
                cnae_prefixes=prefixes,
                display_order=position * 10,
            )
            for position, (key, name, target, prefixes) in enumerate(SEGMENTS, 1)
        ]
    )
    Initiative.objects.bulk_create(
        [
            Initiative(
                key=key,
                name=name,
                target=target,
                product=product,
                signal_types=signal_types,
                display_order=position * 10,
            )
            for position, (key, name, target, product, signal_types) in enumerate(INITIATIVES, 1)
        ]
    )


def unseed_catalog(apps, schema_editor):
    apps.get_model("discovery", "Initiative").objects.filter(
        key__in=[row[0] for row in INITIATIVES]
    ).delete()
    apps.get_model("discovery", "MarketSegment").objects.filter(
        key__in=[row[0] for row in SEGMENTS]
    ).delete()
    apps.get_model("discovery", "GeographicRegion").objects.all().delete()
    apps.get_model("discovery", "Municipality").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("discovery", "0004_initiative_marketsegment_municipality_and_more")]
    operations = [migrations.RunPython(seed_catalog, unseed_catalog)]
