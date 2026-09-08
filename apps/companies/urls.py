from django.urls import path

from . import views

urlpatterns = [
    path("", views.company_list, name="company-list"),
    path("<uuid:pk>/score/", views.company_score, name="company-score"),
    path("<uuid:pk>/", views.company_detail, name="company-detail"),
]
