"""Add the receipt-bound Foundation workspace assessment projection boundary.

The migration is additive for legacy data.  Canonical rows are introduced only
by the runtime projection service; a database-level guard is installed last so
that neither ORM cascades nor raw SQL can silently mutate their provenance.
"""

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


_CANONICAL_GUARDS = (
    ("domain_actor", "source_manifest_entity_id", "actor"),
    ("domain_analyticalelement", "source_manifest_entity_id", "element"),
    ("domain_actorelementrole", "source_manifest_entity_id", "role"),
    ("domain_parameterdefinition", "definition_version_id", "parameter"),
)


def _install_canonical_projection_guards(apps, schema_editor):
    """Protect canonical rows after every SQLite schema rebuild has completed."""

    del apps
    connection = schema_editor.connection
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            for table, marker, label in _CANONICAL_GUARDS:
                for operation in ("UPDATE", "DELETE"):
                    trigger = f"domain_fd08_{label}_canonical_{operation.lower()}"
                    cursor.execute(
                        f"DROP TRIGGER IF EXISTS {quote(trigger)}"
                    )
                    cursor.execute(
                        f"CREATE TRIGGER {quote(trigger)} "
                        f"BEFORE {operation} ON {quote(table)} "
                        "FOR EACH ROW "
                        f"WHEN OLD.{quote(marker)} IS NOT NULL "
                        "BEGIN SELECT RAISE(ABORT, "
                        "'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN'); END"
                    )
            return
        if connection.vendor == "postgresql":
            cursor.execute(
                "CREATE OR REPLACE FUNCTION "
                "domain_fd08_block_canonical_projection_mutation() "
                "RETURNS trigger AS $$ "
                "BEGIN "
                "IF (to_jsonb(OLD) ->> 'source_manifest_entity_id') IS NOT NULL "
                "OR (to_jsonb(OLD) ->> 'definition_version_id') IS NOT NULL THEN "
                "RAISE EXCEPTION 'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN'; "
                "END IF; "
                "IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; "
                "RETURN NEW; "
                "END; $$ LANGUAGE plpgsql"
            )
            for table, _marker, label in _CANONICAL_GUARDS:
                trigger = f"domain_fd08_{label}_canonical_mutation"
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS {quote(trigger)} ON {quote(table)}"
                )
                cursor.execute(
                    f"CREATE TRIGGER {quote(trigger)} "
                    f"BEFORE UPDATE OR DELETE ON {quote(table)} "
                    "FOR EACH ROW EXECUTE FUNCTION "
                    "domain_fd08_block_canonical_projection_mutation()"
                )


def _drop_canonical_projection_guards(schema_editor):
    connection = schema_editor.connection
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            for _table, _marker, label in _CANONICAL_GUARDS:
                for operation in ("update", "delete"):
                    cursor.execute(
                        f"DROP TRIGGER IF EXISTS "
                        f"{quote(f'domain_fd08_{label}_canonical_{operation}') }"
                    )
        elif connection.vendor == "postgresql":
            for table, _marker, label in _CANONICAL_GUARDS:
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS "
                    f"{quote(f'domain_fd08_{label}_canonical_mutation')} "
                    f"ON {quote(table)}"
                )
            cursor.execute(
                "DROP FUNCTION IF EXISTS "
                "domain_fd08_block_canonical_projection_mutation()"
            )


