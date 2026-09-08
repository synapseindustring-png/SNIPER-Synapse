from django.contrib import admin

from .models import RuleSet, ScoreContribution, ScoreOverride, ScoreSnapshot, ScoringRule


class ScoringRuleInline(admin.TabularInline):
    model = ScoringRule
    extra = 0

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == RuleSet.Status.PUBLISHED:
            return tuple(
                field.name
                for field in self.model._meta.fields
                if field.name not in {"id", "rule_set"}
            )
        return ()

    def has_add_permission(self, request, obj=None):
        return not obj or obj.status != RuleSet.Status.PUBLISHED

    def has_delete_permission(self, request, obj=None):
        return not obj or obj.status != RuleSet.Status.PUBLISHED


@admin.register(RuleSet)
class RuleSetAdmin(admin.ModelAdmin):
    list_display = ("name", "target", "version", "status", "active", "published_at")
    list_filter = ("target", "status", "active")
    inlines = (ScoringRuleInline,)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == RuleSet.Status.PUBLISHED:
            return tuple(field.name for field in self.model._meta.fields)
        return ("created_at", "published_at")

    def has_delete_permission(self, request, obj=None):
        return not obj or obj.status != RuleSet.Status.PUBLISHED


class ScoreContributionInline(admin.TabularInline):
    model = ScoreContribution
    extra = 0
    can_delete = False
    readonly_fields = ("rule", "dimension", "base_points", "decay_multiplier", "effective_points", "evidence", "observed_at")


@admin.register(ScoreSnapshot)
class ScoreSnapshotAdmin(admin.ModelAdmin):
    list_display = ("company", "priority", "calculated_classification", "rule_set", "as_of")
    list_filter = ("calculated_classification", "rule_set")
    search_fields = ("company__cnpj", "company__legal_name", "company__trade_name")
    readonly_fields = ("id", "company", "rule_set", "as_of", "dimensions", "priority", "calculated_classification", "best_product", "tied_products", "formula_detail", "created_at")
    inlines = (ScoreContributionInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ScoreOverride)
class ScoreOverrideAdmin(admin.ModelAdmin):
    list_display = ("company", "classification", "priority", "active", "created_by", "created_at")
    list_filter = ("active", "classification")
