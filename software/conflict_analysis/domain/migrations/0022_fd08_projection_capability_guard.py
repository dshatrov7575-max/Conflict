from importlib import import_module

from django.db import migrations


CAPABILITY_TABLE = "domain_fd08_projection_capability"
GUARD_SETTING = "domain.fd08_projection_write_capability"


def _authority_migration():
    return import_module("domain.migrations.0019_projection_db_authority_guards")


def _install_capability_guards(apps, schema_editor):
    # Rebuild the underlying FD08 guard generation first. This is intentionally
    # idempotent and also makes TransactionTestCase teardown/reinstall exact.
    _authority_migration()._install_authority_guards(apps, schema_editor)

    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {CAPABILITY_TABLE} (
                singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
                token text NOT NULL CHECK (length(token) >= 32),
                updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(f"REVOKE ALL ON TABLE {CAPABILITY_TABLE} FROM PUBLIC")
        cursor.execute(
            f"""
            CREATE OR REPLACE FUNCTION domain_fd08_projection_authorized()
            RETURNS boolean
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $$
            DECLARE expected_token text;
            DECLARE supplied_token text;
            BEGIN
                SELECT token INTO expected_token
                  FROM public.{CAPABILITY_TABLE}
                 WHERE singleton = true;
                supplied_token := current_setting('{GUARD_SETTING}', true);
                RETURN expected_token IS NOT NULL
                   AND supplied_token IS NOT NULL
                   AND length(supplied_token) >= 32
                   AND supplied_token = expected_token;
            END;
            $$ LANGUAGE plpgsql STABLE
            """
        )
        cursor.execute(
            "GRANT EXECUTE ON FUNCTION domain_fd08_projection_authorized() TO PUBLIC"
        )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION domain_fd08_block_canonical_projection_mutation()
            RETURNS trigger AS $$
            DECLARE old_canonical boolean := false;
            DECLARE new_canonical boolean := false;
            DECLARE authorized boolean := false;
            BEGIN
                authorized := domain_fd08_projection_authorized();
                IF TG_OP <> 'INSERT' THEN
                    old_canonical :=
                        (to_jsonb(OLD) ->> 'source_manifest_entity_id') IS NOT NULL
                        OR (to_jsonb(OLD) ->> 'definition_version_id') IS NOT NULL;
                END IF;
                IF TG_OP <> 'DELETE' THEN
                    new_canonical :=
                        (to_jsonb(NEW) ->> 'source_manifest_entity_id') IS NOT NULL
                        OR (to_jsonb(NEW) ->> 'definition_version_id') IS NOT NULL;
                END IF;
                IF TG_OP = 'INSERT' THEN
                    IF new_canonical AND NOT authorized THEN
                        RAISE EXCEPTION
                            'FD08_CANONICAL_PROJECTION_INSERT_AUTHORITY_REQUIRED';
                    END IF;
                    RETURN NEW;
                ELSIF TG_OP = 'UPDATE' THEN
                    IF old_canonical OR new_canonical THEN
                        RAISE EXCEPTION
                            'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN';
                    END IF;
                    RETURN NEW;
                ELSE
                    IF old_canonical THEN
                        RAISE EXCEPTION
                            'FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN';
                    END IF;
                    RETURN OLD;
                END IF;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION domain_fd08_guard_workspace_projection()
            RETURNS trigger AS $$
            DECLARE authorized boolean := false;
            BEGIN
                authorized := domain_fd08_projection_authorized();
                IF OLD.definition_version_id IS DISTINCT FROM NEW.definition_version_id
                   OR OLD.definition_manifest_hash IS DISTINCT FROM
                      NEW.definition_manifest_hash THEN
                    RAISE EXCEPTION
                        'FD08_WORKSPACE_DEFINITION_PIN_MUTATION_FORBIDDEN';
                END IF;
                IF (
                    OLD.assessment_projection_status IS DISTINCT FROM
                        NEW.assessment_projection_status
                    OR OLD.assessment_projection_sha256 IS DISTINCT FROM
                        NEW.assessment_projection_sha256
                ) AND NOT authorized THEN
                    RAISE EXCEPTION
                        'FD08_WORKSPACE_PROJECTION_EVIDENCE_AUTHORITY_REQUIRED';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )


def _drop_capability_guards(schema_editor):
    connection = schema_editor.connection

    # Drop the row triggers/functions owned by the underlying generation too.
    # On SQLite this is the only active FD08 database guard generation.
    _authority_migration()._drop_authority_guards(schema_editor)

    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "DROP FUNCTION IF EXISTS domain_fd08_projection_authorized()"
        )
        cursor.execute(f"DROP TABLE IF EXISTS {CAPABILITY_TABLE}")


def _reverse_capability_guards(apps, schema_editor):
    _drop_capability_guards(schema_editor)
    _authority_migration()._install_authority_guards(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [("domain", "0021_audit_event_db_immutability")]

    operations = [
        migrations.RunPython(
            _install_capability_guards,
            _reverse_capability_guards,
        )
    ]
