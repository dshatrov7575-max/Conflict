"""Canonical bounded contracts for method-safe Analysis V1 reads."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any


VERSION = "1.0.0"
CONTEXT_CONTRACT = "FOUNDATION_ANALYSIS_CONTEXT_V1"
TIMELINE_CONTRACT = "FOUNDATION_ANALYSIS_TIMELINE_V1"
MATRIX_CONTRACT = "FOUNDATION_ANALYSIS_MATRIX_V1"
COMPARISON_CONTRACT = "FOUNDATION_ANALYSIS_COMPARISON_V1"
ALLOWED_PARAMETER_CODES = frozenset({"POS", "SAL"})
ABSENT_STATUSES = frozenset({
    "UNKNOWN", "INSUFFICIENT_DATA", "NOT_APPLICABLE", "OPEN_METHOD",
})
PRESENT_STATUSES = frozenset({
    "PROVISIONAL", "CONFIRMED", "DISPUTED", "RETROSPECTIVE_KNOWLEDGE",
})
METHOD_STATE = {
    "project_total_score": "METHOD_NOT_APPROVED",
    "regional_aggregate": "METHOD_NOT_APPROVED",
}

ERROR_MESSAGES = {
    "ANALYSIS_AUTHENTICATION_REQUIRED": "Требуется действующая сессия пользователя.",
    "ANALYSIS_NOT_FOUND": "Объект недоступен или не найден.",
    "ANALYSIS_REQUEST_INVALID": "Запрос не соответствует точному контракту Analysis V1.",
    "ANALYSIS_METHOD_NOT_APPROVED": "Расчётная методика не утверждена.",
    "ANALYSIS_PROJECTION_NOT_PROVEN": "Проекция рабочего пространства не подтверждена.",
    "ANALYSIS_INTEGRITY_CONFLICT": "Целостность аналитического read-model не подтверждена.",
    "ANALYSIS_OPERATION_FAILED": "Операция чтения не завершена.",
}


class AnalysisError(RuntimeError):
    def __init__(self, code: str, status: int = 409) -> None:
        if code not in ERROR_MESSAGES:
            code, status = "ANALYSIS_OPERATION_FAILED", 503
        self.code = code
        self.status = status
        super().__init__(ERROR_MESSAGES[code])


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def snapshot(contract: str, **payload: object) -> dict[str, object]:
    core = {"contract": contract, "contract_version": VERSION, **payload}
    return {**core, "response_sha256": sha256(core)}


def decimal_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT") from exc
    if not decimal.is_finite():
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    text = format(decimal.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def json_number(value: object) -> int | float:
    text = decimal_text(value)
    if text is None:
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    decimal = Decimal(text)
    if decimal == decimal.to_integral_value():
        return int(decimal)
    return float(decimal)


def require_parameter_code(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
    code = value.strip().upper()
    if code not in ALLOWED_PARAMETER_CODES:
        raise AnalysisError("ANALYSIS_METHOD_NOT_APPROVED")
    return code
