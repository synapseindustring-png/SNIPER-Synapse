import re
import uuid

from django import forms
from django.db.models import Q

from apps.companies.models import Company


class JobReviewMatchForm(forms.Form):
    company_reference = forms.CharField(
        label="Empresa de destino",
        max_length=500,
        help_text="Informe o UUID, CNPJ, razão social ou nome fantasia exato.",
    )
    note = forms.CharField(label="Justificativa", max_length=1000, widget=forms.Textarea)

    def clean_company_reference(self):
        value = self.cleaned_data["company_reference"].strip()
        queryset = Company.objects.filter(deleted_at__isnull=True)
        try:
            company_id = uuid.UUID(value)
        except ValueError:
            company_id = None
        if company_id:
            company = queryset.filter(pk=company_id).first()
            if company:
                return company
        normalized_cnpj = re.sub(r"[^A-Za-z0-9]", "", value).upper()
        if normalized_cnpj:
            company = queryset.filter(cnpj=normalized_cnpj).first()
            if company:
                return company
        matches = list(
            queryset.filter(Q(legal_name__iexact=value) | Q(trade_name__iexact=value))[:2]
        )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise forms.ValidationError("Mais de uma empresa possui esse nome; use CNPJ ou UUID.")
        raise forms.ValidationError("Empresa não encontrada por referência exata.")


class JobReviewDismissForm(forms.Form):
    reason = forms.CharField(label="Motivo do descarte", max_length=1000, widget=forms.Textarea)
