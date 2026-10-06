"""Strengthen FD08 canonical-row and workspace-pin database guards.

The application projection context now has a matching database-side insert
lease. Canonical rows may be inserted only inside that bounded context; once
inserted they remain immutable. Workspace definition pins are immutable at the
database layer and projection evidence can change only inside the same bounded
projection context.
"""

from django.db import migrations


_CANONICAL_GUARDS = (
    ("domain_actor", "source_manifest_entity_id", "actor"),
    ("domain_analyticalelement", "source_manifest_entity_id", "element"),
    ("domain_actorelementrole", "source_manifest_entity_id", "role"),
    ("domain_parameterdefinition", "definition_version_id", "parameter"),
)
_GUARD_FUNCTION = "domain_fd08_projection_write_authorized"
_GUARD_SETTING = "domain.fd08_projection_write_authorized"


def _install_authority_guards(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            for table, marker, label in _CANONICAL_GUARDS:
                for operation in ("insert", "update", "delete"):
                    cursor.execute(
                        f"DROP TRIGGER IF EXISTS "
                        f"{quote(f'domain_fd08_{label}_canonical_{operation}')}"
                    )
                cursor.execute(
                    f"CREATE TRIGGER {quote(f'domain_fd08_{label}_canonical_insert')} "
                    f"BEFORE INSERT ON {quote(table)} FOR EACH ROW "
                    f"WHEN NEW.{quote(marker)} IS NOT NULL "
                    f"AND COALESCE({_GUARD_FUNCTION}(), 0) != 1 "
                    "BEGIN SELECT RAISE(ABORT, "
                    "'FD08_CANONICAL_PROJECTION_INSERT_AUTHORITY_REQUIRED'); END"
                )
                cursor.execute(
                    f"CREATE TRIGGER {quote(f'domain_fd08_{label}_canonical_update')} "
                    f"BEFORE UPDATE ON {quote(table)} FOR EACH ROW "
                    f"WHEN OLD.{quote(marker)} IS NOT NULL "
                    f"OR NEW.{quote(marker)} IS NOT NULL "
                    "BEGIN SELECT RAISE(ABORT, "
                    "'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN'); END"
                )
                cursor.execute(
                    f"CREATE TRIGGER {quote(f'domain_fd08_{label}_canonical_delete')} "
                    f"BEFORE DELETE ON {quote(table)} FOR EACH ROW "
                    f"WHEN OLD.{quote(marker)} IS NOT NULL "
                    "BEGIN SELECT RAISE(ABORT, "
                    "'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN'); END"
                )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote('domain_fd08_workspace_pin_update')}"
            )
            cursor.execute(
                f"CREATE TRIGGER {quote('domain_fd08_workspace_pin_update')} "
                f"BEFORE UPDATE ON {quote('domain_projectworkspace')} FOR EACH ROW "
                "WHEN OLD.definition_version_id IS NOT NEW.definition_version_id "
                "OR OLD.definition_manifest_hash IS NOT NEW.definition_manifest_hash "
                "BEGIN SELECT RAISE(ABORT, "
                "'FD08_WORKSPACE_DEFINITION_PIN_MUTATION_FORBIDDEN'); END"
            )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS "
                f"{quote('domain_fd08_workspace_projection_evidence_update')}"
            )
            cursor.execute(
                f"CREATE TRIGGER "
                f"{quote('domain_fd08_workspace_projection_evidence_update')} "
                f"BEFORE UPDATE ON {quote('domain_projectworkspace')} FOR EACH ROW "
                "WHEN (OLD.assessment_projection_status "
                "IS NOT NEW.assessment_projection_status "
                "OR OLD.assessment_projection_sha256 "
                "IS NOT NEW.assessment_projection_sha256) "
                f"AND COALESCE({_GUARD_FUNCTION}(), 0) != 1 "
                "BEGIN SELECT RAISE(ABORT, "
                "'FD08_WORKSPACE_PROJECTION_EVIDENCE_AUTHORITY_REQUIRED'); END"
            )
            return

        if connection.vendor == "postgresql":
            cursor.execute(
                "CREATE OR REPLACE FUNCTION "
                "domain_fd08_block_canonical_projection_mutation() "
                "RETURNS trigger AS $$ "
                "DECLARE old_canonical boolean := false; "
                "DECLARE new_canonical boolean := false; "
                "DECLARE authorized boolean := false; "
                "BEGIN "
                "authorized := COALESCE(current_setting("
                f"'{_GUARD_SETTING}', true), '') = '1'; "
                "IF TG_OP <> 'INSERT' THEN "
                "old_canonical := "
                "(to_jsonb(OLD) ->> 'source_manifest_entity_id') IS NOT NULL "
                "OR (to_jsonb(OLD) ->> 'definition_version_id') IS NOT NULL; "
                "END IF; "
                "IF TG_OP <> 'DELETE' THEN "
                "new_canonical := "
                "(to_jsonb(NEW) ->> 'source_manifest_entity_id') IS NOT NULL "
                "OR (to_jsonb(NEW) ->> 'definition_version_id') IS NOT NULL; "
                "END IF; "
                "IF TG_OP = 'INSERT' THEN "
                "IF new_canonical AND NOT authorized THEN "
                "RAISE EXCEPTION "
                "'FD08_CANONICAL_PROJECTION_INSERT_AUTHORITY_REQUIRED'; "
                "END IF; RETURN NEW; "
                "ELSIF TG_OP = 'UPDATE' THEN "
                "IF old_canonical OR new_canonical THEN "
                "RAISE EXCEPTION "
                "'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN'; "
                "END IF; RETURN NEW; "
                "ELSE "
                "IF old_canonical THEN "
                "RAISE EXCEPTION "
                "'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN'; "
                "END IF; RETURN OLD; "
                "END IF; "
                "END; $$ LANGUAGE plpgsql"
            )
            for table, _marker, label in _CANONICAL_GUARDS:
                trigger = f"domain_fd08_{label}_canonical_mutation"
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS {quote(trigger)} ON {quote(table)}"
                )
                cursor.execute(
                    f"CREATE TRIGGER {quote(trigger)} "
                    f"BEFORE INSERT OR UPDATE OR DELETE ON {quote(table)} "
                    "FOR EACH ROW EXECUTE FUNCTION "
                    "domain_fd08_block_canonical_projection_mutation()"
                )
            cursor.execute(
                "CREATE OR REPLACE FUNCTION "
                "domain_fd08_guard_workspace_projection() "
                "RETURNS trigger AS $$ "
                "DECLARE authorized boolean := false; "
                "BEGIN "
                "authorized := COALESCE(current_setting("
                f"'{_GUARD_SETTING}', true), '') = '1'; "
                "IF OLD.definition_version_id IS DISTINCT FROM NEW.definition_version_id "
                "OR OLD.definition_manifest_hash IS DISTINCT FROM "
                "NEW.definition_manifest_hash THEN "
                "RAISE EXCEPTION "
                "'FD08_WORKSPACE_DEFINITION_PIN_MUTATION_FORBIDDEN'; "
                "END IF; "
                "IF (OLD.assessment_projection_status IS DISTINCT FROM "
                "NEW.assessment_projection_status "
                "OR OLD.assessment_projection_sha256 IS DISTINCT FROM "
                "NEW.assessment_projection_sha256) AND NOT authorized THEN "
                "RAISE EXCEPTION "
                "'FD08_WORKSPACE_PROJECTION_EVIDENCE_AUTHORITY_REQUIRED'; "
                "END IF; "
                "RETURN NEW; "
                "END; $$ LANGUAGE plpgsql"
            )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS "
                f"{quote('domain_fd08_workspace_projection_guard')} "
                f"ON {quote('domain_projectworkspace')}"
            )
            cursor.execute(
                f"CREATE TRIGGER {quote('domain_fd08_workspace_projection_guard')} "
                f"BEFORE UPDATE ON {quote('domain_projectworkspace')} "
                "FOR EACH ROW EXECUTE FUNCTION "
                "domain_fd08_guard_workspace_projection()"
            )


