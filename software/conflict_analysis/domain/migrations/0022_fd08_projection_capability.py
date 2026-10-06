"""Replace the spoofable FD08 boolean GUC with a protected DB capability.

The PostgreSQL runtime role may set arbitrary custom GUC values, so a boolean
session flag cannot prove canonical projection authority.  This migration
stores one high-entropy capability in an owner-only table and makes both FD08
trigger functions SECURITY DEFINER readers of that table.  Runtime can present
the capability transaction-locally, but cannot read or alter the authoritative
copy through database privileges.
"""

from django.conf import settings
from django.db import migrations


_SECRET_TABLE = "domain_fd08_projection_authority_secret"
_CAPABILITY_SETTING = "domain.fd08_projection_write_capability"
_LEGACY_SETTING = "domain.fd08_projection_write_authorized"


def _secret() -> str:
    value = str(getattr(settings, "FD08_PROJECTION_LEASE_SECRET", ""))
    if len(value) < 32:
        raise RuntimeError(
            "FD08_PROJECTION_LEASE_SECRET must contain at least 32 characters."
        )
    return value


def _install(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_SECRET_TABLE} (
                singleton boolean PRIMARY KEY DEFAULT TRUE
                    CHECK (singleton IS TRUE),
                secret text NOT NULL CHECK (char_length(secret) >= 32)
            )
            """
        )
        cursor.execute(
            f"""
            INSERT INTO {_SECRET_TABLE} (singleton, secret)
            VALUES (TRUE, %s)
            ON CONFLICT (singleton)
            DO UPDATE SET secret = EXCLUDED.secret
            """,
            [_secret()],
        )
        cursor.execute(f"REVOKE ALL ON TABLE {_SECRET_TABLE} FROM PUBLIC")

        cursor.execute(
            f"""
            CREATE OR REPLACE FUNCTION domain_fd08_block_canonical_projection_mutation()
            RETURNS trigger AS $$
            DECLARE
                old_canonical boolean := false;
                new_canonical boolean := false;
                authorized boolean := false;
            BEGIN
                SELECT EXISTS (
                    SELECT 1
                    FROM {_SECRET_TABLE} AS capability
                    WHERE capability.singleton IS TRUE
                      AND capability.secret = COALESCE(
                          current_setting('{_CAPABILITY_SETTING}', true),
                          ''
                      )
                      AND capability.secret <> ''
                ) INTO authorized;

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
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            """
        )
        cursor.execute(
            "REVOKE ALL ON FUNCTION "
            "domain_fd08_block_canonical_projection_mutation() FROM PUBLIC"
        )

        cursor.execute(
            f"""
            CREATE OR REPLACE FUNCTION domain_fd08_guard_workspace_projection()
            RETURNS trigger AS $$
            DECLARE
                authorized boolean := false;
            BEGIN
                SELECT EXISTS (
                    SELECT 1
                    FROM {_SECRET_TABLE} AS capability
                    WHERE capability.singleton IS TRUE
                      AND capability.secret = COALESCE(
                          current_setting('{_CAPABILITY_SETTING}', true),
                          ''
                      )
                      AND capability.secret <> ''
                ) INTO authorized;

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
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            """
        )
        cursor.execute(
            "REVOKE ALL ON FUNCTION "
            "domain_fd08_guard_workspace_projection() FROM PUBLIC"
        )


def _reverse(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE OR REPLACE FUNCTION domain_fd08_block_canonical_projection_mutation()
            RETURNS trigger AS $$
            DECLARE
                old_canonical boolean := false;
                new_canonical boolean := false;
                authorized boolean := false;
            BEGIN
                authorized := COALESCE(
                    current_setting('{_LEGACY_SETTING}', true),
                    ''
                ) = '1';
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
            f"""
            CREATE OR REPLACE FUNCTION domain_fd08_guard_workspace_projection()
            RETURNS trigger AS $$
            DECLARE
                authorized boolean := false;
            BEGIN
                authorized := COALESCE(
                    current_setting('{_LEGACY_SETTING}', true),
                    ''
                ) = '1';
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
        cursor.execute(f"DROP TABLE IF EXISTS {_SECRET_TABLE}")


class Migration(migrations.Migration):
    dependencies = [("domain", "0021_audit_event_db_immutability")]

    operations = [
        migrations.RunPython(_install, _reverse),
    ]
