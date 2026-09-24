"""Verification boundary for the fixed, presentation-only C0 claim contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping

from django.core.exceptions import ImproperlyConfigured


CLAIM_BOUNDARY_CONTRACT_NAME: Final = "read_only_claim_boundaries_v1.ru.json"
CLAIM_BOUNDARY_CONTRACT_ID: Final = "STUDIO_READ_ONLY_CLAIM_BOUNDARIES_V1"
CLAIM_BOUNDARY_CONTRACT_VERSION: Final = "1.0.0"
CLAIM_BOUNDARY_CONTRACT_LOCALE: Final = "ru"
CLAIM_BOUNDARY_CONTRACT_BYTES: Final = 2197
CLAIM_BOUNDARY_CONTRACT_SHA256: Final = (
    "da2f5faefeb6d220cfd2c3fa0367b8d1024f1bc3a18f64690c98729f1c980cb2"
)
CLAIM_BOUNDARY_SIDECAR_BYTES: Final = 104
CLAIM_BOUNDARY_CONTRACT_PATH: Final = (
    Path(__file__).resolve().parent / "contracts" / CLAIM_BOUNDARY_CONTRACT_NAME
)
CLAIM_BOUNDARY_SIDECAR_PATH: Final = CLAIM_BOUNDARY_CONTRACT_PATH.with_suffix(
    CLAIM_BOUNDARY_CONTRACT_PATH.suffix + ".sha256"
)
CLAIM_BOUNDARY_EXPECTED_SIDECAR: Final = (
    f"{CLAIM_BOUNDARY_CONTRACT_SHA256}  {CLAIM_BOUNDARY_CONTRACT_NAME}\n".encode(
        "ascii"
    )
)


class ClaimBoundaryContractError(ImproperlyConfigured):
    """The committed claim contract is absent, changed, or malformed."""


@dataclass(frozen=True, slots=True)
class VerifiedClaimBoundaries:
    """Exact verified bytes and their presentation-safe decoded statements."""

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
        raise ClaimBoundaryContractError(
            f"The fixed Studio claim {label} is unavailable."
        ) from exc


def load_claim_boundaries() -> VerifiedClaimBoundaries:
    """Read and verify every byte before any Studio domain surface is rendered."""

    payload = _read_exact(CLAIM_BOUNDARY_CONTRACT_PATH, "contract")
    sidecar = _read_exact(CLAIM_BOUNDARY_SIDECAR_PATH, "sidecar")

    if len(payload) != CLAIM_BOUNDARY_CONTRACT_BYTES:
        raise ClaimBoundaryContractError("The fixed Studio claim byte length drifted.")
    if payload.startswith(b"\xef\xbb\xbf") or not payload.endswith(b"\n"):
        raise ClaimBoundaryContractError(
            "The fixed Studio claim encoding or terminal newline drifted."
        )
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != CLAIM_BOUNDARY_CONTRACT_SHA256:
        raise ClaimBoundaryContractError("The fixed Studio claim checksum drifted.")
    if (
        len(sidecar) != CLAIM_BOUNDARY_SIDECAR_BYTES
        or sidecar != CLAIM_BOUNDARY_EXPECTED_SIDECAR
    ):
        raise ClaimBoundaryContractError("The fixed Studio claim sidecar drifted.")

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaimBoundaryContractError(
            "The fixed Studio claim JSON is malformed."
        ) from exc

    if not isinstance(decoded, dict) or set(decoded) != {
        "contract",
        "locale",
        "statements",
        "version",
    }:
        raise ClaimBoundaryContractError("The fixed Studio claim envelope drifted.")
    if (
        decoded.get("contract") != CLAIM_BOUNDARY_CONTRACT_ID
        or decoded.get("locale") != CLAIM_BOUNDARY_CONTRACT_LOCALE
        or decoded.get("version") != CLAIM_BOUNDARY_CONTRACT_VERSION
    ):
        raise ClaimBoundaryContractError("The fixed Studio claim identity drifted.")

    raw_statements = decoded.get("statements")
    if not isinstance(raw_statements, list) or len(raw_statements) != 9:
        raise ClaimBoundaryContractError("The fixed Studio claim statements drifted.")
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
            raise ClaimBoundaryContractError(
                "The fixed Studio claim statement shape drifted."
            )
        seen_codes.add(statement["code"])
        statements.append(MappingProxyType(dict(statement)))

    return VerifiedClaimBoundaries(
        payload=payload,
        sha256=actual_sha256,
        contract=decoded["contract"],
        locale=decoded["locale"],
        version=decoded["version"],
        statements=tuple(statements),
    )
