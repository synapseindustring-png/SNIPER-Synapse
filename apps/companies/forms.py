from django import forms

from apps.signals.models import SignalRule

from .corrections import CORRECTABLE_FIELDS
from .models import Company


class CompanyFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Empresa ou CNPJ")
    state = forms.CharField(required=False, max_length=2, label="UF")
    registration_status = forms.ChoiceField(
        required=False,
        label="Situação cadastral",
        choices=(("", "Todas"), *Company.RegistrationStatus.choices),
    )
    commercial_status = forms.ChoiceField(
        required=False,
        label="Etapa comercial",
        choices=(("", "Todas"), *Company.CommercialStatus.choices),
    )
    classification = forms.ChoiceField(
        required=False,
        label="Classificação",
        choices=(
            ("", "Todas"),
            ("HOT", "Hot"),
            ("WARM", "Warm"),
            ("WATCH", "Watch"),
            ("COLD", "Cold"),
            ("DISQUALIFIED", "Desqualificada"),
        ),
    )
    best_product = forms.ChoiceField(
        required=False,
        label="Melhor produto",
        choices=(("", "Todos"), ("MES", "MES"), ("CMMS", "CMMS"), ("PULSE", "Pulse")),
    )
    signal_type = forms.ChoiceField(required=False, label="Sinal ativo", choices=())
    minimum_priority = forms.DecimalField(
        required=False,
        label="Prioridade mínima",
        min_value=0,
        max_value=100,
        decimal_places=0,
    )
    scored_since = forms.DateField(
        required=False,
        label="Score desde",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    ordering = forms.ChoiceField(
        required=False,
        label="Ordenar por",
        initial="priority_desc",
        choices=(
            ("priority_desc", "Maior prioridade"),
            ("priority_asc", "Menor prioridade"),
            ("score_recent", "Score mais recente"),
            ("company_name", "Nome da empresa"),
        ),
    )

    def __init__(self, *args, target="industry", **kwargs):
        super().__init__(*args, **kwargs)
        if target == "partner":
            self.fields["classification"].choices = (
                ("", "Todas"),
                ("PRIORITY_PARTNER", "Parceiro prioritário"),
                ("WARM_PARTNER", "Parceiro warm"),
                ("WATCH", "Watch"),
                ("LOW_FIT", "Baixo fit"),
                ("CONFLICT", "Conflito"),
            )
            self.fields.pop("best_product")
        signal_types = (
            SignalRule.objects.filter(active=True)
            .order_by("signal_type")
            .values_list("signal_type", flat=True)
            .distinct()
        )
        self.fields["signal_type"].choices = (("", "Todos"), *((value, value) for value in signal_types))

    def clean_state(self):
        return self.cleaned_data["state"].strip().upper()


class CompanyCorrectionForm(forms.ModelForm):
    justification = forms.CharField(
        label="Justificativa",
        min_length=10,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Explique a origem e o motivo da correção (mínimo de 10 caracteres).",
    )

    class Meta:
        model = Company
        fields = CORRECTABLE_FIELDS

    def clean_state(self):
        state = self.cleaned_data["state"].strip().upper()
        if state and len(state) != 2:
            raise forms.ValidationError("Informe uma UF com duas letras.")
        return state

    def clean(self):
        cleaned = super().clean()
        changed_company_fields = set(self.changed_data).intersection(CORRECTABLE_FIELDS)
        if not changed_company_fields:
            raise forms.ValidationError("Altere ao menos um campo do cadastro.")
        return cleaned
