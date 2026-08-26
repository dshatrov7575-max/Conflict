"""Root URL configuration for Conflict Analysis."""

from django.contrib import admin
from django.urls import path

from . import studio_definition_api


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/studio/definitions/drafts/",
        studio_definition_api.create_definition_draft,
        name="studio-definition-create",
    ),
    path(
        "api/studio/definitions/<uuid:definition_id>/",
        studio_definition_api.open_definition_draft,
        name="studio-definition-open",
    ),
    path(
        "api/studio/definitions/<uuid:definition_id>/clone/",
        studio_definition_api.clone_definition_draft,
        name="studio-definition-clone",
    ),
    path(
        "api/studio/definitions/<uuid:definition_id>/save/",
        studio_definition_api.save_definition_draft,
        name="studio-definition-save",
    ),
    path(
        "api/studio/definitions/<uuid:definition_id>/validate/",
        studio_definition_api.validate_definition,
        name="studio-definition-validate",
    ),
    path(
        "api/studio/definitions/<uuid:definition_id>/publish/",
        studio_definition_api.publish_definition,
        name="studio-definition-publish",
    ),
    path(
        "api/studio/definitions/<uuid:definition_id>/bootstrap/",
        studio_definition_api.bootstrap_definition,
        name="studio-definition-bootstrap",
    ),
    path(
        "api/studio/help/<str:ui_key>/",
        studio_definition_api.exact_help_topic,
        name="studio-help-exact",
    ),
]
