"""Fail-closed verification of fixed, presentation-only G7 claim bytes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping

from django.core.exceptions import ImproperlyConfigured


CLAIM_BOUNDARY_CONTRACT_NAME: Final = "player_g7_claim_boundaries_v1.ru.json"
CLAIM_BOUNDARY_CONTRACT_ID: Final = "PLAYER_G7_CLAIM_BOUNDARIES_V1"
CLAIM_BOUNDARY_CONTRACT_VERSION: Final = "1.0.0"
CLAIM_BOUNDARY_CONTRACT_LOCALE: Final = "ru"
CLAIM_BOUNDARY_CONTRACT_SHA256: Final = "4c17b09c8e8ada9ef13278f1d39a569a0df8e7907790f80ce650a4400a215a6c"
CLAIM_BOUNDARY_CONTRACT_BYTES: Final = 4219
CLAIM_BOUNDARY_CONTRACT_PATH: Final = Path(__file__).resolve().parent / "contracts" / CLAIM_BOUNDARY_CONTRACT_NAME
CLAIM_BOUNDARY_SIDECAR_PATH: Final = CLAIM_BOUNDARY_CONTRACT_PATH.with_suffix(".json.sha256")
CLAIM_BOUNDARY_EXPECTED_SIDECAR: Final = f"{CLAIM_BOUNDARY_CONTRACT_SHA256}  {CLAIM_BOUNDARY_CONTRACT_NAME}\n".encode("ascii")


class ClaimBoundaryContractError(ImproperlyConfigured):
    """The immutable G7 contract is absent, malformed, or has drifted."""


@dataclass(frozen=True, slots=True)
class VerifiedClaimBoundaries:
    payload: bytes
    sha256: str
    contract: str
    locale: str
    version: str
    statements: tuple[Mapping[str, str], ...]


def load_claim_boundaries() -> VerifiedClaimBoundaries:
    """Verify bytes, checksum, sidecar and shape before rendering a shell."""

    try:
        payload = CLAIM_BOUNDARY_CONTRACT_PATH.read_bytes()
        sidecar = CLAIM_BOUNDARY_SIDECAR_PATH.read_bytes()
    except OSError as exc:
        raise ClaimBoundaryContractError("PLAYER_CLAIM_BOUNDARY_CONTRACT_UNAVAILABLE") from exc
    if (
        len(payload) != CLAIM_BOUNDARY_CONTRACT_BYTES
        or payload.startswith(b"\xef\xbb\xbf")
        or not payload.endswith(b"\n")
        or hashlib.sha256(payload).hexdigest() != CLAIM_BOUNDARY_CONTRACT_SHA256
        or sidecar != CLAIM_BOUNDARY_EXPECTED_SIDECAR
    ):
        raise ClaimBoundaryContractError("PLAYER_CLAIM_BOUNDARY_CONTRACT_DRIFT")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaimBoundaryContractError("PLAYER_CLAIM_BOUNDARY_CONTRACT_INVALID") from exc
    if (
        not isinstance(decoded, dict)
        or set(decoded) != {"contract", "locale", "statements", "version"}
        or decoded["contract"] != CLAIM_BOUNDARY_CONTRACT_ID
        or decoded["locale"] != CLAIM_BOUNDARY_CONTRACT_LOCALE
        or decoded["version"] != CLAIM_BOUNDARY_CONTRACT_VERSION
        or not isinstance(decoded["statements"], list)
        or len(decoded["statements"]) != 14
    ):
        raise ClaimBoundaryContractError("PLAYER_CLAIM_BOUNDARY_CONTRACT_SHAPE")
    statements = []
    seen = set()
    for item in decoded["statements"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"code", "text"}
            or not all(isinstance(item[key], str) and item[key] for key in ("code", "text"))
            or item["code"] in seen
        ):
            raise ClaimBoundaryContractError("PLAYER_CLAIM_BOUNDARY_STATEMENT_INVALID")
        seen.add(item["code"])
        statements.append(MappingProxyType(dict(item)))
    return VerifiedClaimBoundaries(
        payload, CLAIM_BOUNDARY_CONTRACT_SHA256, decoded["contract"],
        decoded["locale"], decoded["version"], tuple(statements),
    )
