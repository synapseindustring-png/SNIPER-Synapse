from django.urls import path

from . import views


urlpatterns = [
    path("", views.query_list, name="query-list"),
    path("manifest/sync/", views.manifest_sync, name="manifest-sync"),
    path("new/", views.query_create, name="query-create"),
    path("<uuid:pk>/", views.query_detail, name="query-detail"),
    path("<uuid:pk>/preview/", views.query_run_preview, name="query-run-preview"),
    path("runs/<uuid:pk>/", views.query_run_detail, name="query-run-detail"),
]
