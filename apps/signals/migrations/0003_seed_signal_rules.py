from django.db import migrations


SOURCE_FIELDS = [
    "title",
    "description",
    "content",
    "text",
    "job_title",
    "job_description",
    "news_title",
    "news_text",
]


def seed_signal_rules(apps, schema_editor):
    SignalRule = apps.get_model("signals", "SignalRule")
    seeds = [
        ("pcm", "PCM e planejamento de manutenção", "pcm", "CMMS", ["pcm", "planejamento e controle da manutenção", "planejador de manutenção"]),
        ("manutencao", "Manutenção e confiabilidade", "manutencao", "CMMS", ["manutenção preventiva", "manutenção preditiva", "gestão de ativos", "confiabilidade"]),
        ("oee", "OEE e eficiência industrial", "oee", "MES", ["oee", "eficiência global dos equipamentos"]),
        ("mes", "Sistema MES", "mes", "MES", ["sistema mes", "manufacturing execution system"]),
        ("producao", "Gestão da produção", "producao", "MES", ["pcp", "gestão da produção", "chão de fábrica"]),
        ("telemetria", "Telemetria e dados de processo", "telemetria", "PULSE", ["telemetria", "sensores industriais", "historian", "dados de processo"]),
        ("automacao", "Automação e digitalização industrial", "automacao", "PULSE", ["automação industrial", "digitalização industrial", "indústria 4.0"]),
        ("expansao", "Expansão industrial", "expansao", "NONE", ["nova fábrica", "nova unidade", "expansão da fábrica", "ampliação da planta", "nova linha de produção"]),
        ("contratacao", "Contratação técnica", "contratacao", "NONE", ["vaga de pcm", "vaga de manutenção", "vaga de produção", "planejador de manutenção"]),
        ("erp", "ERP industrial", "erp", "MES", ["sap", "totvs", "sistema erp"]),
        ("planilhas", "Processo controlado por planilhas", "planilhas", "PULSE", ["controle em planilhas", "processo em excel", "planilha de produção"]),
    ]
    SignalRule.objects.bulk_create([
        SignalRule(
            key=key,
            version=1,
            name=name,
            description="Hipótese inicial explícita; revisar falsos positivos antes de uso comercial.",
            signal_type=signal_type,
            product=product,
            keywords=keywords,
            source_fields=SOURCE_FIELDS,
            base_weight=0,
            applies_decay=True,
            expires_after_days=365,
            active=True,
        )
        for key, name, signal_type, product, keywords in seeds
    ])


def unseed_signal_rules(apps, schema_editor):
    apps.get_model("signals", "SignalRule").objects.filter(version=1).delete()


class Migration(migrations.Migration):
    dependencies = [("signals", "0002_signalrule_signaldetection")]
    operations = [migrations.RunPython(seed_signal_rules, unseed_signal_rules)]
