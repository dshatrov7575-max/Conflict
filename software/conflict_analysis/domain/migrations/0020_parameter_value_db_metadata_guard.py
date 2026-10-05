"""Enforce ParameterValue metadata inheritance at the database boundary.

The model contract permits a present value only when it has either explicit
numeric confidence plus a non-empty rationale, or an exact inherited assessment
header.  The previous cross-row check stopped at a non-null
``actor_element_assessment_id``.  These triggers make direct SQL and any path
that bypasses ``full_clean()`` obey the same bounded rule.
"""

from django.db import migrations


_PRESENT_STATUSES = (
    "PROVISIONAL",
    "CONFIRMED",
    "DISPUTED",
    "RETROSPECTIVE_KNOWLEDGE",
)
_ALLOWED_CATEGORICAL_CONFIDENCE = ("LOW", "MEDIUM", "HIGH", "UNKNOWN")
_PARAMETER_VALUE_TABLE = "domain_parametervalue"
_ASSESSMENT_TABLE = "domain_actorelementassessment"
_DEFINITION_TABLE = "domain_parameterdefinition"
_TRIGGER_FUNCTION = "domain_guard_parameter_value_metadata"
_ASSESSMENT_DEPENDENCY_FUNCTION = "domain_guard_parameter_value_assessment_dependency"
_DEFINITION_DEPENDENCY_FUNCTION = "domain_guard_parameter_value_definition_dependency"
_TRIGGER = "domain_parameter_value_metadata_guard"
_ASSESSMENT_DEPENDENCY_TRIGGER = "domain_parameter_value_assessment_dependency_guard"
_DEFINITION_DEPENDENCY_TRIGGER = "domain_parameter_value_definition_dependency_guard"


