import re

from django import forms
from django.conf import settings

from .models import DiscoveryQuery, GeographicRegion, Initiative, MarketSegment, OpportunitySearch


STATE_CHOICES = (
    ("AC", "Acre"), ("AL", "Alagoas"), ("AP", "Amapá"), ("AM", "Amazonas"),
    ("BA", "Bahia"), ("CE", "Ceará"), ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"), ("GO", "Goiás"), ("MA", "Maranhão"),
    ("MT", "Mato Grosso"), ("MS", "Mato Grosso do Sul"), ("MG", "Minas Gerais"),
    ("PA", "Pará"), ("PB", "Paraíba"), ("PR", "Paraná"), ("PE", "Pernambuco"),
    ("PI", "Piauí"), ("RJ", "Rio de Janeiro"), ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"), ("RO", "Rondônia"), ("RR", "Roraima"),
    ("SC", "Santa Catarina"), ("SP", "São Paulo"), ("SE", "Sergipe"),
    ("TO", "Tocantins"),
)


class OpportunitySearchForm(forms.Form):
    target = forms.ChoiceField(
        label="Quero encontrar",
        choices=(("INDUSTRY", "Clientes industriais"), ("PARTNER", "Parceiros comerciais")),
        initial="INDUSTRY",
    )
    state = forms.ChoiceField(label="Estado", choices=STATE_CHOICES, initial="MG")
    regions = forms.ModelMultipleChoiceField(
        label="Regiões",
        queryset=GeographicRegion.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Deixe sem marcar para pesquisar o estado inteiro.",
    )
    segments = forms.ModelMultipleChoiceField(
        label="Segmentos",
        queryset=MarketSegment.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    initiative = forms.ModelChoiceField(
        label="O que você quer identificar",
        queryset=Initiative.objects.none(),
        empty_label=None,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        target = self.data.get("target") or self.initial.get("target") or "INDUSTRY"
        state = self.data.get("state") or self.initial.get("state") or "MG"
        regions = GeographicRegion.objects.filter(state=state, active=True)
        if GeographicRegion.objects.filter(
            state=state, kind=GeographicRegion.Kind.COMMERCIAL, active=True
        ).exists():
            regions = regions.filter(kind=GeographicRegion.Kind.COMMERCIAL)
        self.fields["regions"].queryset = regions
        self.fields["segments"].queryset = MarketSegment.objects.filter(
            target=target, active=True
        )
        self.fields["initiative"].queryset = Initiative.objects.filter(
            target=target, active=True
        )

    def clean(self):
        cleaned = super().clean()
        target = cleaned.get("target")
        state = cleaned.get("state")
        if any(region.state != state for region in cleaned.get("regions", [])):
            self.add_error("regions", "Escolha somente regiões do estado selecionado.")
        if any(segment.target != target for segment in cleaned.get("segments", [])):
            self.add_error("segments", "Escolha segmentos compatíveis com o objetivo.")
        initiative = cleaned.get("initiative")
        if initiative and initiative.target != target:
            self.add_error("initiative", "Escolha uma iniciativa compatível com o objetivo.")
        return cleaned

    def save(self, user):
        regions = list(self.cleaned_data["regions"])
        segments = list(self.cleaned_data["segments"])
        state = self.cleaned_data["state"]
        region_label = ", ".join(region.name for region in regions) or f"todo o estado de {state}"
        cnae_prefixes = sorted({code for segment in segments for code in segment.cnae_prefixes})
        municipality_codes = sorted({
            code
            for region in regions
            for municipality in region.municipalities.all()
            for code in municipality.receita_codes
        })
        search = OpportunitySearch.objects.create(
            name=f"{self.cleaned_data['initiative'].name} · {region_label}",
            target=self.cleaned_data["target"],
            state=state,
            initiative=self.cleaned_data["initiative"],
            technical_filters={
                "registration_statuses": ["02"],
                "states": [state],
                "municipality_codes": municipality_codes,
                "cnae_prefixes": cnae_prefixes,
            },
            created_by=user,
        )
        search.regions.set(regions)
        search.segments.set(segments)
        return search


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


class FullRunForm(forms.Form):
    max_results = forms.IntegerField(
        label="Limite máximo de empresas",
        min_value=1,
        initial=1000,
    )
    confirm = forms.BooleanField(
        label="Confirmo o processamento completo e o volume estimado",
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["max_results"].max_value = settings.CNPJ_MAX_PERSISTED_MATCHES
        self.fields["max_results"].initial = min(1000, settings.CNPJ_MAX_PERSISTED_MATCHES)
        self.fields["max_results"].widget.attrs["max"] = settings.CNPJ_MAX_PERSISTED_MATCHES
        self.fields["max_results"].help_text = (
            f"Teto configurado: {settings.CNPJ_MAX_PERSISTED_MATCHES}."
        )
