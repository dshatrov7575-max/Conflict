from django.db import migrations


def backfill_contract_boundaries(apps, schema_editor):
    database = schema_editor.connection.alias
    AuditEvent = apps.get_model("domain", "AuditEvent")
    HelpTopic = apps.get_model("domain", "HelpTopic")
    ImportRun = apps.get_model("domain", "ImportRun")
    ProjectWorkspace = apps.get_model("domain", "ProjectWorkspace")
    UIHelpBinding = apps.get_model("domain", "UIHelpBinding")

    audit_events = AuditEvent.objects.using(database)
    if audit_events.filter(workspace_id__isnull=True).exists():
        raise RuntimeError(
            "Cannot classify a legacy AuditEvent without its exact workspace."
        )
    audit_events.update(scope="WORKSPACE", definition_version_id=None)

    topics = dict(
        HelpTopic.objects.using(database).values_list("id", "application_scope")
    )
    bindings = UIHelpBinding.objects.using(database)
    for binding_id, topic_id in bindings.values_list("id", "help_topic_id").iterator():
        application_scope = topics.get(topic_id)
        if not application_scope:
            raise RuntimeError(
                f"Cannot backfill UIHelpBinding {binding_id}: HelpTopic is missing."
            )
        bindings.filter(pk=binding_id).update(application_scope=application_scope)

    workspaces = {
        row["id"]: row
        for row in ProjectWorkspace.objects.using(database).values(
            "id", "project_id", "definition_version_id"
        )
    }
    import_runs = ImportRun.objects.using(database)
    for receipt_id, workspace_id in import_runs.values_list(
        "id", "workspace_id"
    ).iterator():
        workspace = workspaces.get(workspace_id)
        if workspace is None:
            raise RuntimeError(
                f"Cannot backfill ImportRun {receipt_id}: workspace is missing."
            )
        if workspace["definition_version_id"] is None:
            raise RuntimeError(
                f"Cannot backfill ImportRun {receipt_id}: workspace has no definition pin."
            )
        import_runs.filter(pk=receipt_id).update(
            project_id=workspace["project_id"],
            definition_version_id=workspace["definition_version_id"],
            package_scope="WORKSPACE",
        )


def reject_lossy_reverse(apps, schema_editor):
    database = schema_editor.connection.alias
    AuditEvent = apps.get_model("domain", "AuditEvent")
    ImportRun = apps.get_model("domain", "ImportRun")
    ProjectPublication = apps.get_model("domain", "ProjectPublication")
    UIHelpBinding = apps.get_model("domain", "UIHelpBinding")

    if AuditEvent.objects.using(database).filter(scope="DEFINITION").exists():
        raise RuntimeError(
            "Cannot reverse after definition-scoped audit provenance exists."
        )
    if UIHelpBinding.objects.using(database).filter(workspace_id__isnull=True).exists():
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
        ("domain", "0013_foundation_studio_contract_fields"),
    ]

    operations = [
        migrations.RunPython(
            backfill_contract_boundaries,
            reject_lossy_reverse,
        ),
    ]
