from django.urls import path

from . import views


urlpatterns = [
    path("", views.job_review_list, name="job-review-list"),
    path("<uuid:pk>/", views.job_review_detail, name="job-review-detail"),
    path("<uuid:pk>/match/", views.job_review_match, name="job-review-match"),
    path("<uuid:pk>/dismiss/", views.job_review_dismiss, name="job-review-dismiss"),
]
