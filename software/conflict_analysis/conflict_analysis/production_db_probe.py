"""Machine-readable PostgreSQL authority probe for the production web runtime."""

from __future__ import annotations

import json
import os

import django
from django.db import connection


def snapshot() -> dict[str, object]:
    django.setup()
    if connection.vendor != "postgresql":
        raise RuntimeError("Production database authority probe requires PostgreSQL")

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user, current_database()")
        current_user, database_name = cursor.fetchone()

        cursor.execute(
            """
            SELECT oid, rolsuper, rolcreatedb, rolcreaterole, rolinherit,
                   rolreplication, rolbypassrls
            FROM pg_roles
            WHERE rolname = current_user
            """
        )
        (
            runtime_oid,
            rolsuper,
            rolcreatedb,
            rolcreaterole,
            rolinherit,
            rolreplication,
            rolbypassrls,
        ) = cursor.fetchone()

        cursor.execute(
            """
            SELECT pg_get_userbyid(datdba)
            FROM pg_database
            WHERE datname = current_database()
            """
        )
        database_owner = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT pg_get_userbyid(relowner)
            FROM pg_class
            WHERE oid = 'domain_auditevent'::regclass
            """
        )
        audit_owner = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM pg_auth_members WHERE member = %s",
            [runtime_oid],
        )
        role_memberships = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE relation.relowner = %s
              AND namespace.nspname NOT IN ('pg_catalog', 'information_schema')
              AND namespace.nspname NOT LIKE 'pg_toast%%'
            """,
            [runtime_oid],
        )
        owned_relations = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM pg_namespace
            WHERE nspowner = %s
              AND nspname NOT LIKE 'pg_%%'
              AND nspname <> 'information_schema'
            """,
            [runtime_oid],
        )
        owned_schemas = int(cursor.fetchone()[0])

        cursor.execute(
            "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
        )
        schema_create = bool(cursor.fetchone()[0])
        cursor.execute(
            "SELECT has_database_privilege(current_user, current_database(), 'TEMPORARY')"
        )
        database_temp = bool(cursor.fetchone()[0])

        audit_privileges: dict[str, bool] = {}
        for privilege in (
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
            "TRIGGER",
        ):
            cursor.execute(
                "SELECT has_table_privilege(current_user, 'domain_auditevent', %s)",
                [privilege],
            )
            audit_privileges[privilege.lower()] = bool(cursor.fetchone()[0])

        capability_privileges: dict[str, bool] = {}
        for privilege in (
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
            "REFERENCES",
            "TRIGGER",
        ):
            cursor.execute(
                "SELECT has_table_privilege("
                "current_user, 'domain_fd08_projection_authority_secret', %s"
                ")",
                [privilege],
            )
            capability_privileges[privilege.lower()] = bool(cursor.fetchone()[0])

        migration_privileges: dict[str, bool] = {}
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
            cursor.execute(
                "SELECT has_table_privilege(current_user, 'django_migrations', %s)",
                [privilege],
            )
            migration_privileges[privilege.lower()] = bool(cursor.fetchone()[0])

        cursor.execute("SELECT pg_get_serial_sequence('django_migrations', 'id')")
        migration_sequence = cursor.fetchone()[0]
        migration_sequence_update = None
        if migration_sequence:
            cursor.execute(
                "SELECT has_sequence_privilege(current_user, %s, 'UPDATE')",
                [migration_sequence],
            )
            migration_sequence_update = bool(cursor.fetchone()[0])

    return {
        "status": "PASS",
        "database": database_name,
        "current_user": current_user,
        "configured_user": connection.settings_dict["USER"],
        "database_owner": database_owner,
        "audit_owner": audit_owner,
        "runtime_is_database_owner": current_user == database_owner,
        "runtime_is_audit_owner": current_user == audit_owner,
        "role_memberships": role_memberships,
        "owned_relations": owned_relations,
        "owned_schemas": owned_schemas,
        "schema_create": schema_create,
        "database_temp": database_temp,
        "role_flags": {
            "superuser": bool(rolsuper),
            "createdb": bool(rolcreatedb),
            "createrole": bool(rolcreaterole),
            "inherit": bool(rolinherit),
            "replication": bool(rolreplication),
            "bypassrls": bool(rolbypassrls),
        },
        "audit_privileges": audit_privileges,
        "capability_privileges": capability_privileges,
        "migration_privileges": migration_privileges,
        "migration_sequence_update": migration_sequence_update,
        "migration_user_env_present": bool(
            os.getenv("POSTGRES_MIGRATION_USER")
            or os.getenv("POSTGRES_MIGRATION_PASSWORD")
        ),
        "postgres_password_present": bool(os.getenv("POSTGRES_PASSWORD")),
        "fd08_projection_secret_present": bool(
            os.getenv("FD08_PROJECTION_LEASE_SECRET")
        ),
    }


def main() -> None:
    print(json.dumps(snapshot(), sort_keys=True))


if __name__ == "__main__":
    main()
