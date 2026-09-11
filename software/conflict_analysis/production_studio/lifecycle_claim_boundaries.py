"""Verification boundary for the fixed C2A lifecycle-publication claims."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping

from django.core.exceptions import ImproperlyConfigured


LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_NAME: Final = (
    "lifecycle_publication_claim_boundaries_v1.ru.json"
)
LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_ID: Final = (
    "STUDIO_LIFECYCLE_PUBLICATION_CLAIM_BOUNDARIES_V1"
)
LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_VERSION: Final = "1.0.0"
LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_LOCALE: Final = "ru"
LIFECYCLE_CLAIM_BOUNDARY_STATEMENT_COUNT: Final = 15
# Exact values are pinned to the committed UTF-8 payload below.
LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_BYTES: Final = 4942
LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_SHA256: Final = (
    "4afb64e3ca27218c5ca0f29b4eaad209894f8623d96956085b450deded67996d"
)
LIFECYCLE_CLAIM_BOUNDARY_SIDECAR_BYTES: Final = 116
LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_PATH: Final = (
    Path(__file__).resolve().parent
    / "contracts"
    / LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_NAME
)
LIFECYCLE_CLAIM_BOUNDARY_SIDECAR_PATH: Final = (
    LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_PATH.with_suffix(
        LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_PATH.suffix + ".sha256"
    )
)
LIFECYCLE_CLAIM_BOUNDARY_EXPECTED_SIDECAR: Final = (
    f"{LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_SHA256}  "
    f"{LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_NAME}\n"
).encode("ascii")


class LifecycleClaimBoundaryContractError(ImproperlyConfigured):
    """The committed C2A claim contract is absent, changed, or malformed."""


@dataclass(frozen=True, slots=True)
class VerifiedLifecycleClaimBoundaries:
    """Exact verified bytes and presentation-safe lifecycle statements."""

    payload: bytes
    sha256: str
    contract: str
    locale: str
    version: str
    statements: tuple[Mapping[str, str], ...]


def _read_exact(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise LifecycleClaimBoundaryContractError(
            f"The fixed Studio lifecycle claim {label} is unavailable."
        ) from exc


def load_lifecycle_claim_boundaries() -> VerifiedLifecycleClaimBoundaries:
    """Read and verify every byte before a C2A shell is rendered."""

    payload = _read_exact(LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_PATH, "contract")
    sidecar = _read_exact(LIFECYCLE_CLAIM_BOUNDARY_SIDECAR_PATH, "sidecar")

    if len(payload) != LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_BYTES:
        raise LifecycleClaimBoundaryContractError(
            "The fixed Studio lifecycle claim byte length drifted."
        )
    if payload.startswith(b"\xef\xbb\xbf") or not payload.endswith(b"\n"):
        raise LifecycleClaimBoundaryContractError(
            "The fixed Studio lifecycle claim encoding or terminal newline drifted."
        )
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_SHA256:
        raise LifecycleClaimBoundaryContractError(
            "The fixed Studio lifecycle claim checksum drifted."
        )
    if (
        len(sidecar) != LIFECYCLE_CLAIM_BOUNDARY_SIDECAR_BYTES
        or sidecar != LIFECYCLE_CLAIM_BOUNDARY_EXPECTED_SIDECAR
    ):
        raise LifecycleClaimBoundaryContractError(
            "The fixed Studio lifecycle claim sidecar drifted."
        )

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecycleClaimBoundaryContractError(
            "The fixed Studio lifecycle claim JSON is malformed."
        ) from exc

    if not isinstance(decoded, dict) or set(decoded) != {
        "contract",
        "locale",
        "statements",
        "version",
    }:
        raise LifecycleClaimBoundaryContractError(
            "The fixed Studio lifecycle claim envelope drifted."
        )
    if (
        decoded.get("contract") != LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_ID
        or decoded.get("locale") != LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_LOCALE
        or decoded.get("version") != LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_VERSION
    ):
        raise LifecycleClaimBoundaryContractError(
            "The fixed Studio lifecycle claim identity drifted."
        )

    raw_statements = decoded.get("statements")
    if (
        not isinstance(raw_statements, list)
        or len(raw_statements) != LIFECYCLE_CLAIM_BOUNDARY_STATEMENT_COUNT
    ):
        raise LifecycleClaimBoundaryContractError(
            "The fixed Studio lifecycle claim statements drifted."
        )
    statements: list[Mapping[str, str]] = []
    seen_codes: set[str] = set()
    for statement in raw_statements:
        if (
            not isinstance(statement, dict)
            or set(statement) != {"code", "text"}
            or not isinstance(statement.get("code"), str)
            or not isinstance(statement.get("text"), str)
            or not statement["code"]
            or not statement["text"]
            or statement["code"] in seen_codes
        ):
            raise LifecycleClaimBoundaryContractError(
                "The fixed Studio lifecycle claim statement shape drifted."
            )
        seen_codes.add(statement["code"])
        statements.append(MappingProxyType(dict(statement)))

    return VerifiedLifecycleClaimBoundaries(
        payload=payload,
        sha256=actual_sha256,
        contract=decoded["contract"],
        locale=decoded["locale"],
        version=decoded["version"],
        statements=tuple(statements),
    )
