from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.companies import views as company_views
from apps.discovery import views as discovery_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("opportunities/", discovery_views.opportunity_create, name="opportunity-create"),
    path("opportunities/options/", discovery_views.opportunity_options, name="opportunity-options"),
    path("opportunities/<uuid:pk>/", discovery_views.opportunity_results, name="opportunity-results"),
    path("queries/", include("apps.discovery.urls")),
    path("industries/", include("apps.companies.urls")),
    path("partners/", company_views.partner_list, name="partner-list"),
    path("partners/export.csv", company_views.partner_export, name="partner-export"),
    path("partners/<uuid:pk>/", company_views.company_detail, name="partner-detail"),
    path("reviews/jobs/", include("apps.crawler.urls")),
    path("operations/jobs/", include("apps.jobs.urls")),
    path("rules/", include("apps.scoring.urls")),
    path("", include("apps.core.urls")),
]
