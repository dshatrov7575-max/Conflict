"""URL composition root for ConflictAnalysis Studio — Прототип."""

from django.urls import include, path


urlpatterns = [
    path("", include("studio_showcase.urls")),
]

