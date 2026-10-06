from __future__ import annotations

import json
import os
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from psycopg import sql


_ROLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise CommandError(f"{name} is required")
    return value


class Command(BaseCommand):
    help = "Provision the least-privilege PostgreSQL runtime role after migrations."

    def handle(self, *args, **options):
        del args, options
        if connection.vendor != "postgresql":
            raise CommandError("Runtime database role provisioning requires PostgreSQL.")

        runtime_user = _required("POSTGRES_RUNTIME_USER")
        runtime_password = _required("POSTGRES_RUNTIME_PASSWORD")
        projection_capability = _required("FD08_PROJECTION_CAPABILITY_TOKEN")
        if len(projection_capability) < 32:
            raise CommandError(
                "FD08_PROJECTION_CAPABILITY_TOKEN must be at least 32 characters."
            )
        if not _ROLE_RE.fullmatch(runtime_user):
            raise CommandError("POSTGRES_RUNTIME_USER is not a safe PostgreSQL role identifier.")
        if len(runtime_password) < 20 or runtime_password == runtime_user:
            raise CommandError(
                "POSTGRES_RUNTIME_PASSWORD must be at least 20 characters and differ from the role name."
            )

        database_name = connection.settings_dict["NAME"]
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                migration_user = cursor.fetchone()[0]
                if runtime_user == migration_user:
                    raise CommandError(
                        "Runtime and migration PostgreSQL roles must be distinct."
                    )

                cursor.execute(
                    "SELECT 1 FROM pg_roles WHERE rolname = %s",
                    [runtime_user],
                )
                role_exists = cursor.fetchone() is not None
                role_ident = sql.Identifier(runtime_user)
                password_literal = sql.Literal(runtime_password)
                if role_exists:
                    cursor.execute(
                        sql.SQL(
                            "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                            "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}"
                        ).format(role_ident, password_literal)
                    )
                else:
                    cursor.execute(
                        sql.SQL(
                            "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                            "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}"
                        ).format(role_ident, password_literal)
                    )

                db_ident = sql.Identifier(str(database_name))
                # Production uses a dedicated database. Remove PUBLIC object-creation
                # paths so runtime cannot recover authority through pg_temp or a
                # writable schema inherited from PUBLIC.
                cursor.execute(
                    sql.SQL(
                        "REVOKE TEMPORARY, CREATE ON DATABASE {} FROM PUBLIC"
                    ).format(db_ident)
                )
                cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                cursor.execute(
                    sql.SQL(
                        "ALTER ROLE {} SET search_path = pg_catalog, public"
                    ).format(role_ident)
                )
                # Reset direct privileges first so an existing runtime role cannot
                # retain stale DDL/DML authority from an earlier deployment.
                cursor.execute(
                    sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(
                        db_ident,
                        role_ident,
                    )
                )
                cursor.execute(
                    sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA public FROM {}").format(
                        role_ident
                    )
                )
                cursor.execute(
                    sql.SQL(
                        "REVOKE ALL PRIVILEGES ON ALL TABLES "
                        "IN SCHEMA public FROM {}"
                    ).format(role_ident)
                )
                cursor.execute(
                    sql.SQL(
                        "REVOKE ALL PRIVILEGES ON ALL SEQUENCES "
                        "IN SCHEMA public FROM {}"
                    ).format(role_ident)
                )
                cursor.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        db_ident,
                        role_ident,
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role_ident)
                )
                cursor.execute(
                    sql.SQL(
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                        "IN SCHEMA public TO {}"
                    ).format(role_ident)
                )
                cursor.execute(
                    sql.SQL(
                        "GRANT USAGE, SELECT ON ALL SEQUENCES "
                        "IN SCHEMA public TO {}"
                    ).format(role_ident)
                )
                cursor.execute(
                    """
                    INSERT INTO domain_fd08_projection_capability
                        (singleton, token, updated_at)
                    VALUES (true, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (singleton) DO UPDATE
                    SET token = EXCLUDED.token, updated_at = EXCLUDED.updated_at
                    """,
                    [projection_capability],
                )
                # No ALTER DEFAULT PRIVILEGES: this command is deliberately
                # rerun after every migration and grants only the tables/sequences
                # that actually exist at that checkpoint before applying the deny-list.
                for table in (
                    "domain_auditevent",
                    "django_migrations",
                    "domain_fd08_projection_capability",
                ):
                    table_ident = sql.Identifier(table)
                    cursor.execute(
                        sql.SQL("REVOKE UPDATE, DELETE ON TABLE {} FROM {}").format(
                            table_ident,
                            role_ident,
                        )
                    )
                cursor.execute(
                    sql.SQL(
                        "REVOKE INSERT ON TABLE django_migrations FROM {}"
                    ).format(role_ident)
                )
                cursor.execute(
                    sql.SQL(
                        "REVOKE SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER "
                        "ON TABLE domain_fd08_projection_capability FROM {}"
                    ).format(role_ident)
                )

                cursor.execute(
                    """
                    SELECT rolsuper, rolcreatedb, rolcreaterole, rolinherit,
                           rolreplication, rolbypassrls
                    FROM pg_roles
                    WHERE rolname = %s
                    """,
                    [runtime_user],
                )
                flags = cursor.fetchone()
                if flags != (False, False, False, False, False, False):
                    raise CommandError("Runtime PostgreSQL role retained privileged attributes.")

                checks = {}
                for privilege in (
                    "SELECT",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "TRUNCATE",
                    "TRIGGER",
                ):
                    cursor.execute(
                        "SELECT has_table_privilege(%s, 'domain_auditevent', %s)",
                        [runtime_user, privilege],
                    )
                    checks[f"audit_{privilege.lower()}"] = bool(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT has_schema_privilege(%s, 'public', 'CREATE')",
                    [runtime_user],
                )
                checks["schema_create"] = bool(cursor.fetchone()[0])
                cursor.execute(
                    """
                    SELECT oid
                    FROM pg_roles
                    WHERE rolname = %s
                    """,
                    [runtime_user],
                )
                runtime_oid = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM pg_auth_members WHERE member = %s",
                    [runtime_oid],
                )
                checks["role_memberships"] = int(cursor.fetchone()[0])
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
                checks["owned_relations"] = int(cursor.fetchone()[0])
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
                checks["owned_schemas"] = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    SELECT datdba = %s
                    FROM pg_database
                    WHERE datname = current_database()
                    """,
                    [runtime_oid],
                )
                checks["database_owned_by_runtime"] = bool(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT has_database_privilege(%s, current_database(), 'CREATE')",
                    [runtime_user],
                )
                checks["database_create"] = bool(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT has_database_privilege(%s, current_database(), 'TEMPORARY')",
                    [runtime_user],
                )
                checks["database_temp"] = bool(cursor.fetchone()[0])
                cursor.execute(
                    """
                    SELECT pg_get_userbyid(relowner)
                    FROM pg_class
                    WHERE oid = 'domain_auditevent'::regclass
                    """
                )
                audit_owner = cursor.fetchone()[0]
                checks["audit_owned_by_runtime"] = audit_owner == runtime_user
                cursor.execute(
                    "SELECT has_table_privilege(%s, "
                    "'domain_fd08_projection_capability', 'SELECT')",
                    [runtime_user],
                )
                checks["projection_capability_select"] = bool(cursor.fetchone()[0])
                if checks != {
                    "audit_select": True,
                    "audit_insert": True,
                    "audit_update": False,
                    "audit_delete": False,
                    "audit_truncate": False,
                    "audit_trigger": False,
                    "schema_create": False,
                    "role_memberships": 0,
                    "owned_relations": 0,
                    "owned_schemas": 0,
                    "database_owned_by_runtime": False,
                    "database_create": False,
                    "database_temp": False,
                    "audit_owned_by_runtime": False,
                    "projection_capability_select": False,
                }:
                    raise CommandError(
                        f"Runtime PostgreSQL privilege verification failed: {checks!r}"
                    )

        self.stdout.write(
            json.dumps(
                {
                    "status": "PASS",
                    "migration_role": migration_user,
                    "runtime_role": runtime_user,
                    "runtime_superuser": False,
                    "runtime_create_db": False,
                    "runtime_create_role": False,
                    "runtime_inherit": False,
                    "runtime_replication": False,
                    "runtime_bypass_rls": False,
                    **checks,
                },
                sort_keys=True,
            )
        )
