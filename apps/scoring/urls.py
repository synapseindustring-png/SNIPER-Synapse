from django.urls import path

from . import views


urlpatterns = [
    path("", views.rule_set_list, name="rule-set-list"),
    path("clone/<str:target>/", views.rule_set_clone, name="rule-set-clone"),
    path("<uuid:pk>/", views.rule_set_detail, name="rule-set-detail"),
    path("<uuid:pk>/publish/", views.rule_set_publish, name="rule-set-publish"),
    path("<uuid:pk>/simulate/", views.rule_set_simulate, name="rule-set-simulate"),
    path("<uuid:rule_set_pk>/rules/new/", views.scoring_rule_edit, name="scoring-rule-create"),
    path("<uuid:rule_set_pk>/rules/<uuid:pk>/", views.scoring_rule_edit, name="scoring-rule-edit"),
    path("<uuid:rule_set_pk>/rules/<uuid:pk>/delete/", views.scoring_rule_delete, name="scoring-rule-delete"),
]
