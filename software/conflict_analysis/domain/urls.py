"""Exact canonical Foundation API routes accepted by the Studio addendum."""

from django.urls import path

from domain.api import evidence, player, player_experiments, studio_definitions


urlpatterns = [
    path("player/workspaces/<uuid:workspace_id>/expert-profiles/", player_experiments.expert_profiles, name="foundation-player-g8-expert-profiles"),
    path("player/workspaces/<uuid:workspace_id>/experiments/", player_experiments.experiments, name="foundation-player-experiments"),
    path("player/experiments/<uuid:experiment_id>/", player_experiments.experiment, name="foundation-player-g8-experiment"),
    path("player/experiments/<uuid:experiment_id>/freeze/", player_experiments.freeze, name="foundation-player-g8-experiment-freeze"),
    path("player/experiments/<uuid:experiment_id>/archive/", player_experiments.archive, name="foundation-player-g8-experiment-archive"),
    path("player/experiments/<uuid:experiment_id>/values/", player_experiments.values, name="foundation-player-g8-values"),
    path("player/experiments/<uuid:experiment_id>/xlsx-preview/", player_experiments.xlsx_preview, name="foundation-player-g8-xlsx-preview"),
    path("player/experiments/<uuid:experiment_id>/xlsx-import/", player_experiments.xlsx_import, name="foundation-player-g8-xlsx-import"),
    path("player/experiments/<uuid:experiment_id>/imports/<uuid:operation_id>/", player_experiments.import_recovery, name="foundation-player-g8-import-recovery"),
    path("player/workspaces/<uuid:workspace_id>/experiment-comparison/", player_experiments.experiment_comparison, name="foundation-player-g8-comparison"),
    path("player/projects/<uuid:project_id>/definitions/", player.definitions, name="foundation-player-definitions"),
    path("player/definitions/<uuid:definition_id>/", player.definition, name="foundation-player-definition"),
    path("player/projects/<uuid:project_id>/workspaces/", player.workspaces, name="foundation-player-workspaces"),
    path("player/workspaces/<uuid:workspace_id>/", player.workspace, name="foundation-player-workspace"),
    path("player/workspaces/<uuid:workspace_id>/time-slices/", player.time_slices, name="foundation-player-time-slices"),
    path("player/workspaces/<uuid:workspace_id>/help/<str:ui_key>/", player.help_topic, name="foundation-player-help"),
    path(
        "projects/<uuid:project_id>/workspaces/<uuid:workspace_id>/parameter-values/<uuid:parameter_value_id>/facts/",
        evidence.parameter_value_fact_list,
        name="foundation-parameter-value-facts",
    ),
    path(
        "projects/<uuid:project_id>/workspaces/<uuid:workspace_id>/assessments/<uuid:assessment_id>/facts/",
        evidence.assessment_fact_list,
        name="foundation-assessment-facts",
    ),
    path(
        "projects/<uuid:project_id>/workspaces/<uuid:workspace_id>/facts/<uuid:fact_id>/evidence/",
        evidence.fact_evidence_drilldown,
        name="foundation-fact-evidence-drilldown",
    ),
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
        "definitions/<uuid:definition_id>/publication-readiness/",
        studio_definitions.open_publication_readiness,
        name="foundation-definition-publication-readiness",
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