def _drop_authority_guards(schema_editor):
    connection = schema_editor.connection
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            for _table, _marker, label in _CANONICAL_GUARDS:
                for operation in ("insert", "update", "delete"):
                    cursor.execute(
                        f"DROP TRIGGER IF EXISTS "
                        f"{quote(f'domain_fd08_{label}_canonical_{operation}')}"
                    )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote('domain_fd08_workspace_pin_update')}"
            )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS "
                f"{quote('domain_fd08_workspace_projection_evidence_update')}"
            )
        elif connection.vendor == "postgresql":
            for table, _marker, label in _CANONICAL_GUARDS:
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS "
                    f"{quote(f'domain_fd08_{label}_canonical_mutation')} "
                    f"ON {quote(table)}"
                )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS "
                f"{quote('domain_fd08_workspace_projection_guard')} "
                f"ON {quote('domain_projectworkspace')}"
            )
            cursor.execute(
                "DROP FUNCTION IF EXISTS "
                "domain_fd08_block_canonical_projection_mutation()"
            )
            cursor.execute(
                "DROP FUNCTION IF EXISTS "
                "domain_fd08_guard_workspace_projection()"
            )


def _install_legacy_guards(schema_editor):
    """Restore the exact 0018 guard shape when this migration is reversed."""

    connection = schema_editor.connection
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            for table, marker, label in _CANONICAL_GUARDS:
                for operation in ("UPDATE", "DELETE"):
                    trigger = f"domain_fd08_{label}_canonical_{operation.lower()}"
                    cursor.execute(f"DROP TRIGGER IF EXISTS {quote(trigger)}")
                    cursor.execute(
                        f"CREATE TRIGGER {quote(trigger)} "
                        f"BEFORE {operation} ON {quote(table)} FOR EACH ROW "
                        f"WHEN OLD.{quote(marker)} IS NOT NULL "
                        "BEGIN SELECT RAISE(ABORT, "
                        "'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN'); END"
                    )
            return
        if connection.vendor == "postgresql":
            cursor.execute(
                "CREATE OR REPLACE FUNCTION "
                "domain_fd08_block_canonical_projection_mutation() "
                "RETURNS trigger AS $$ BEGIN "
                "IF (to_jsonb(OLD) ->> 'source_manifest_entity_id') IS NOT NULL "
                "OR (to_jsonb(OLD) ->> 'definition_version_id') IS NOT NULL THEN "
                "RAISE EXCEPTION 'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN'; "
                "END IF; "
                "IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; "
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


def _reverse_authority_guards(apps, schema_editor):
    del apps
    _drop_authority_guards(schema_editor)
    _install_legacy_guards(schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("domain", "0018_workspace_assessment_projection"),
    ]

    operations = [
        migrations.RunPython(_install_authority_guards, _reverse_authority_guards),
    ]
