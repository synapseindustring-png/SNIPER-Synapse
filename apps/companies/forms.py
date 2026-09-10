from django import forms

from apps.signals.models import SignalRule

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        signal_types = (
            SignalRule.objects.filter(active=True)
            .order_by("signal_type")
            .values_list("signal_type", flat=True)
            .distinct()
        )
        self.fields["signal_type"].choices = (("", "Todos"), *((value, value) for value in signal_types))

    def clean_state(self):
        return self.cleaned_data["state"].strip().upper()
