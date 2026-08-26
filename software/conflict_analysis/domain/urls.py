"""Exact canonical Foundation API routes accepted by the Studio addendum."""

from django.urls import path

from domain.api import studio_definitions


urlpatterns = [
    path(
        "projects/<uuid:project_id>/definitions/",
        studio_definitions.create_definition_draft,
        name="foundation-definition-create",
    ),
    path(
        "definitions/<uuid:definition_id>/",
        studio_definitions.open_definition,
        name="foundation-definition-open",
    ),
    path(
        "definitions/<uuid:definition_id>/clone/",
        studio_definitions.clone_definition,
        name="foundation-definition-clone",
    ),
    path(
        "definitions/<uuid:definition_id>/draft/",
        studio_definitions.save_definition_draft,
        name="foundation-definition-save-draft",
    ),
    path(
        "definitions/<uuid:definition_id>/validate/",
        studio_definitions.validate_definition,
        name="foundation-definition-validate",
    ),
    path(
        "definitions/<uuid:definition_id>/publish-initial/",
        studio_definitions.publish_initial_definition,
        name="foundation-definition-publish-initial",
    ),
    path(
        "help/<str:ui_key>/",
        studio_definitions.exact_help_topic,
        name="foundation-help-exact",
    ),
]
