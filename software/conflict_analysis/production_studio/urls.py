"""GET-only browser routes for Production Studio C0."""

from django.urls import path

from production_studio import views


app_name = "production_studio"

urlpatterns = [
    path("", views.entry, name="entry"),
    path(
        "definitions/<uuid:definition_id>/",
        views.definition,
        name="definition",
    ),
    path(
        "claim-boundaries/read-only/v1/",
        views.claim_boundaries_read_only_v1,
        name="claim_boundaries_read_only_v1",
    ),
]
