from django.urls import path

from . import views


urlpatterns = [
    path("", views.job_list, name="job-list"),
    path("sources/cnpj/", views.cnpj_source_detail, name="cnpj-source-detail"),
    path("<uuid:pk>/", views.job_detail, name="job-detail"),
]
