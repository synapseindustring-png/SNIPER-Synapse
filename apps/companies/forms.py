from django import forms

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

    def clean_state(self):
        return self.cleaned_data["state"].strip().upper()
