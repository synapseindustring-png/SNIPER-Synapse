from django import forms

from apps.companies.models import Company

from .models import RuleSet, ScoringRule


class RuleSetForm(forms.ModelForm):
    class Meta:
        model = RuleSet
        fields = ("name", "description", "formula", "thresholds", "tie_order")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "formula": forms.Textarea(attrs={"rows": 5}),
            "thresholds": forms.Textarea(attrs={"rows": 8}),
            "tie_order": forms.Textarea(attrs={"rows": 3}),
        }


class ScoringRuleForm(forms.ModelForm):
    class Meta:
        model = ScoringRule
        fields = (
            "key",
            "name",
            "description",
            "dimension",
            "condition",
            "points",
            "decay_policy",
            "decay_curve",
            "critical_outcome",
            "group_key",
            "group_cap",
            "max_occurrences",
            "active",
            "order",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "condition": forms.Textarea(attrs={"rows": 7}),
            "decay_curve": forms.Textarea(attrs={"rows": 6}),
        }


class ScoreSimulationForm(forms.Form):
    company = forms.ModelChoiceField(label="Empresa para simulação", queryset=Company.objects.none())

    def __init__(self, *args, rule_set, **kwargs):
        super().__init__(*args, **kwargs)
        if rule_set.target == RuleSet.Target.INDUSTRY:
            queryset = Company.objects.filter(company_type=Company.Type.INDUSTRY)
        else:
            queryset = Company.objects.filter(
                company_type__in=(
                    Company.Type.CONSULTANCY,
                    Company.Type.INTEGRATOR,
                    Company.Type.ENGINEERING,
                    Company.Type.SERVICE_PROVIDER,
                )
            )
        self.fields["company"].queryset = queryset.filter(
            deleted_at__isnull=True
        ).order_by("trade_name", "legal_name")
