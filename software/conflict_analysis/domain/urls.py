"""Exact canonical Foundation API routes accepted by the Studio addendum."""

from django.urls import path

from domain.api import studio_definitions


urlpatterns = [
    path(
        "projects/bootstrap-first-draft/",
        studio_definitions.bootstrap_first_definition_draft,
        name="foundation-project-bootstrap-first-draft",
    ),
    path(
        "projects/<uuid:project_id>/definitions/",
        studio_definitions.create_definition_draft,
        name="foundation-definition-create",
    ),
    path(
        "projects/<uuid:project_id>/publication-operations/<uuid:operation_id>/",
        studio_definitions.open_publication_operation,
        name="foundation-publication-operation-open",
    ),
    path(
        "projects/<uuid:project_id>/publication-results/<uuid:publication_id>/",
        studio_definitions.open_publication_result,
        name="foundation-publication-result-open",
    ),
    path(
        "projects/<uuid:project_id>/definition-packages/2.1/preview/",
        studio_definitions.preview_definition_package_2_1,
        name="foundation-definition-package-21-preview",
    ),
    path(
        "projects/<uuid:project_id>/definition-packages/2.1/attempt/",
        studio_definitions.attempt_definition_package_2_1,
        name="foundation-definition-package-21-attempt",
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
        "definitions/<uuid:definition_id>/validation-preview/",
        studio_definitions.validation_preview,
        name="foundation-definition-validation-preview",
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
        "definitions/<uuid:definition_id>/publish-successor/",
        studio_definitions.publish_successor_definition,
        name="foundation-definition-publish-successor",
    ),
    path(
        "definitions/<uuid:definition_id>/package/2.1/",
        studio_definitions.export_definition_package_2_1,
        name="foundation-definition-package-21-export",
    ),
    path(
        "help/<str:ui_key>/",
        studio_definitions.exact_help_topic,
        name="foundation-help-exact",
    ),
]
