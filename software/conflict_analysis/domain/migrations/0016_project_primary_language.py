from django.db import migrations, models


KZ_PROJECT_ID = "3de70d1d-f4cf-535a-95b9-94c0a65e60e3"
KZ_PROJECT_CODE = "KZ-ZHANAOZEN-DEMO"


def backfill_project_primary_language(apps, schema_editor):
    database = schema_editor.connection.alias
    Project = apps.get_model("domain", "Project")
    projects = Project.objects.using(database)

    # Start from the deterministic conservative state, then admit only the
    # exact durable demo identity.  Neither a matching UUID nor code alone is
    # authority to infer Russian.
    projects.update(
        primary_language_tag="und",
        primary_language_assignment="LEGACY_UNKNOWN",
    )
    projects.filter(id=KZ_PROJECT_ID, code=KZ_PROJECT_CODE).update(
        primary_language_tag="ru",
        primary_language_assignment="EXPLICIT",
    )


def clear_project_primary_language(apps, schema_editor):
    database = schema_editor.connection.alias
    Project = apps.get_model("domain", "Project")
    Project.objects.using(database).update(
        primary_language_tag=None,
        primary_language_assignment=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0015_foundation_studio_contract_constraints"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="project",
            options={"base_manager_name": "objects", "ordering": ("code",)},
        ),
        migrations.AddField(
            model_name="project",
            name="primary_language_tag",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="project",
            name="primary_language_assignment",
            field=models.CharField(
                choices=[
                    ("EXPLICIT", "Explicit"),
                    ("LEGACY_UNKNOWN", "Legacy unknown"),
                ],
                max_length=16,
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_project_primary_language,
            clear_project_primary_language,
        ),
        migrations.AlterField(
            model_name="project",
            name="primary_language_tag",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="project",
            name="primary_language_assignment",
            field=models.CharField(
                choices=[
                    ("EXPLICIT", "Explicit"),
                    ("LEGACY_UNKNOWN", "Legacy unknown"),
                ],
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(primary_language_assignment="EXPLICIT")
                    & ~models.Q(primary_language_tag="und")
                    & ~models.Q(primary_language_tag="")
                    | models.Q(
                        primary_language_assignment="LEGACY_UNKNOWN",
                        primary_language_tag="und",
                    )
                ),
                name="domain_project_language_pair",
            ),
        ),
    ]
