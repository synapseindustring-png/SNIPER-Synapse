import re

from django import forms

from .models import DiscoveryQuery


class DiscoveryQueryForm(forms.Form):
    name = forms.CharField(label="Nome da consulta", max_length=160)
    entity_target = forms.ChoiceField(
        label="Tipo de empresa",
        choices=DiscoveryQuery.EntityTarget.choices,
        initial=DiscoveryQuery.EntityTarget.INDUSTRY,
    )
    state = forms.CharField(label="UF", max_length=2, required=False)
    municipality_code = forms.CharField(
        label="Código IBGE do município",
        max_length=16,
        required=False,
    )
    cnae_prefixes = forms.CharField(
        label="CNAEs ou prefixos",
        required=False,
        help_text="Separe por vírgulas. Exemplo: 10, 10911.",
    )

    def clean_state(self):
        state = self.cleaned_data["state"].strip().upper()
        if state and not re.fullmatch(r"[A-Z]{2}", state):
            raise forms.ValidationError("Informe uma UF com duas letras.")
        return state

    def clean_municipality_code(self):
        value = re.sub(r"\D", "", self.cleaned_data["municipality_code"])
        if value and len(value) != 4 and len(value) != 7:
            raise forms.ValidationError("Informe o código do município com 4 ou 7 dígitos.")
        return value

    def clean_cnae_prefixes(self):
        raw_values = self.cleaned_data["cnae_prefixes"].split(",")
        values = []
        for raw_value in raw_values:
            value = re.sub(r"\D", "", raw_value)
            if not value:
                continue
            if len(value) > 7:
                raise forms.ValidationError("Cada CNAE deve possuir no máximo 7 dígitos.")
            values.append(value)
        return sorted(set(values))

    def clean(self):
        cleaned = super().clean()
        if not any(
            cleaned.get(field)
            for field in ("state", "municipality_code", "cnae_prefixes")
        ):
            raise forms.ValidationError("Informe ao menos UF, município ou CNAE.")
        return cleaned

    def save(self, user) -> DiscoveryQuery:
        filters = {
            "registration_statuses": ["02"],
            "states": [self.cleaned_data["state"]] if self.cleaned_data["state"] else [],
            "municipality_codes": (
                [self.cleaned_data["municipality_code"]]
                if self.cleaned_data["municipality_code"]
                else []
            ),
            "cnae_prefixes": self.cleaned_data["cnae_prefixes"],
        }
        return DiscoveryQuery.objects.create(
            name=self.cleaned_data["name"],
            entity_target=self.cleaned_data["entity_target"],
            filters=filters,
            created_by=user,
        )


class PreviewRunForm(forms.Form):
    max_results = forms.TypedChoiceField(
        label="Limite da prévia",
        choices=((10, "10"), (50, "50"), (100, "100"), (500, "500")),
        coerce=int,
        initial=100,
    )
