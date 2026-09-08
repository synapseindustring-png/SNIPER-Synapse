from django.db import migrations
from django.utils import timezone


INDUSTRY_THRESHOLDS = [
    {"min": "80", "classification": "HOT"},
    {"min": "65", "classification": "WARM"},
    {"min": "45", "classification": "WATCH"},
    {"min": "0", "classification": "COLD"},
]
PARTNER_THRESHOLDS = [
    {"min": "80", "classification": "PRIORITY_PARTNER"},
    {"min": "65", "classification": "WARM_PARTNER"},
    {"min": "45", "classification": "WATCH"},
    {"min": "0", "classification": "LOW_PRIORITY"},
]
DECAY = [
    {"max_days": 30, "multiplier": "1.00"},
    {"max_days": 60, "multiplier": "0.80"},
    {"max_days": 90, "multiplier": "0.60"},
    {"max_days": 180, "multiplier": "0.30"},
    {"max_days": None, "multiplier": "0.10"},
]


def seed_rules(apps, schema_editor):
    RuleSet = apps.get_model("scoring", "RuleSet")
    ScoringRule = apps.get_model("scoring", "ScoringRule")
    industry = RuleSet.objects.create(
        name="Hipóteses iniciais — Indústrias",
        target="INDUSTRY",
        version=1,
        status="PUBLISHED",
        active=True,
        formula={"ICP": "0.35", "BEST_PRODUCT": "0.35", "INTENT": "0.30"},
        thresholds=INDUSTRY_THRESHOLDS,
        tie_order=["MES", "CMMS", "PULSE"],
        description="Seeds configuráveis para iniciar validação comercial; não representam precisão comprovada.",
        published_at=timezone.now(),
    )
    rules = [
        ("cnpj-inativo", "CNPJ inativo", "ICP", {"field": "registration_status", "op": "EQ", "value": "INACTIVE"}, "0", "NONE", "DISQUALIFIED"),
        ("cadastro-ativo", "Cadastro ativo", "ICP", {"field": "registration_status", "op": "EQ", "value": "ACTIVE"}, "20", "NONE", ""),
        ("cnae-industrial", "CNAE industrial", "ICP", {"field": "cnaes", "op": "HAS_CNAE_PREFIX", "value": [str(value) for value in range(10, 34)]}, "30", "NONE", ""),
        ("sinal-oee-mes", "Sinal de OEE ou MES", "MES", {"field": "signal_types", "op": "HAS_SIGNAL", "value": ["oee", "mes", "producao"]}, "30", "AGE_BUCKETS", ""),
        ("sinal-pcm-cmms", "Sinal de PCM ou manutenção", "CMMS", {"field": "signal_types", "op": "HAS_SIGNAL", "value": ["pcm", "manutencao", "cmms"]}, "30", "AGE_BUCKETS", ""),
        ("sinal-telemetria-pulse", "Sinal de telemetria ou processo", "PULSE", {"field": "signal_types", "op": "HAS_SIGNAL", "value": ["telemetria", "sensores", "historian"]}, "30", "AGE_BUCKETS", ""),
        ("sinal-expansao", "Expansão ou nova linha", "INTENT", {"field": "signal_types", "op": "HAS_SIGNAL", "value": ["expansao", "nova-fabrica", "nova-linha", "contratacao"]}, "25", "AGE_BUCKETS", ""),
    ]
    ScoringRule.objects.bulk_create([
        ScoringRule(rule_set=industry, key=key, name=name, dimension=dimension, condition=condition, points=points, decay_policy=decay, decay_curve=DECAY if decay == "AGE_BUCKETS" else [], critical_outcome=critical, order=index * 10, description="Hipótese inicial editável em uma futura versão de regras.")
        for index, (key, name, dimension, condition, points, decay, critical) in enumerate(rules, 1)
    ])
    RuleSet.objects.create(
        name="Hipóteses iniciais — Parceiros",
        target="PARTNER",
        version=1,
        status="PUBLISHED",
        active=True,
        formula={"PARTNER_FIT": "0.45", "CHANNEL": "0.35", "ACTIVITY": "0.20", "CONFLICT": "-1.00"},
        thresholds=PARTNER_THRESHOLDS,
        description="Estrutura inicial sem contribuições até existirem sinais de parceiros validados.",
        published_at=timezone.now(),
    )


def unseed_rules(apps, schema_editor):
    rule_sets = apps.get_model("scoring", "RuleSet").objects.filter(version=1)
    apps.get_model("scoring", "ScoringRule").objects.filter(rule_set__in=rule_sets).delete()
    rule_sets.delete()


class Migration(migrations.Migration):
    dependencies = [("scoring", "0001_initial")]
    operations = [migrations.RunPython(seed_rules, unseed_rules)]
