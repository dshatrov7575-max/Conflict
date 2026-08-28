"""GET-only browser composition routes for Production Studio C0 and C1."""

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
    path(
        "drafts/",
        views.audited_draft_entry,
        name="audited_draft_entry",
    ),
    path(
        "drafts/definitions/<uuid:definition_id>/",
        views.audited_draft_definition,
        name="audited_draft_definition",
    ),
    path(
        "claim-boundaries/audited-draft/v1/",
        views.claim_boundaries_audited_draft_v1,
        name="claim_boundaries_audited_draft_v1",
    ),
]
