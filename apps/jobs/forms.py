from django import forms

from .models import Job


class JobFilterForm(forms.Form):
    q = forms.CharField(required=False, label="ID ou chave")
    job_type = forms.ChoiceField(
        required=False,
        label="Tipo",
        choices=(("", "Todos"), *Job.Type.choices),
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=(("", "Todos"), *Job.Status.choices),
    )
    created_since = forms.DateField(
        required=False,
        label="Criado desde",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
