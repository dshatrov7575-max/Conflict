"""Shared deterministic oracles for Production Studio C0 tests."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from django.db import connection


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "domain"
    / "tests"
    / "fixtures"
    / "foundation_studio_definition_vectors_v1.json"
)


def foundation_manifest() -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(fixture["vectors"][0]["manifest"])


def database_fingerprint() -> dict[str, str]:
    """Hash every server table without relying on model-level serialization."""

    fingerprints: dict[str, str] = {}
    with connection.cursor() as cursor:
        tables = sorted(connection.introspection.table_names(cursor))
        for table in tables:
            description = connection.introspection.get_table_description(cursor, table)
            columns = [field.name for field in description]
            quoted_columns = ", ".join(
                connection.ops.quote_name(column) for column in columns
            )
            cursor.execute(
                f"SELECT {quoted_columns} FROM {connection.ops.quote_name(table)}"
            )
            rows = sorted(repr(tuple(row)) for row in cursor.fetchall())
            payload = json.dumps(
                {"columns": columns, "rows": rows},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            fingerprints[table] = hashlib.sha256(payload).hexdigest()
    return fingerprints
