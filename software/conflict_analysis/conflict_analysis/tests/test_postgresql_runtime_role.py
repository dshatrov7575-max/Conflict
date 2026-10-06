from __future__ import annotations

import io
import json
import os
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase
import psycopg
from psycopg import sql


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only runtime role contract")
class PostgreSQLRuntimeRoleTests(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        super().setUp()
        self.runtime_user = f"conflict_rt_{uuid4().hex[:12]}"
        self.runtime_password = "runtime-test-password-" + uuid4().hex
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_user, rolsuper, rolcreaterole
                FROM pg_roles
                WHERE rolname = current_user
                """
            )
            self.migration_user, is_superuser, can_create_role = cursor.fetchone()
        if not (is_superuser or can_create_role):
            self.skipTest("Migration test role cannot create PostgreSQL roles.")

    def tearDown(self):
        if connection.vendor == "postgresql":
            runtime_ident = sql.Identifier(self.runtime_user)
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP OWNED BY {}").format(runtime_ident)
                )
                cursor.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(runtime_ident)
                )
        super().tearDown()

    def _provision(self):
        stdout = io.StringIO()
        with patch.dict(
            os.environ,
            {
                "POSTGRES_RUNTIME_USER": self.runtime_user,
                "POSTGRES_RUNTIME_PASSWORD": self.runtime_password,
            },
            clear=False,
        ):
            call_command("provision_runtime_db_role", stdout=stdout)
        return json.loads(stdout.getvalue())

    def test_runtime_role_is_distinct_idempotent_and_cannot_mutate_audit_or_migrations(self):
        first = self._provision()
        second = self._provision()
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PASS")
        self.assertEqual(first["migration_role"], self.migration_user)
        self.assertEqual(first["runtime_role"], self.runtime_user)
        self.assertNotEqual(self.runtime_user, self.migration_user)
        for key in (
            "audit_update",
            "audit_delete",
            "audit_truncate",
            "audit_trigger",
            "schema_create",
            "database_owned_by_runtime",
            "database_create",
            "database_temp",
            "audit_owned_by_runtime",
        ):
            self.assertFalse(first[key], key)
        for key in ("role_memberships", "owned_relations", "owned_schemas"):
            self.assertEqual(first[key], 0, key)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rolsuper, rolcreatedb, rolcreaterole, rolinherit,
                       rolreplication, rolbypassrls
                FROM pg_roles
                WHERE rolname = %s
                """,
                [self.runtime_user],
            )
            self.assertEqual(
                cursor.fetchone(),
                (False, False, False, False, False, False),
            )
            for privilege, expected in (
                ("SELECT", True),
                ("INSERT", True),
                ("UPDATE", False),
                ("DELETE", False),
            ):
                cursor.execute(
                    "SELECT has_table_privilege(%s, 'domain_auditevent', %s)",
                    [self.runtime_user, privilege],
                )
                self.assertEqual(bool(cursor.fetchone()[0]), expected)
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                cursor.execute(
                    "SELECT has_table_privilege(%s, 'django_migrations', %s)",
                    [self.runtime_user, privilege],
                )
                self.assertFalse(bool(cursor.fetchone()[0]))
            cursor.execute(
                "SELECT has_schema_privilege(%s, 'public', 'CREATE')",
                [self.runtime_user],
            )
            self.assertFalse(bool(cursor.fetchone()[0]))
            cursor.execute(
                "SELECT has_database_privilege(%s, current_database(), 'CONNECT')",
                [self.runtime_user],
            )
            self.assertTrue(bool(cursor.fetchone()[0]))
            cursor.execute(
                "SELECT pg_get_serial_sequence('django_migrations', 'id')"
            )
            migration_sequence = cursor.fetchone()[0]
            self.assertIsNotNone(migration_sequence)
            cursor.execute(
                "SELECT has_sequence_privilege(%s, %s, 'USAGE')",
                [self.runtime_user, migration_sequence],
            )
            self.assertTrue(bool(cursor.fetchone()[0]))
            cursor.execute(
                "SELECT has_sequence_privilege(%s, %s, 'UPDATE')",
                [self.runtime_user, migration_sequence],
            )
            self.assertFalse(bool(cursor.fetchone()[0]))

        settings = connection.settings_dict
        with psycopg.connect(
            dbname=settings["NAME"],
            user=self.runtime_user,
            password=self.runtime_password,
            host=settings["HOST"],
            port=settings["PORT"],
            autocommit=True,
        ) as runtime:
            with runtime.cursor() as cursor:
                cursor.execute("SELECT current_user, current_setting('search_path')")
                current_user, search_path = cursor.fetchone()
                self.assertEqual(current_user, self.runtime_user)
                self.assertEqual(search_path, "pg_catalog, public")

                probe_key = f"rt-{uuid4().hex}"
                cursor.execute(
                    """
                    INSERT INTO django_session (session_key, session_data, expire_date)
                    VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '1 hour')
                    """,
                    [probe_key, "runtime-role-probe"],
                )
                cursor.execute(
                    "SELECT session_data FROM django_session WHERE session_key = %s",
                    [probe_key],
                )
                self.assertEqual(cursor.fetchone()[0], "runtime-role-probe")
                cursor.execute(
                    "DELETE FROM django_session WHERE session_key = %s",
                    [probe_key],
                )

                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute("CREATE TEMP TABLE runtime_temp_escape(id integer)")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute("CREATE TABLE public.runtime_ddl_escape(id integer)")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        "UPDATE domain_auditevent "
                        "SET actor_identifier = actor_identifier WHERE false"
                    )
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute("TRUNCATE TABLE domain_auditevent")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        "ALTER TABLE domain_auditevent DISABLE TRIGGER USER"
                    )
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        sql.SQL("SET ROLE {}").format(
                            sql.Identifier(self.migration_user)
                        )
                    )
