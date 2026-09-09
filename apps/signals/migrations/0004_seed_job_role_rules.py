from django.db import migrations


RULES = [
    (
        "vaga-processos",
        "Vaga de processos industriais",
        "producao",
        "MES",
        ["engenheiro de processos", "analista de processos", "especialista de processos"],
    ),
    (
        "vaga-melhoria-continua",
        "Vaga de melhoria contínua",
        "producao",
        "MES",
        ["melhoria contínua", "lean manufacturing", "excelência operacional"],
    ),
]


def seed_rules(apps, schema_editor):
    SignalRule = apps.get_model("signals", "SignalRule")
    SignalRule.objects.bulk_create(
        [
            SignalRule(
                key=key,
                version=1,
                name=name,
                description="Regra explícita para cargos em vagas estruturadas.",
                signal_type=signal_type,
                product=product,
                keywords=keywords,
                source_fields=["job_title", "job_description"],
                base_weight=0,
                applies_decay=True,
                expires_after_days=365,
                active=True,
            )
            for key, name, signal_type, product, keywords in RULES
        ]
    )


def unseed_rules(apps, schema_editor):
    apps.get_model("signals", "SignalRule").objects.filter(
        key__in=[rule[0] for rule in RULES], version=1
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("signals", "0003_seed_signal_rules")]
    operations = [migrations.RunPython(seed_rules, unseed_rules)]
