"""Fail-closed verification of immutable, presentation-only G8 claim bytes."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping

from django.core.exceptions import ImproperlyConfigured


CONTRACT_NAME: Final = "player_g8_claim_boundaries_v1.ru.json"
CONTRACT_ID: Final = "PLAYER_G8_CLAIM_BOUNDARIES_V1"
CONTRACT_VERSION: Final = "1.0.0"
CONTRACT_LOCALE: Final = "ru"
CONTRACT_SHA256: Final = "62a0737d590a266af8351a0d1d22a391a29d3f98033dfecff833d620069aadbc"
CONTRACT_BYTES: Final = 2858
CONTRACT_PATH: Final = Path(__file__).resolve().parent / "contracts" / CONTRACT_NAME
SIDECAR_PATH: Final = CONTRACT_PATH.with_suffix(".json.sha256")


class ExperimentClaimBoundaryError(ImproperlyConfigured):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedExperimentClaims:
    sha256: str
    contract: str
    locale: str
    version: str
    statements: tuple[Mapping[str, str], ...]


def load_experiment_claim_boundaries() -> VerifiedExperimentClaims:
    try:
        raw = CONTRACT_PATH.read_bytes()
        sidecar = SIDECAR_PATH.read_bytes()
    except OSError as exc:
        raise ExperimentClaimBoundaryError("PLAYER_G8_CLAIM_CONTRACT_UNAVAILABLE") from exc
    expected = f"{CONTRACT_SHA256}  {CONTRACT_NAME}\n".encode("ascii")
    if (
        len(raw) != CONTRACT_BYTES or raw.startswith(b"\xef\xbb\xbf")
        or not raw.endswith(b"\n") or hashlib.sha256(raw).hexdigest() != CONTRACT_SHA256
        or sidecar != expected
    ):
        raise ExperimentClaimBoundaryError("PLAYER_G8_CLAIM_CONTRACT_DRIFT")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ExperimentClaimBoundaryError("PLAYER_G8_CLAIM_CONTRACT_INVALID") from exc
    if (
        type(payload) is not dict
        or set(payload) != {"contract", "locale", "statements", "version"}
        or payload["contract"] != CONTRACT_ID or payload["locale"] != CONTRACT_LOCALE
        or payload["version"] != CONTRACT_VERSION or type(payload["statements"]) is not list
        or len(payload["statements"]) != 14
    ):
        raise ExperimentClaimBoundaryError("PLAYER_G8_CLAIM_CONTRACT_SHAPE")
    statements, seen = [], set()
    for item in payload["statements"]:
        if (
            type(item) is not dict or set(item) != {"code", "text"}
            or not all(type(item[key]) is str and item[key] for key in ("code", "text"))
            or item["code"] in seen
        ):
            raise ExperimentClaimBoundaryError("PLAYER_G8_CLAIM_STATEMENT_INVALID")
        seen.add(item["code"])
        statements.append(MappingProxyType(dict(item)))
    return VerifiedExperimentClaims(
        CONTRACT_SHA256, CONTRACT_ID, CONTRACT_LOCALE, CONTRACT_VERSION, tuple(statements),
    )
