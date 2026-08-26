import django.db.models.deletion
from django.db import migrations, models


def reject_lossy_reverse_before_schema_changes(apps, schema_editor):
    """Refuse a lossy downgrade before any 0015 DDL is reversed."""

    database = schema_editor.connection.alias
    AuditEvent = apps.get_model("domain", "AuditEvent")
    ImportRun = apps.get_model("domain", "ImportRun")
    ProjectPublication = apps.get_model("domain", "ProjectPublication")
    UIHelpBinding = apps.get_model("domain", "UIHelpBinding")

    if AuditEvent.objects.using(database).filter(scope="DEFINITION").exists():
        raise RuntimeError(
            "Cannot reverse after definition-scoped audit provenance exists."
        )
    if UIHelpBinding.objects.using(database).filter(
        workspace_id__isnull=True
    ).exists():
        raise RuntimeError(
            "Cannot reverse after pre-workspace HelpTopic bindings exist."
        )
    if ProjectPublication.objects.using(database).filter(
        initial_workspace_id__isnull=False
    ).exists():
        raise RuntimeError(
            "Cannot reverse after an initial-workspace publication receipt exists."
        )
    if ImportRun.objects.using(database).filter(
        package_scope="PROJECT_DEFINITION"
    ).exists():
        raise RuntimeError(
            "Cannot reverse after project-definition import receipts exist."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0014_foundation_studio_contract_backfill"),
    ]

    operations = [
        migrations.AlterField(
            model_name="uihelpbinding",
            name="application_scope",
            field=models.CharField(
                choices=[
                    ("STUDIO", "Studio"),
                    ("PLAYER", "Player"),
                    ("SHARED", "Shared"),
                ],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="importrun",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="import_runs",
                to="domain.project",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="helptopic",
            name="domain_help_exact_version_uniq",
        ),
        migrations.AddConstraint(
            model_name="helptopic",
            constraint=models.UniqueConstraint(
                fields=("application_scope", "stable_key", "locale", "version"),
                name="domain_help_exact_version_uniq",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="uihelpbinding",
            name="domain_ui_help_binding_uniq",
        ),
        migrations.AddConstraint(
            model_name="uihelpbinding",
            constraint=models.UniqueConstraint(
                condition=models.Q(("workspace__isnull", False)),
                fields=(
                    "workspace",
                    "application_scope",
                    "ui_key",
                    "locale",
                    "version",
                ),
                name="domain_ui_help_ws_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="uihelpbinding",
            constraint=models.UniqueConstraint(
                condition=models.Q(("workspace__isnull", True)),
                fields=("application_scope", "ui_key", "locale", "version"),
                name="domain_ui_help_global_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="uihelpbinding",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("workspace__isnull", False),
                    ("application_scope", "STUDIO"),
                    _connector="OR",
                ),
                name="domain_ui_help_global_studio",
            ),
        ),
        migrations.AddIndex(
            model_name="uihelpbinding",
            index=models.Index(
                fields=(
                    "workspace",
                    "application_scope",
                    "ui_key",
                    "locale",
                    "version",
                ),
                name="domain_ui_help_ws_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="uihelpbinding",
            index=models.Index(
                fields=("application_scope", "ui_key", "locale", "version"),
                name="domain_ui_help_global_idx",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="importrun",
            name="domain_import_run_code_uniq",
        ),
        migrations.AddConstraint(
            model_name="importrun",
            constraint=models.UniqueConstraint(
                condition=models.Q(("package_scope", "WORKSPACE")),
                fields=("workspace", "code"),
                name="domain_import_run_ws_code_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="importrun",
            constraint=models.UniqueConstraint(
                condition=models.Q(("package_scope", "PROJECT_DEFINITION")),
                fields=("project", "code"),
                name="domain_import_run_def_code_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="importrun",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("definition_version__isnull", False),
                        ("package_scope", "WORKSPACE"),
                        ("workspace__isnull", False),
                    ),
                    models.Q(
                        ("package_scope", "PROJECT_DEFINITION"),
                        ("target_assessment_set__isnull", True),
                        ("target_experiment__isnull", True),
                        ("workspace__isnull", True),
                        models.Q(
                            models.Q(("status", "COMMITTED"), _negated=True),
                            ("definition_version__isnull", False),
                            _connector="OR",
                        ),
                    ),
                    _connector="OR",
                ),
                name="domain_import_scope_boundary",
            ),
        ),
        migrations.AddIndex(
            model_name="importrun",
            index=models.Index(
                fields=("project", "package_scope", "created_at"),
                name="domain_import_scope_time_idx",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="auditevent",
            name="domain_audit_workspace_code_uniq",
        ),
        migrations.AddConstraint(
            model_name="auditevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("scope", "WORKSPACE")),
                fields=("workspace", "code"),
                name="domain_audit_ws_code_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="auditevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("scope", "DEFINITION")),
                fields=("definition_version", "code"),
                name="domain_audit_def_code_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="auditevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("definition_version__isnull", True),
                        ("scope", "WORKSPACE"),
                        ("workspace__isnull", False),
                    ),
                    models.Q(
                        ("assessment_set__isnull", True),
                        ("definition_version__isnull", False),
                        ("parameter_value__isnull", True),
                        ("scope", "DEFINITION"),
                        ("workspace__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="domain_audit_scope_boundary",
            ),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(
                fields=("definition_version", "entity_type", "entity_id"),
                name="domain_audit_def_entity_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(
                fields=("definition_version", "occurred_at"),
                name="domain_audit_def_time_idx",
            ),
        ),
        # This must remain the final forward operation. Django reverses operations
        # in the opposite order, so the guard runs before any 0015 schema change.
        migrations.RunPython(
            migrations.RunPython.noop,
            reject_lossy_reverse_before_schema_changes,
        ),
    ]