def _quoted_csv(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def _sqlite_assessment_context(prefix: str = "NEW") -> str:
    return f"""
        EXISTS (
            SELECT 1
            FROM {_ASSESSMENT_TABLE} AS assessment
            WHERE assessment.id = {prefix}.actor_element_assessment_id
              AND assessment.workspace_id = {prefix}.workspace_id
              AND assessment.time_slice_id = {prefix}.time_slice_id
              AND assessment.assessment_set_id = {prefix}.assessment_set_id
        )
    """


def _sqlite_inherited_metadata(prefix: str = "NEW") -> str:
    categories = _quoted_csv(_ALLOWED_CATEGORICAL_CONFIDENCE)
    return f"""
        EXISTS (
            SELECT 1
            FROM {_ASSESSMENT_TABLE} AS assessment
            JOIN {_DEFINITION_TABLE} AS definition
              ON definition.id = {prefix}.parameter_definition_id
            WHERE assessment.id = {prefix}.actor_element_assessment_id
              AND assessment.workspace_id = {prefix}.workspace_id
              AND assessment.time_slice_id = {prefix}.time_slice_id
              AND assessment.assessment_set_id = {prefix}.assessment_set_id
              AND (
                    (
                        assessment.confidence_level IN ('LOW', 'MEDIUM', 'HIGH')
                        AND TRIM(COALESCE(assessment.reference_statement, '')) <> ''
                    )
                    OR (
                        assessment.confidence_level = 'UNKNOWN'
                        AND TRIM(COALESCE({prefix}.rationale, '')) <> ''
                        AND definition.code IN ('POS', 'SAL')
                        AND json_type(
                            assessment.provenance,
                            '$.parameter_confidence'
                        ) = 'object'
                        AND (
                            SELECT COUNT(*)
                            FROM json_each(
                                json_extract(
                                    assessment.provenance,
                                    '$.parameter_confidence'
                                )
                            )
                        ) = 2
                        AND json_extract(
                            assessment.provenance,
                            '$.parameter_confidence.POS'
                        ) IN ({categories})
                        AND json_extract(
                            assessment.provenance,
                            '$.parameter_confidence.SAL'
                        ) IN ({categories})
                    )
              )
        )
    """


def _sqlite_invalid_existing_rows_sql() -> str:
    statuses = _quoted_csv(_PRESENT_STATUSES)
    return f"""
        SELECT COUNT(*)
        FROM {_PARAMETER_VALUE_TABLE} AS value
        WHERE (
            value.actor_element_assessment_id IS NOT NULL
            AND NOT ({_sqlite_assessment_context('value')})
        ) OR (
            value.status IN ({statuses})
            AND NOT (
                (
                    value.confidence IS NOT NULL
                    AND TRIM(COALESCE(value.rationale, '')) <> ''
                )
                OR ({_sqlite_inherited_metadata('value')})
            )
        )
    """


def _postgres_guard_function_sql() -> str:
    statuses = _quoted_csv(_PRESENT_STATUSES)
    categories = _quoted_csv(_ALLOWED_CATEGORICAL_CONFIDENCE)
    return f"""
        CREATE OR REPLACE FUNCTION {_TRIGGER_FUNCTION}()
        RETURNS trigger AS $$
        DECLARE
            context_matches boolean := false;
            inherited_metadata_complete boolean := false;
        BEGIN
            IF NEW.actor_element_assessment_id IS NOT NULL THEN
                SELECT EXISTS (
                    SELECT 1
                    FROM {_ASSESSMENT_TABLE} AS assessment
                    WHERE assessment.id = NEW.actor_element_assessment_id
                      AND assessment.workspace_id = NEW.workspace_id
                      AND assessment.time_slice_id = NEW.time_slice_id
                      AND assessment.assessment_set_id = NEW.assessment_set_id
                ) INTO context_matches;
                IF NOT context_matches THEN
                    RAISE EXCEPTION
                        'PARAMETER_VALUE_ASSESSMENT_CONTEXT_MISMATCH';
                END IF;
            END IF;

            IF NEW.status IN ({statuses}) THEN
                SELECT EXISTS (
                    SELECT 1
                    FROM {_ASSESSMENT_TABLE} AS assessment
                    JOIN {_DEFINITION_TABLE} AS definition
                      ON definition.id = NEW.parameter_definition_id
                    WHERE assessment.id = NEW.actor_element_assessment_id
                      AND assessment.workspace_id = NEW.workspace_id
                      AND assessment.time_slice_id = NEW.time_slice_id
                      AND assessment.assessment_set_id = NEW.assessment_set_id
                      AND (
                            (
                                assessment.confidence_level IN ('LOW', 'MEDIUM', 'HIGH')
                                AND BTRIM(
                                    COALESCE(assessment.reference_statement, '')
                                ) <> ''
                            )
                            OR (
                                assessment.confidence_level = 'UNKNOWN'
                                AND BTRIM(COALESCE(NEW.rationale, '')) <> ''
                                AND definition.code IN ('POS', 'SAL')
                                AND CASE
                                    WHEN jsonb_typeof(
                                        assessment.provenance -> 'parameter_confidence'
                                    ) = 'object'
                                    THEN
                                        (
                                            SELECT COUNT(*)
                                            FROM jsonb_object_keys(
                                                assessment.provenance -> 'parameter_confidence'
                                            )
                                        ) = 2
                                        AND (
                                            assessment.provenance
                                            -> 'parameter_confidence'
                                            ->> 'POS'
                                        ) IN ({categories})
                                        AND (
                                            assessment.provenance
                                            -> 'parameter_confidence'
                                            ->> 'SAL'
                                        ) IN ({categories})
                                    ELSE false
                                END
                            )
                      )
                ) INTO inherited_metadata_complete;

                IF NOT (
                    (
                        NEW.confidence IS NOT NULL
                        AND BTRIM(COALESCE(NEW.rationale, '')) <> ''
                    )
                    OR inherited_metadata_complete
                ) THEN
                    RAISE EXCEPTION 'PARAMETER_VALUE_METADATA_INCOMPLETE';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """


def _postgres_assessment_dependency_function_sql() -> str:
    statuses = _quoted_csv(_PRESENT_STATUSES)
    categories = _quoted_csv(_ALLOWED_CATEGORICAL_CONFIDENCE)
    return f"""
        CREATE OR REPLACE FUNCTION {_ASSESSMENT_DEPENDENCY_FUNCTION}()
        RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM {_PARAMETER_VALUE_TABLE} AS value
                JOIN {_DEFINITION_TABLE} AS definition
                  ON definition.id = value.parameter_definition_id
                WHERE value.actor_element_assessment_id = OLD.id
                  AND (
                        NEW.id IS DISTINCT FROM OLD.id
                        OR NEW.workspace_id IS DISTINCT FROM value.workspace_id
                        OR NEW.time_slice_id IS DISTINCT FROM value.time_slice_id
                        OR NEW.assessment_set_id IS DISTINCT FROM value.assessment_set_id
                        OR (
                            value.status IN ({statuses})
                            AND NOT (
                                (
                                    value.confidence IS NOT NULL
                                    AND BTRIM(COALESCE(value.rationale, '')) <> ''
                                )
                                OR (
                                    NEW.workspace_id = value.workspace_id
                                    AND NEW.time_slice_id = value.time_slice_id
                                    AND NEW.assessment_set_id = value.assessment_set_id
                                    AND (
                                        (
                                            NEW.confidence_level IN ('LOW', 'MEDIUM', 'HIGH')
                                            AND BTRIM(
                                                COALESCE(NEW.reference_statement, '')
                                            ) <> ''
                                        )
                                        OR (
                                            NEW.confidence_level = 'UNKNOWN'
                                            AND BTRIM(
                                                COALESCE(value.rationale, '')
                                            ) <> ''
                                            AND definition.code IN ('POS', 'SAL')
                                            AND CASE
                                                WHEN jsonb_typeof(
                                                    NEW.provenance
                                                    -> 'parameter_confidence'
                                                ) = 'object'
                                                THEN
                                                    (
                                                        SELECT COUNT(*)
                                                        FROM jsonb_object_keys(
                                                            NEW.provenance
                                                            -> 'parameter_confidence'
                                                        )
                                                    ) = 2
                                                    AND (
                                                        NEW.provenance
                                                        -> 'parameter_confidence'
                                                        ->> 'POS'
                                                    ) IN ({categories})
                                                    AND (
                                                        NEW.provenance
                                                        -> 'parameter_confidence'
                                                        ->> 'SAL'
                                                    ) IN ({categories})
                                                ELSE false
                                            END
                                        )
                                    )
                                )
                            )
                        )
                  )
            ) THEN
                RAISE EXCEPTION
                    'PARAMETER_VALUE_METADATA_DEPENDENCY_INVALIDATION';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """


def _postgres_definition_dependency_function_sql() -> str:
    statuses = _quoted_csv(_PRESENT_STATUSES)
    categories = _quoted_csv(_ALLOWED_CATEGORICAL_CONFIDENCE)
    return f"""
        CREATE OR REPLACE FUNCTION {_DEFINITION_DEPENDENCY_FUNCTION}()
        RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM {_PARAMETER_VALUE_TABLE} AS value
                LEFT JOIN {_ASSESSMENT_TABLE} AS assessment
                  ON assessment.id = value.actor_element_assessment_id
                WHERE value.parameter_definition_id = OLD.id
                  AND (
                        NEW.id IS DISTINCT FROM OLD.id
                        OR (
                            value.status IN ({statuses})
                            AND NOT (
                                (
                                    value.confidence IS NOT NULL
                                    AND BTRIM(COALESCE(value.rationale, '')) <> ''
                                )
                                OR (
                                    assessment.id IS NOT NULL
                                    AND assessment.workspace_id = value.workspace_id
                                    AND assessment.time_slice_id = value.time_slice_id
                                    AND assessment.assessment_set_id = value.assessment_set_id
                                    AND (
                                        (
                                            assessment.confidence_level IN ('LOW', 'MEDIUM', 'HIGH')
                                            AND BTRIM(
                                                COALESCE(
                                                    assessment.reference_statement,
                                                    ''
                                                )
                                            ) <> ''
                                        )
                                        OR (
                                            assessment.confidence_level = 'UNKNOWN'
                                            AND BTRIM(
                                                COALESCE(value.rationale, '')
                                            ) <> ''
                                            AND NEW.code IN ('POS', 'SAL')
                                            AND CASE
                                                WHEN jsonb_typeof(
                                                    assessment.provenance
                                                    -> 'parameter_confidence'
                                                ) = 'object'
                                                THEN
                                                    (
                                                        SELECT COUNT(*)
                                                        FROM jsonb_object_keys(
                                                            assessment.provenance
                                                            -> 'parameter_confidence'
                                                        )
                                                    ) = 2
                                                    AND (
                                                        assessment.provenance
                                                        -> 'parameter_confidence'
                                                        ->> 'POS'
                                                    ) IN ({categories})
                                                    AND (
                                                        assessment.provenance
                                                        -> 'parameter_confidence'
                                                        ->> 'SAL'
                                                    ) IN ({categories})
                                                ELSE false
                                            END
                                        )
                                    )
                                )
                            )
                        )
                  )
            ) THEN
                RAISE EXCEPTION
                    'PARAMETER_VALUE_METADATA_DEPENDENCY_INVALIDATION';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """


def _postgres_invalid_existing_rows_sql() -> str:
    statuses = _quoted_csv(_PRESENT_STATUSES)
    categories = _quoted_csv(_ALLOWED_CATEGORICAL_CONFIDENCE)
    return f"""
        SELECT COUNT(*)
        FROM {_PARAMETER_VALUE_TABLE} AS value
        LEFT JOIN {_ASSESSMENT_TABLE} AS assessment
          ON assessment.id = value.actor_element_assessment_id
        LEFT JOIN {_DEFINITION_TABLE} AS definition
          ON definition.id = value.parameter_definition_id
        WHERE (
            value.actor_element_assessment_id IS NOT NULL
            AND NOT (
                assessment.id IS NOT NULL
                AND assessment.workspace_id = value.workspace_id
                AND assessment.time_slice_id = value.time_slice_id
                AND assessment.assessment_set_id = value.assessment_set_id
            )
        ) OR (
            value.status IN ({statuses})
            AND NOT (
                (
                    value.confidence IS NOT NULL
                    AND BTRIM(COALESCE(value.rationale, '')) <> ''
                )
                OR (
                    assessment.id IS NOT NULL
                    AND assessment.workspace_id = value.workspace_id
                    AND assessment.time_slice_id = value.time_slice_id
                    AND assessment.assessment_set_id = value.assessment_set_id
                    AND (
                        (
                            assessment.confidence_level IN ('LOW', 'MEDIUM', 'HIGH')
                            AND BTRIM(
                                COALESCE(assessment.reference_statement, '')
                            ) <> ''
                        )
                        OR (
                            assessment.confidence_level = 'UNKNOWN'
                            AND BTRIM(COALESCE(value.rationale, '')) <> ''
                            AND definition.code IN ('POS', 'SAL')
                            AND CASE
                                WHEN jsonb_typeof(
                                    assessment.provenance -> 'parameter_confidence'
                                ) = 'object'
                                THEN
                                    (
                                        SELECT COUNT(*)
                                        FROM jsonb_object_keys(
                                            assessment.provenance -> 'parameter_confidence'
                                        )
                                    ) = 2
                                    AND (
                                        assessment.provenance
                                        -> 'parameter_confidence'
                                        ->> 'POS'
                                    ) IN ({categories})
                                    AND (
                                        assessment.provenance
                                        -> 'parameter_confidence'
                                        ->> 'SAL'
                                    ) IN ({categories})
                                ELSE false
                            END
                        )
                    )
                )
            )
        )
    """


def _sqlite_assessment_dependency_trigger_sql(quote_name) -> str:
    statuses = _quoted_csv(_PRESENT_STATUSES)
    categories = _quoted_csv(_ALLOWED_CATEGORICAL_CONFIDENCE)
    return f"""
        CREATE TRIGGER {quote_name(_ASSESSMENT_DEPENDENCY_TRIGGER)}
        BEFORE UPDATE ON {quote_name(_ASSESSMENT_TABLE)}
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1
            FROM {_PARAMETER_VALUE_TABLE} AS value
            JOIN {_DEFINITION_TABLE} AS definition
              ON definition.id = value.parameter_definition_id
            WHERE value.actor_element_assessment_id = OLD.id
              AND (
                    NEW.id <> OLD.id
                    OR NEW.workspace_id <> value.workspace_id
                    OR NEW.time_slice_id <> value.time_slice_id
                    OR NEW.assessment_set_id <> value.assessment_set_id
                    OR (
                        value.status IN ({statuses})
                        AND NOT (
                            (
                                value.confidence IS NOT NULL
                                AND TRIM(COALESCE(value.rationale, '')) <> ''
                            )
                            OR (
                                NEW.workspace_id = value.workspace_id
                                AND NEW.time_slice_id = value.time_slice_id
                                AND NEW.assessment_set_id = value.assessment_set_id
                                AND (
                                    (
                                        NEW.confidence_level IN ('LOW', 'MEDIUM', 'HIGH')
                                        AND TRIM(
                                            COALESCE(NEW.reference_statement, '')
                                        ) <> ''
                                    )
                                    OR (
                                        NEW.confidence_level = 'UNKNOWN'
                                        AND TRIM(
                                            COALESCE(value.rationale, '')
                                        ) <> ''
                                        AND definition.code IN ('POS', 'SAL')
                                        AND json_type(
                                            NEW.provenance,
                                            '$.parameter_confidence'
                                        ) = 'object'
                                        AND (
                                            SELECT COUNT(*)
                                            FROM json_each(
                                                json_extract(
                                                    NEW.provenance,
                                                    '$.parameter_confidence'
                                                )
                                            )
                                        ) = 2
                                        AND json_extract(
                                            NEW.provenance,
                                            '$.parameter_confidence.POS'
                                        ) IN ({categories})
                                        AND json_extract(
                                            NEW.provenance,
                                            '$.parameter_confidence.SAL'
                                        ) IN ({categories})
                                    )
                                )
                            )
                        )
                    )
              )
        )
        BEGIN
            SELECT RAISE(
                ABORT,
                'PARAMETER_VALUE_METADATA_DEPENDENCY_INVALIDATION'
            );
        END
    """


def _sqlite_definition_dependency_trigger_sql(quote_name) -> str:
    statuses = _quoted_csv(_PRESENT_STATUSES)
    categories = _quoted_csv(_ALLOWED_CATEGORICAL_CONFIDENCE)
    return f"""
        CREATE TRIGGER {quote_name(_DEFINITION_DEPENDENCY_TRIGGER)}
        BEFORE UPDATE ON {quote_name(_DEFINITION_TABLE)}
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1
            FROM {_PARAMETER_VALUE_TABLE} AS value
            LEFT JOIN {_ASSESSMENT_TABLE} AS assessment
              ON assessment.id = value.actor_element_assessment_id
            WHERE value.parameter_definition_id = OLD.id
              AND (
                    NEW.id <> OLD.id
                    OR (
                        value.status IN ({statuses})
                        AND NOT (
                            (
                                value.confidence IS NOT NULL
                                AND TRIM(COALESCE(value.rationale, '')) <> ''
                            )
                            OR (
                                assessment.id IS NOT NULL
                                AND assessment.workspace_id = value.workspace_id
                                AND assessment.time_slice_id = value.time_slice_id
                                AND assessment.assessment_set_id = value.assessment_set_id
                                AND (
                                    (
                                        assessment.confidence_level IN ('LOW', 'MEDIUM', 'HIGH')
                                        AND TRIM(
                                            COALESCE(
                                                assessment.reference_statement,
                                                ''
                                            )
                                        ) <> ''
                                    )
                                    OR (
                                        assessment.confidence_level = 'UNKNOWN'
                                        AND TRIM(
                                            COALESCE(value.rationale, '')
                                        ) <> ''
                                        AND NEW.code IN ('POS', 'SAL')
                                        AND json_type(
                                            assessment.provenance,
                                            '$.parameter_confidence'
                                        ) = 'object'
                                        AND (
                                            SELECT COUNT(*)
                                            FROM json_each(
                                                json_extract(
                                                    assessment.provenance,
                                                    '$.parameter_confidence'
                                                )
                                            )
                                        ) = 2
                                        AND json_extract(
                                            assessment.provenance,
                                            '$.parameter_confidence.POS'
                                        ) IN ({categories})
                                        AND json_extract(
                                            assessment.provenance,
                                            '$.parameter_confidence.SAL'
                                        ) IN ({categories})
                                    )
                                )
                            )
                        )
                    )
              )
        )
        BEGIN
            SELECT RAISE(
                ABORT,
                'PARAMETER_VALUE_METADATA_DEPENDENCY_INVALIDATION'
            );
        END
    """


def _install_parameter_value_metadata_guards(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute(_sqlite_invalid_existing_rows_sql())
            if cursor.fetchone()[0]:
                raise RuntimeError(
                    "Existing ParameterValue rows violate the metadata inheritance contract."
                )
            for operation in ("insert", "update"):
                context_trigger = f"{_TRIGGER}_context_{operation}"
                metadata_trigger = f"{_TRIGGER}_metadata_{operation}"
                cursor.execute(f"DROP TRIGGER IF EXISTS {quote(context_trigger)}")
                cursor.execute(f"DROP TRIGGER IF EXISTS {quote(metadata_trigger)}")
                cursor.execute(
                    f"CREATE TRIGGER {quote(context_trigger)} "
                    f"BEFORE {operation.upper()} ON {quote(_PARAMETER_VALUE_TABLE)} "
                    "FOR EACH ROW "
                    "WHEN NEW.actor_element_assessment_id IS NOT NULL "
                    f"AND NOT ({_sqlite_assessment_context()}) "
                    "BEGIN SELECT RAISE(ABORT, "
                    "'PARAMETER_VALUE_ASSESSMENT_CONTEXT_MISMATCH'); END"
                )
                cursor.execute(
                    f"CREATE TRIGGER {quote(metadata_trigger)} "
                    f"BEFORE {operation.upper()} ON {quote(_PARAMETER_VALUE_TABLE)} "
                    "FOR EACH ROW "
                    f"WHEN NEW.status IN ({_quoted_csv(_PRESENT_STATUSES)}) "
                    "AND NOT ("
                    "(NEW.confidence IS NOT NULL "
                    "AND TRIM(COALESCE(NEW.rationale, '')) <> '') "
                    f"OR ({_sqlite_inherited_metadata()})"
                    ") "
                    "BEGIN SELECT RAISE(ABORT, "
                    "'PARAMETER_VALUE_METADATA_INCOMPLETE'); END"
                )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_ASSESSMENT_DEPENDENCY_TRIGGER)}"
            )
            cursor.execute(_sqlite_assessment_dependency_trigger_sql(quote))
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_DEFINITION_DEPENDENCY_TRIGGER)}"
            )
            cursor.execute(_sqlite_definition_dependency_trigger_sql(quote))
            return

        if connection.vendor == "postgresql":
            cursor.execute(_postgres_invalid_existing_rows_sql())
            if cursor.fetchone()[0]:
                raise RuntimeError(
                    "Existing ParameterValue rows violate the metadata inheritance contract."
                )
            cursor.execute(_postgres_guard_function_sql())
            cursor.execute(_postgres_assessment_dependency_function_sql())
            cursor.execute(_postgres_definition_dependency_function_sql())
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_TRIGGER)} "
                f"ON {quote(_PARAMETER_VALUE_TABLE)}"
            )
            cursor.execute(
                f"CREATE TRIGGER {quote(_TRIGGER)} "
                f"BEFORE INSERT OR UPDATE ON {quote(_PARAMETER_VALUE_TABLE)} "
                f"FOR EACH ROW EXECUTE FUNCTION {_TRIGGER_FUNCTION}()"
            )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_ASSESSMENT_DEPENDENCY_TRIGGER)} "
                f"ON {quote(_ASSESSMENT_TABLE)}"
            )
            cursor.execute(
                f"CREATE TRIGGER {quote(_ASSESSMENT_DEPENDENCY_TRIGGER)} "
                f"BEFORE UPDATE ON {quote(_ASSESSMENT_TABLE)} "
                "FOR EACH ROW EXECUTE FUNCTION "
                f"{_ASSESSMENT_DEPENDENCY_FUNCTION}()"
            )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_DEFINITION_DEPENDENCY_TRIGGER)} "
                f"ON {quote(_DEFINITION_TABLE)}"
            )
            cursor.execute(
                f"CREATE TRIGGER {quote(_DEFINITION_DEPENDENCY_TRIGGER)} "
                f"BEFORE UPDATE ON {quote(_DEFINITION_TABLE)} "
                "FOR EACH ROW EXECUTE FUNCTION "
                f"{_DEFINITION_DEPENDENCY_FUNCTION}()"
            )


