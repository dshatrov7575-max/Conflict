"""Verification boundary for the fixed C1 audited-authoring claim contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping

from django.core.exceptions import ImproperlyConfigured


AUTHORING_CLAIM_BOUNDARY_CONTRACT_NAME: Final = (
    "audited_draft_claim_boundaries_v1.ru.json"
)
AUTHORING_CLAIM_BOUNDARY_CONTRACT_ID: Final = (
    "STUDIO_AUDITED_DRAFT_CLAIM_BOUNDARIES_V1"
)
AUTHORING_CLAIM_BOUNDARY_CONTRACT_VERSION: Final = "1.0.0"
AUTHORING_CLAIM_BOUNDARY_CONTRACT_LOCALE: Final = "ru"
AUTHORING_CLAIM_BOUNDARY_STATEMENT_COUNT: Final = 11
# Exact values are deliberately pinned after the committed UTF-8 payload is built.
AUTHORING_CLAIM_BOUNDARY_CONTRACT_BYTES: Final = 2873
AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256: Final = (
    "bc7ae9264bcfe22d0169785a3db1fee175387245edfc66b8de36b17f9cdb0bcf"
)
AUTHORING_CLAIM_BOUNDARY_SIDECAR_BYTES: Final = 108
AUTHORING_CLAIM_BOUNDARY_CONTRACT_PATH: Final = (
    Path(__file__).resolve().parent
    / "contracts"
    / AUTHORING_CLAIM_BOUNDARY_CONTRACT_NAME
)
AUTHORING_CLAIM_BOUNDARY_SIDECAR_PATH: Final = (
    AUTHORING_CLAIM_BOUNDARY_CONTRACT_PATH.with_suffix(
        AUTHORING_CLAIM_BOUNDARY_CONTRACT_PATH.suffix + ".sha256"
    )
)
AUTHORING_CLAIM_BOUNDARY_EXPECTED_SIDECAR: Final = (
    f"{AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256}  "
    f"{AUTHORING_CLAIM_BOUNDARY_CONTRACT_NAME}\n"
).encode("ascii")


class AuthoringClaimBoundaryContractError(ImproperlyConfigured):
    """The committed authoring claim contract is absent, changed, or malformed."""


@dataclass(frozen=True, slots=True)
class VerifiedAuthoringClaimBoundaries:
    """Exact verified bytes and presentation-safe decoded authoring statements."""

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
        raise AuthoringClaimBoundaryContractError(
            f"The fixed Studio authoring claim {label} is unavailable."
        ) from exc


def load_authoring_claim_boundaries() -> VerifiedAuthoringClaimBoundaries:
    """Read and verify every byte before an audited-authoring shell is rendered."""

    payload = _read_exact(AUTHORING_CLAIM_BOUNDARY_CONTRACT_PATH, "contract")
    sidecar = _read_exact(AUTHORING_CLAIM_BOUNDARY_SIDECAR_PATH, "sidecar")

    if len(payload) != AUTHORING_CLAIM_BOUNDARY_CONTRACT_BYTES:
        raise AuthoringClaimBoundaryContractError(
            "The fixed Studio authoring claim byte length drifted."
        )
    if payload.startswith(b"\xef\xbb\xbf") or not payload.endswith(b"\n"):
        raise AuthoringClaimBoundaryContractError(
            "The fixed Studio authoring claim encoding or terminal newline drifted."
        )
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256:
        raise AuthoringClaimBoundaryContractError(
            "The fixed Studio authoring claim checksum drifted."
        )
    if (
        len(sidecar) != AUTHORING_CLAIM_BOUNDARY_SIDECAR_BYTES
        or sidecar != AUTHORING_CLAIM_BOUNDARY_EXPECTED_SIDECAR
    ):
        raise AuthoringClaimBoundaryContractError(
            "The fixed Studio authoring claim sidecar drifted."
        )

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthoringClaimBoundaryContractError(
            "The fixed Studio authoring claim JSON is malformed."
        ) from exc

    if not isinstance(decoded, dict) or set(decoded) != {
        "contract",
        "locale",
        "statements",
        "version",
    }:
        raise AuthoringClaimBoundaryContractError(
            "The fixed Studio authoring claim envelope drifted."
        )
    if (
        decoded.get("contract") != AUTHORING_CLAIM_BOUNDARY_CONTRACT_ID
        or decoded.get("locale") != AUTHORING_CLAIM_BOUNDARY_CONTRACT_LOCALE
        or decoded.get("version") != AUTHORING_CLAIM_BOUNDARY_CONTRACT_VERSION
    ):
        raise AuthoringClaimBoundaryContractError(
            "The fixed Studio authoring claim identity drifted."
        )

    raw_statements = decoded.get("statements")
    if (
        not isinstance(raw_statements, list)
        or len(raw_statements) != AUTHORING_CLAIM_BOUNDARY_STATEMENT_COUNT
    ):
        raise AuthoringClaimBoundaryContractError(
            "The fixed Studio authoring claim statements drifted."
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
            raise AuthoringClaimBoundaryContractError(
                "The fixed Studio authoring claim statement shape drifted."
            )
        seen_codes.add(statement["code"])
        statements.append(MappingProxyType(dict(statement)))

    return VerifiedAuthoringClaimBoundaries(
        payload=payload,
        sha256=actual_sha256,
        contract=decoded["contract"],
        locale=decoded["locale"],
        version=decoded["version"],
        statements=tuple(statements),
    )
