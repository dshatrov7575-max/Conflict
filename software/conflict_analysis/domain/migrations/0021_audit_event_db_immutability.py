"""Protect AuditEvent rows from in-place PostgreSQL mutation.

Production uses PostgreSQL.  The existing ORM contract already rejects
AuditEvent update/delete operations, and receipt reads detect drift.  This
migration adds the missing database-side UPDATE/DELETE/TRUNCATE denial.  Role
separation remains a distinct follow-up: a table owner/superuser can still
alter or remove database triggers and therefore is outside this guard's trust
boundary.
"""

from django.db import migrations


_TRIGGER = "domain_audit_event_immutable_guard"
_TRUNCATE_TRIGGER = "domain_audit_event_truncate_guard"
_FUNCTION = "domain_guard_audit_event_immutable"
_TABLE = "domain_auditevent"


def _install_guard(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION}()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'AUDIT_EVENT_IMMUTABLE';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        cursor.execute(
            f"DROP TRIGGER IF EXISTS {quote(_TRIGGER)} ON {quote(_TABLE)}"
        )
        cursor.execute(
            f"CREATE TRIGGER {quote(_TRIGGER)} "
            f"BEFORE UPDATE OR DELETE ON {quote(_TABLE)} "
            f"FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}()"
        )
        cursor.execute(
            f"DROP TRIGGER IF EXISTS {quote(_TRUNCATE_TRIGGER)} ON {quote(_TABLE)}"
        )
        cursor.execute(
            f"CREATE TRIGGER {quote(_TRUNCATE_TRIGGER)} "
            f"BEFORE TRUNCATE ON {quote(_TABLE)} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCTION}()"
        )


def _drop_guard(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            f"DROP TRIGGER IF EXISTS {quote(_TRUNCATE_TRIGGER)} ON {quote(_TABLE)}"
        )
        cursor.execute(
            f"DROP TRIGGER IF EXISTS {quote(_TRIGGER)} ON {quote(_TABLE)}"
        )
        cursor.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")


class Migration(migrations.Migration):
    dependencies = [("domain", "0020_parameter_value_db_metadata_guard")]

    operations = [
        migrations.RunPython(_install_guard, _drop_guard),
    ]