def _drop_parameter_value_metadata_guards(schema_editor):
    connection = schema_editor.connection
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_ASSESSMENT_DEPENDENCY_TRIGGER)}"
            )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_DEFINITION_DEPENDENCY_TRIGGER)}"
            )
            for operation in ("insert", "update"):
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS "
                    f"{quote(f'{_TRIGGER}_context_{operation}')}"
                )
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS "
                    f"{quote(f'{_TRIGGER}_metadata_{operation}')}"
                )
        elif connection.vendor == "postgresql":
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_ASSESSMENT_DEPENDENCY_TRIGGER)} "
                f"ON {quote(_ASSESSMENT_TABLE)}"
            )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_DEFINITION_DEPENDENCY_TRIGGER)} "
                f"ON {quote(_DEFINITION_TABLE)}"
            )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {quote(_TRIGGER)} "
                f"ON {quote(_PARAMETER_VALUE_TABLE)}"
            )
            cursor.execute(
                f"DROP FUNCTION IF EXISTS {_ASSESSMENT_DEPENDENCY_FUNCTION}()"
            )
            cursor.execute(
                f"DROP FUNCTION IF EXISTS {_DEFINITION_DEPENDENCY_FUNCTION}()"
            )
            cursor.execute(
                f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNCTION}()"
            )


def _reverse_parameter_value_metadata_guards(apps, schema_editor):
    del apps
    _drop_parameter_value_metadata_guards(schema_editor)


class Migration(migrations.Migration):
    dependencies = [("domain", "0019_projection_db_authority_guards")]

    operations = [
        migrations.RunPython(
            _install_parameter_value_metadata_guards,
            _reverse_parameter_value_metadata_guards,
        ),
    ]
