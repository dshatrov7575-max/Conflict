#!/usr/bin/env python3
"""Verify deterministic Natural Earth R1 output using only stdlib."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable


REQUIRED = (
    "central_asia_admin0.geojson",
    "central_asia_disputed_lines.geojson",
    "kazakhstan_admin1.geojson",
    "central_asia_places.geojson",
    "labels_ru.json",
    "map_style.json",
    "NATURAL_EARTH_TERMS.txt",
    "DATASET_LICENSES_RU.md",
    "BOUNDARY_POLICY_RU.md",
    "MAP_DATASET_MANIFEST.json",
    "MAP_DATASET_MANIFEST.json.sha256",
)

APPROVED = frozenset({"AZE", "CHN", "IRN", "KAZ", "KGZ", "MNG", "RUS", "TKM", "UZB"})
EXPECTED_COMMIT = "f1890d9f152c896d250a77557a5751a93d494776"


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8-sig"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            RuntimeError(f"non-finite JSON token: {value}")
        ),
    )


def coords(value: Any) -> Iterable[tuple[float, float]]:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and not isinstance(value[0], bool)
        and isinstance(value[1], (int, float))
        and not isinstance(value[1], bool)
    ):
        yield float(value[0]), float(value[1])
    elif isinstance(value, list):
        for item in value:
            yield from coords(item)


def validate_fc(path: Path, geometry_types: frozenset[str]) -> dict[str, Any]:
    value = load(path)
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
        fail(f"{path.name}: not a FeatureCollection")
    features = value.get("features")
    if not isinstance(features, list):
        fail(f"{path.name}: features is not a list")
    identities: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            fail(f"{path.name}: invalid feature")
        identity = str(feature.get("id") or "")
        if not identity or identity in identities:
            fail(f"{path.name}: absent/duplicate feature id {identity!r}")
        identities.add(identity)
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in geometry_types:
            fail(f"{path.name}: invalid geometry type")
        points = list(coords(geometry.get("coordinates")))
        if not points:
            fail(f"{path.name}: empty geometry")
        for longitude, latitude in points:
            if not math.isfinite(longitude) or not math.isfinite(latitude):
                fail(f"{path.name}: non-finite coordinate")
            if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                fail(f"{path.name}: coordinate outside CRS84")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    root = args.output_dir.resolve()

    for name in REQUIRED:
        if not (root / name).is_file():
            fail(f"required output absent: {name}")

    admin0 = validate_fc(root / "central_asia_admin0.geojson", frozenset({"Polygon", "MultiPolygon"}))
    disputed = validate_fc(root / "central_asia_disputed_lines.geojson", frozenset({"LineString", "MultiLineString"}))
    admin1 = validate_fc(root / "kazakhstan_admin1.geojson", frozenset({"Polygon", "MultiPolygon"}))
    places = validate_fc(root / "central_asia_places.geojson", frozenset({"Point"}))

    codes = {str(row["properties"].get("adm0_a3")) for row in admin0["features"]}
    if codes != APPROVED:
        fail(f"admin0 country set mismatch: {sorted(codes)}")
    if any(row["properties"].get("adm0_a3") != "KAZ" for row in admin1["features"]):
        fail("admin1 contains a non-Kazakhstan feature")
    if any(row["properties"].get("adm0_a3") not in APPROVED for row in places["features"]):
        fail("places contains a non-approved country")

    labels = load(root / "labels_ru.json")
    if labels.get("schema") != "CONFLICT_MAP_LABELS_RU_V1":
        fail("labels schema mismatch")
    country_labels = {
        row["feature_id"]: row["name_ru"]
        for row in labels.get("labels", [])
        if row.get("dataset") == "admin0"
    }
    for code in APPROVED:
        if not country_labels.get(code):
            fail(f"Russian country label absent: {code}")

    style = load(root / "map_style.json")
    style_text = json.dumps(style, ensure_ascii=False)
    if re.search(r"https?://|tile\.openstreetmap|yandex|cdn\.|\.pmtiles", style_text, re.I):
        fail("map style contains a forbidden remote/PMTiles reference")

    manifest_path = root / "MAP_DATASET_MANIFEST.json"
    manifest = load(manifest_path)
    if manifest.get("source_commit") != EXPECTED_COMMIT:
        fail("Natural Earth source commit mismatch")
    for flag in ("geoboundaries_used", "osm_derived_data_used", "odbl_data_used", "pmtiles_used"):
        if manifest.get(flag) is not False:
            fail(f"manifest flag must be false: {flag}")
    digest = manifest.get("manifest_sha256")
    without = dict(manifest)
    without.pop("manifest_sha256", None)
    if digest != hashlib.sha256(canonical(without)).hexdigest():
        fail("manifest canonical SHA-256 mismatch")

    recorded = (root / "MAP_DATASET_MANIFEST.json.sha256").read_text(
        encoding="ascii"
    ).split()[0]
    if recorded != sha(manifest_path):
        fail("manifest exact-file SHA-256 mismatch")

    rows = {row["path"]: row for row in manifest.get("files", [])}
    for name in REQUIRED:
        if name in {"MAP_DATASET_MANIFEST.json", "MAP_DATASET_MANIFEST.json.sha256"}:
            continue
        row = rows.get(name)
        if row is None:
            fail(f"manifest row absent: {name}")
        path = root / name
        if row.get("bytes") != path.stat().st_size:
            fail(f"manifest bytes mismatch: {name}")
        if row.get("sha256") != sha(path):
            fail(f"manifest SHA mismatch: {name}")

    combined_text = "\n".join(
        (root / name).read_text(encoding="utf-8-sig", errors="replace")
        for name in (
            "DATASET_LICENSES_RU.md",
            "BOUNDARY_POLICY_RU.md",
            "MAP_DATASET_MANIFEST.json",
        )
    )
    if "geoBoundaries" in combined_text and "не используются" not in combined_text:
        fail("geoBoundaries appears as a used runtime source")
    if "ODbL" in combined_text and "не используются" not in combined_text:
        fail("ODbL appears as a used runtime license")

    result = {
        "schema": "CONFLICT_MVP7_R1_MAP_OUTPUT_VERIFY_V1",
        "status": "PASS",
        "source_commit": EXPECTED_COMMIT,
        "counts": {
            "admin0": len(admin0["features"]),
            "disputed": len(disputed["features"]),
            "admin1": len(admin1["features"]),
            "places": len(places["features"]),
        },
        "manifest_sha256": digest,
        "manifest_file_sha256": sha(manifest_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(
            {
                "schema": "CONFLICT_MVP7_R1_MAP_OUTPUT_VERIFY_V1",
                "status": "FAIL",
                "error": str(exc),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ))
        raise SystemExit(1)