def _reverse_projection_guard(apps, schema_editor):
    """Never make a populated canonical projection silently mutable on reverse."""

    database = schema_editor.connection.alias
    markers = (
        ("Actor", "source_manifest_entity_id"),
        ("AnalyticalElement", "source_manifest_entity_id"),
        ("ActorElementRole", "source_manifest_entity_id"),
        ("ParameterDefinition", "definition_version_id"),
    )
    for model_name, marker in markers:
        model = apps.get_model("domain", model_name)
        if model.objects.using(database).filter(**{f"{marker}__isnull": False}).exists():
            raise RuntimeError(
                "FD08_CANONICAL_PROJECTION_REVERSE_BLOCKED: "
                f"{model_name} contains protected canonical rows."
            )
    _drop_canonical_projection_guards(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0017_multilingual_evidence_lineage"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="actorelementrole",
            options={
                "ordering": (
                    "workspace__code",
                    "order",
                    "actor__code",
                    "element__code",
                    "role",
                )
            },
        ),
        migrations.RemoveConstraint(
            model_name="parameterdefinition",
            name="domain_parameter_project_code_uniq",
        ),
        migrations.AddField(
            model_name="actor",
            name="source_manifest_entity_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="actor",
            name="source_manifest_entity_sha256",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="A manifest hash must be a lowercase hexadecimal SHA-256 digest.",
                        regex="^[0-9a-f]{64}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="actorelementrole",
            name="order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="actorelementrole",
            name="source_manifest_entity_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="actorelementrole",
            name="source_manifest_entity_sha256",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="A manifest hash must be a lowercase hexadecimal SHA-256 digest.",
                        regex="^[0-9a-f]{64}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="analyticalelement",
            name="source_manifest_entity_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="analyticalelement",
            name="source_manifest_entity_sha256",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="A manifest hash must be a lowercase hexadecimal SHA-256 digest.",
                        regex="^[0-9a-f]{64}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="parameterdefinition",
            name="allowed_statuses",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="parameterdefinition",
            name="applicability",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="parameterdefinition",
            name="definition_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="canonical_parameter_definitions",
                to="domain.projectdefinitionversion",
            ),
        ),
        migrations.AddField(
            model_name="parameterdefinition",
            name="manifest_snapshot_sha256",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="A manifest hash must be a lowercase hexadecimal SHA-256 digest.",
                        regex="^[0-9a-f]{64}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="parameterdefinition",
            name="reference_statement",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="parameterdefinition",
            name="scale_step",
            field=models.DecimalField(
                blank=True,
                decimal_places=8,
                max_digits=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="parameterdefinition",
            name="source_manifest_parameter_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="projectworkspace",
            name="assessment_projection_sha256",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="A manifest hash must be a lowercase hexadecimal SHA-256 digest.",
                        regex="^[0-9a-f]{64}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="projectworkspace",
            name="assessment_projection_status",
            field=models.CharField(
                choices=[
                    ("COMPLETE", "Complete"),
                    ("NOT_PROVEN", "Not proven"),
                    ("INTEGRITY_CONFLICT", "Integrity conflict"),
                ],
                default="NOT_PROVEN",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="parameterdefinition",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("PROJECT", "Project"),
                    ("TIME_SLICE", "Time slice"),
                    ("TENSION_POINT", "Tension point"),
                    ("PARTICIPANT_GROUP", "Participant group"),
                    ("GROUP_TENSION_RELATION", "Group-tension relation"),
                    ("ACTOR", "Actor"),
                    ("ANALYTICAL_ELEMENT", "Analytical element"),
                    ("ACTOR_ELEMENT_ROLE", "Actor-element role"),
                    ("ACTOR_ELEMENT_ASSESSMENT", "Actor-element assessment"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="parametervalue",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("PROJECT", "Project"),
                    ("TIME_SLICE", "Time slice"),
                    ("TENSION_POINT", "Tension point"),
                    ("PARTICIPANT_GROUP", "Participant group"),
                    ("GROUP_TENSION_RELATION", "Group-tension relation"),
                    ("ACTOR", "Actor"),
                    ("ANALYTICAL_ELEMENT", "Analytical element"),
                    ("ACTOR_ELEMENT_ROLE", "Actor-element role"),
                    ("ACTOR_ELEMENT_ASSESSMENT", "Actor-element assessment"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="scenariooverride",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("PROJECT", "Project"),
                    ("TIME_SLICE", "Time slice"),
                    ("TENSION_POINT", "Tension point"),
                    ("PARTICIPANT_GROUP", "Participant group"),
                    ("GROUP_TENSION_RELATION", "Group-tension relation"),
                    ("ACTOR", "Actor"),
                    ("ANALYTICAL_ELEMENT", "Analytical element"),
                    ("ACTOR_ELEMENT_ROLE", "Actor-element role"),
                    ("ACTOR_ELEMENT_ASSESSMENT", "Actor-element assessment"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="actor",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        source_manifest_entity_id__isnull=True,
                        source_manifest_entity_sha256__isnull=True,
                    )
                    | models.Q(
                        source_manifest_entity_id__isnull=False,
                        source_manifest_entity_sha256__isnull=False,
                    )
                ),
                name="domain_actor_projection_provenance_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="actor",
            constraint=models.UniqueConstraint(
                condition=models.Q(source_manifest_entity_id__isnull=False),
                fields=("workspace", "source_manifest_entity_id"),
                name="domain_actor_workspace_source_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="actorelementrole",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        source_manifest_entity_id__isnull=True,
                        source_manifest_entity_sha256__isnull=True,
                    )
                    | models.Q(
                        source_manifest_entity_id__isnull=False,
                        source_manifest_entity_sha256__isnull=False,
                    )
                ),
                name="domain_actor_role_projection_provenance_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="actorelementrole",
            constraint=models.UniqueConstraint(
                condition=models.Q(source_manifest_entity_id__isnull=False),
                fields=("workspace", "source_manifest_entity_id"),
                name="domain_actor_role_workspace_source_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticalelement",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        source_manifest_entity_id__isnull=True,
                        source_manifest_entity_sha256__isnull=True,
                    )
                    | models.Q(
                        source_manifest_entity_id__isnull=False,
                        source_manifest_entity_sha256__isnull=False,
                    )
                ),
                name="domain_element_projection_provenance_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticalelement",
            constraint=models.UniqueConstraint(
                condition=models.Q(source_manifest_entity_id__isnull=False),
                fields=("workspace", "source_manifest_entity_id"),
                name="domain_element_workspace_source_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="parameterdefinition",
            constraint=models.UniqueConstraint(
                condition=models.Q(definition_version__isnull=True),
                fields=("project", "code"),
                name="domain_parameter_legacy_project_code_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="parameterdefinition",
            constraint=models.UniqueConstraint(
                condition=models.Q(definition_version__isnull=False),
                fields=("definition_version", "code"),
                name="domain_parameter_definition_code_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="parameterdefinition",
            constraint=models.UniqueConstraint(
                condition=(
                    models.Q(definition_version__isnull=False)
                    & models.Q(source_manifest_parameter_id__isnull=False)
                ),
                fields=("definition_version", "source_manifest_parameter_id"),
                name="domain_parameter_definition_source_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="parameterdefinition",
            constraint=models.CheckConstraint(
                condition=models.Q(scale_step__isnull=True)
                | models.Q(scale_step__gt=0),
                name="domain_parameter_scale_step_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="parameterdefinition",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        definition_version__isnull=True,
                        source_manifest_parameter_id__isnull=True,
                        manifest_snapshot_sha256__isnull=True,
                    )
                    | models.Q(
                        definition_version__isnull=False,
                        source_manifest_parameter_id__isnull=False,
                        manifest_snapshot_sha256__isnull=False,
                    )
                ),
                name="domain_parameter_canonical_bridge_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="projectworkspace",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        assessment_projection_status="COMPLETE",
                        assessment_projection_sha256__isnull=False,
                    )
                    | (
                        ~models.Q(assessment_projection_status="COMPLETE")
                        & models.Q(assessment_projection_sha256__isnull=True)
                    )
                ),
                name="domain_workspace_projection_evidence",
            ),
        ),
        migrations.RunPython(
            _install_canonical_projection_guards,
            _reverse_projection_guard,
        ),
    ]
