from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("health/live", views.health_live, name="health-live"),
    path("health/ready", views.health_ready, name="health-ready"),
]

