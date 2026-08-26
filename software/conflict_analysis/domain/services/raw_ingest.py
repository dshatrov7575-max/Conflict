"""Strict raw-byte JSON boundary shared by Foundation HTTP and package adapters.

The parser deliberately operates before Django REST Framework (or any other
transport adapter) materializes JSON.  It never repairs input and emits only
bounded, deterministic diagnostics that do not quote request content.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


FOUNDATION_RAW_JSON_MAX_BYTES = 2 * 1024 * 1024
FOUNDATION_RAW_JSON_MAX_NESTING = 128
FOUNDATION_JSON_MEDIA_TYPE = "application/json"
FOUNDATION_JSON_CHARSET = "utf-8"
STRONG_MANIFEST_ETAG_PATTERN = re.compile(r'^"([0-9a-f]{64})"$')


@dataclass(frozen=True, slots=True)
class RawInputIdentity:
    kind: str
    sha256: str
    byte_length: int
    name: str = ""

    def as_dict(self) -> Mapping[str, Any]:
        value: dict[str, Any] = {
            "raw_input_kind": self.kind,
            "raw_input_sha256": self.sha256,
            "raw_input_byte_length": self.byte_length,
        }
        if self.name:
            value["raw_input_name"] = self.name
        return MappingProxyType(value)


@dataclass(frozen=True, slots=True)
class RawJSONDocument:
    value: Mapping[str, Any]
    identity: RawInputIdentity


@dataclass(frozen=True, slots=True)
class CapturedRawJSON:
    payload: bytes
    identity: RawInputIdentity


class RawJSONError(ValueError):
    """One stable, bounded raw-ingest failure."""

    def __init__(self, code: str, message: str, *, path: str = "$") -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")

    def as_dict(self) -> Mapping[str, str]:
        return MappingProxyType(
            {"code": self.code, "path": self.path, "message": self.message}
        )


def _error(code: str, message: str, *, path: str = "$") -> RawJSONError:
    return RawJSONError(code, message, path=path)


def validate_json_content_type(raw_content_type: str | None) -> None:
    """Accept only application/json with no charset or exact UTF-8 charset."""

    if not isinstance(raw_content_type, str) or not raw_content_type.strip():
        raise _error(
            "RAW_JSON_MEDIA_TYPE_REQUIRED",
            "Content-Type must be application/json with optional charset=utf-8.",
        )
    parts = [part.strip() for part in raw_content_type.split(";")]
    if parts[0].lower() != FOUNDATION_JSON_MEDIA_TYPE:
        raise _error(
            "RAW_JSON_MEDIA_TYPE_UNSUPPORTED",
            "Content-Type must be application/json.",
        )
    parameters: dict[str, str] = {}
    for part in parts[1:]:
        if not part or "=" not in part:
            raise _error(
                "RAW_JSON_CHARSET_UNSUPPORTED",
                "Only the optional charset=utf-8 parameter is accepted.",
            )
        name, value = (item.strip() for item in part.split("=", 1))
        name = name.lower()
        normalized_value = value.lower()
        if normalized_value == f'"{FOUNDATION_JSON_CHARSET}"':
            normalized_value = FOUNDATION_JSON_CHARSET
        if (
            name in parameters
            or name != "charset"
            or normalized_value != FOUNDATION_JSON_CHARSET
        ):
            raise _error(
                "RAW_JSON_CHARSET_UNSUPPORTED",
                "Only the optional charset=utf-8 parameter is accepted.",
            )
        parameters[name] = normalized_value


def _reject_constant(_value: str) -> Any:
    raise _error(
        "RAW_JSON_NON_FINITE_NUMBER",
        "NaN and Infinity are not valid Foundation JSON numbers.",
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _error(
                "RAW_JSON_DUPLICATE_KEY",
                "Duplicate object keys are forbidden at every nesting depth.",
            )
        value[key] = item
    return value


def _reject_non_finite_tree(
    value: Any,
    *,
    depth: int = 0,
    active_container_ids: frozenset[int] = frozenset(),
) -> None:
    """Reject exponent overflow and excessive structural nesting."""

    if depth > FOUNDATION_RAW_JSON_MAX_NESTING:
        raise _error(
            "RAW_JSON_NESTING_EXCEEDED",
            f"JSON nesting exceeds the configured {FOUNDATION_RAW_JSON_MAX_NESTING}-level limit.",
        )

    if isinstance(value, float) and not math.isfinite(value):
        raise _error(
            "RAW_JSON_NON_FINITE_NUMBER",
            "NaN and Infinity are not valid Foundation JSON numbers.",
        )
    if isinstance(value, Mapping | list):
        container_id = id(value)
        if container_id in active_container_ids:
            raise _error(
                "RAW_JSON_MAPPING_NOT_SERIALIZABLE",
                "The canonical mapping contains a cyclic non-JSON value.",
            )
        active_container_ids = active_container_ids | {container_id}
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_non_finite_tree(
                item,
                depth=depth + 1,
                active_container_ids=active_container_ids,
            )
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite_tree(
                item,
                depth=depth + 1,
                active_container_ids=active_container_ids,
            )


def parse_raw_json_bytes(
    payload: bytes,
    *,
    kind: str = "BYTES",
    name: str = "",
    content_type: str = FOUNDATION_JSON_MEDIA_TYPE,
    max_bytes: int = FOUNDATION_RAW_JSON_MAX_BYTES,
) -> RawJSONDocument:
    """Parse exactly one UTF-8 JSON object without normalization or repair."""

    validate_json_content_type(content_type)
    if not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer.")
    if len(payload) > max_bytes:
        raise _error(
            "RAW_JSON_BYTE_BUDGET_EXCEEDED",
            f"JSON input exceeds the configured {max_bytes}-byte budget.",
        )
    if payload.startswith(b"\xef\xbb\xbf"):
        raise _error("RAW_JSON_BOM_FORBIDDEN", "A UTF-8 BOM is forbidden.")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _error(
            "RAW_JSON_INVALID_UTF8",
            "JSON input must be strict UTF-8.",
        ) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except RawJSONError:
        raise
    except RecursionError as exc:
        raise _error(
            "RAW_JSON_NESTING_EXCEEDED",
            f"JSON nesting exceeds the configured {FOUNDATION_RAW_JSON_MAX_NESTING}-level limit.",
        ) from exc
    except json.JSONDecodeError as exc:
        code = (
            "RAW_JSON_TRAILING_DOCUMENT"
            if exc.msg == "Extra data"
            else "RAW_JSON_SYNTAX_INVALID"
        )
        message = (
            "Exactly one JSON document is required."
            if code == "RAW_JSON_TRAILING_DOCUMENT"
            else "JSON syntax is invalid."
        )
        raise _error(code, message) from exc
    except ValueError as exc:
        raise _error(
            "RAW_JSON_NUMBER_INVALID",
            "A JSON numeric token exceeds the bounded Foundation representation.",
        ) from exc
    _reject_non_finite_tree(value)
    if not isinstance(value, dict):
        raise _error("RAW_JSON_OBJECT_REQUIRED", "The JSON document root must be an object.")
    identity = RawInputIdentity(
        kind=kind,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_length=len(payload),
        name=name,
    )
    try:
        copied = copy.deepcopy(value)
    except RecursionError as exc:
        raise _error(
            "RAW_JSON_NESTING_EXCEEDED",
            f"JSON nesting exceeds the configured {FOUNDATION_RAW_JSON_MAX_NESTING}-level limit.",
        ) from exc
    return RawJSONDocument(copied, identity)


def _canonical_mapping_bytes(value: Mapping[str, Any]) -> bytes:
    _reject_non_finite_tree(value)
    try:
        return json.dumps(
            copy.deepcopy(dict(value)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except RecursionError as exc:
        raise _error(
            "RAW_JSON_NESTING_EXCEEDED",
            f"JSON nesting exceeds the configured {FOUNDATION_RAW_JSON_MAX_NESTING}-level limit.",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise _error(
            "RAW_JSON_MAPPING_NOT_SERIALIZABLE",
            "The canonical mapping contains a non-JSON value.",
        ) from exc


def capture_json_source(
    source: Any,
    *,
    max_bytes: int = FOUNDATION_RAW_JSON_MAX_BYTES,
) -> CapturedRawJSON:
    """Capture transport bytes and immutable identity without parsing JSON."""

    if not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer.")
    name = ""
    if isinstance(source, Path):
        try:
            digest = hashlib.sha256()
            retained = bytearray()
            byte_length = 0
            with source.open("rb") as stream:
                while chunk := stream.read(64 * 1024):
                    digest.update(chunk)
                    byte_length += len(chunk)
                    remaining = max_bytes + 1 - len(retained)
                    if remaining > 0:
                        retained.extend(chunk[:remaining])
        except OSError as exc:
            raise _error("RAW_JSON_PATH_UNREADABLE", "The JSON path cannot be read.") from exc
        payload = bytes(retained)
        kind = "PATH_BYTES"
        name = source.name
        identity = RawInputIdentity(
            kind=kind,
            sha256=digest.hexdigest(),
            byte_length=byte_length,
            name=name,
        )
    elif isinstance(source, bytes):
        payload = source
        kind = "BYTES"
    elif isinstance(source, str):
        payload = source.encode("utf-8")
        kind = "TEXT"
    elif isinstance(source, Mapping):
        payload = _canonical_mapping_bytes(source)
        kind = "CANONICAL_MAPPING"
    else:
        raise _error(
            "RAW_JSON_INPUT_UNSUPPORTED",
            "JSON input must be bytes, UTF-8 text, Path, or an explicit canonical mapping.",
        )
    if not isinstance(source, Path):
        identity = RawInputIdentity(
            kind=kind,
            sha256=hashlib.sha256(payload).hexdigest(),
            byte_length=len(payload),
            name=name,
        )
    return CapturedRawJSON(payload=payload, identity=identity)


def parse_captured_json(
    captured: CapturedRawJSON,
    *,
    max_bytes: int = FOUNDATION_RAW_JSON_MAX_BYTES,
    content_type: str = FOUNDATION_JSON_MEDIA_TYPE,
) -> RawJSONDocument:
    """Parse an immutable capture without reading its transport a second time."""

    validate_json_content_type(content_type)
    if captured.identity.byte_length > max_bytes:
        raise _error(
            "RAW_JSON_BYTE_BUDGET_EXCEEDED",
            f"JSON input exceeds the configured {max_bytes}-byte budget.",
        )
    document = parse_raw_json_bytes(
        captured.payload,
        kind=captured.identity.kind,
        name=captured.identity.name,
        content_type=content_type,
        max_bytes=max_bytes,
    )
    if document.identity != captured.identity:
        raise RuntimeError("Captured raw JSON identity changed before parsing.")
    return document


def parse_json_source(
    source: Any,
    *,
    max_bytes: int = FOUNDATION_RAW_JSON_MAX_BYTES,
    content_type: str = FOUNDATION_JSON_MEDIA_TYPE,
) -> RawJSONDocument:
    """Route bytes, text, Path, or an explicit canonical mapping to one parser."""

    return parse_captured_json(
        capture_json_source(source, max_bytes=max_bytes),
        content_type=content_type,
        max_bytes=max_bytes,
    )


def read_http_json(request: Any, *, max_bytes: int = FOUNDATION_RAW_JSON_MAX_BYTES) -> RawJSONDocument:
    """Read a Django/DRF request once, before ``request.data`` is accessed."""

    http_request = getattr(request, "_request", request)
    content_type = str(http_request.META.get("CONTENT_TYPE", ""))
    validate_json_content_type(content_type)
    length_header = http_request.META.get("CONTENT_LENGTH")
    if length_header not in (None, ""):
        try:
            advertised_length = int(length_header)
        except (TypeError, ValueError) as exc:
            raise _error(
                "RAW_JSON_CONTENT_LENGTH_INVALID",
                "Content-Length must be a non-negative decimal integer.",
            ) from exc
        if advertised_length < 0:
            raise _error(
                "RAW_JSON_CONTENT_LENGTH_INVALID",
                "Content-Length must be a non-negative decimal integer.",
            )
        if advertised_length > max_bytes:
            raise _error(
                "RAW_JSON_BYTE_BUDGET_EXCEEDED",
                f"JSON input exceeds the configured {max_bytes}-byte budget.",
            )
    if hasattr(http_request, "_body"):
        payload = http_request._body
    else:
        payload = http_request.read(max_bytes + 1)
    return parse_raw_json_bytes(
        payload,
        kind="HTTP_BYTES",
        content_type=content_type,
        max_bytes=max_bytes,
    )


def parse_strong_manifest_if_match(value: str | None) -> str:
    """Accept one exact strong ETag: a quoted lowercase SHA-256 digest."""

    if value is None or value == "":
        raise _error(
            "IF_MATCH_REQUIRED",
            'Draft save requires If-Match: "<lowercase-sha256>".',
        )
    match = STRONG_MANIFEST_ETAG_PATTERN.fullmatch(value)
    if match is None:
        raise _error(
            "IF_MATCH_INVALID",
            "If-Match must contain exactly one strong quoted lowercase SHA-256 validator.",
        )
    return match.group(1)
