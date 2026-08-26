import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0012_xlsx_metadata_contract"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="projectdefinitionversion",
            options={
                "ordering": ("project__code", "version"),
                "permissions": (
                    ("studio_read_definition", "Can read Studio project definitions"),
                    (
                        "studio_create_definition_draft",
                        "Can create Studio definition drafts",
                    ),
                    (
                        "studio_clone_definition_draft",
                        "Can clone Studio definition drafts",
                    ),
                    (
                        "studio_save_definition_draft",
                        "Can save Studio definition drafts",
                    ),
                    (
                        "studio_validate_definition",
                        "Can validate Studio project definitions",
                    ),
                    (
                        "studio_publish_definition",
                        "Can publish Studio project definitions",
                    ),
                ),
            },
        ),
        migrations.AlterModelOptions(
            name="importrun",
            options={
                "ordering": ("project__code", "package_scope", "-created_at"),
            },
        ),
        migrations.AlterField(
            model_name="auditevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("CREATE", "Create"),
                    ("UPDATE", "Update"),
                    ("DELETE", "Delete"),
                    ("IMPORT", "Import"),
                    ("VALIDATE", "Validate"),
                    ("PUBLISH", "Publish"),
                    ("FREEZE", "Freeze"),
                    ("LOCK", "Lock"),
                    ("UNLOCK", "Unlock"),
                    ("BOOTSTRAP", "Bootstrap"),
                ],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="auditevent",
            name="workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="audit_events",
                to="domain.projectworkspace",
            ),
        ),
        migrations.AddField(
            model_name="auditevent",
            name="definition_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="audit_events",
                to="domain.projectdefinitionversion",
            ),
        ),
        migrations.AddField(
            model_name="auditevent",
            name="scope",
            field=models.CharField(
                choices=[
                    ("WORKSPACE", "Workspace"),
                    ("DEFINITION", "Project definition"),
                ],
                default="WORKSPACE",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="projectpublication",
            name="initial_workspace",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="initial_publication",
                to="domain.projectworkspace",
            ),
        ),
        migrations.AlterField(
            model_name="uihelpbinding",
            name="workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="help_bindings",
                to="domain.projectworkspace",
            ),
        ),
        migrations.AddField(
            model_name="uihelpbinding",
            name="application_scope",
            field=models.CharField(
                blank=True,
                choices=[
                    ("STUDIO", "Studio"),
                    ("PLAYER", "Player"),
                    ("SHARED", "Shared"),
                ],
                max_length=16,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="importrun",
            name="workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="import_runs",
                to="domain.projectworkspace",
            ),
        ),
        migrations.AddField(
            model_name="importrun",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="import_runs",
                to="domain.project",
            ),
        ),
        migrations.AddField(
            model_name="importrun",
            name="definition_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="import_runs",
                to="domain.projectdefinitionversion",
            ),
        ),
        migrations.AddField(
            model_name="importrun",
            name="package_scope",
            field=models.CharField(
                choices=[
                    ("WORKSPACE", "Workspace"),
                    ("PROJECT_DEFINITION", "Project definition"),
                ],
                default="WORKSPACE",
                max_length=24,
            ),
        ),
    ]
