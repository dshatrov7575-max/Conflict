#!/usr/bin/env python3
"""Build deterministic offline geography assets for Conflict MVP7/R1.

Source is pinned to one immutable Natural Earth commit.  The builder:
- downloads only raw.githubusercontent.com paths listed in the source lock;
- records raw SHA-256 and exact source URLs;
- filters Central Asia/Kazakhstan deterministically;
- preserves stable Natural Earth identifiers;
- emits canonical GeoJSON and a canonical dataset manifest;
- downloads the exact Natural Earth public-domain license snapshot;
- performs an optional two-build reproducibility test.

No geoBoundaries, OpenStreetMap-derived data, PMTiles, CDN, Yandex or public
runtime tile service is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import ssl
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable


PACK_ROOT = Path(__file__).resolve().parent
SOURCE_LOCK_PATH = PACK_ROOT / "NATURAL_EARTH_SOURCE_LOCK.json"
LABEL_OVERRIDES_PATH = PACK_ROOT / "LABEL_OVERRIDES_RU.json"

DATASET_CODE = "CA_CENTRAL_ASIA_POLITICAL_V1"
DATASET_VERSION = "1.0.1"
BOUNDARY_POLICY_VERSION = "CA_BOUNDARY_POLICY_V1"
BUILDER_VERSION = "1.0.1"
STATIC_MAP_BASE = "/static/analysis_dashboard/maps"

REQUIRED_OUTPUTS = (
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


class BuildError(RuntimeError):
    pass


def duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuildError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=duplicate_rejecting_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                BuildError(f"non-finite JSON number: {token}")
            ),
        )
    except BuildError:
        raise
    except Exception as exc:
        raise BuildError(f"cannot read JSON {path}: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_finite(value: Any, where: str = "$") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BuildError(f"non-finite number at {where}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            ensure_finite(item, f"{where}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            ensure_finite(item, f"{where}.{key}")
        return
    raise BuildError(f"unsupported JSON value at {where}: {type(value)!r}")


def pget(properties: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in properties and properties[name] not in (None, ""):
            return properties[name]
    folded = {str(key).casefold(): value for key, value in properties.items()}
    for name in names:
        value = folded.get(name.casefold())
        if value not in (None, ""):
            return value
    return None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def clean_code(value: Any) -> str | None:
    result = clean_text(value)
    if result is None:
        return None
    return result.upper()


def normalized_name(value: Any) -> str:
    text = clean_text(value) or ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).strip().casefold()
    return text


def geometry_coordinates(value: Any) -> Iterable[tuple[float, float]]:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and not isinstance(value[0], bool)
        and isinstance(value[1], (int, float))
        and not isinstance(value[1], bool)
    ):
        yield float(value[0]), float(value[1])
        return
    if isinstance(value, list):
        for item in value:
            yield from geometry_coordinates(item)


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    coordinates = list(geometry_coordinates(geometry.get("coordinates")))
    if not coordinates:
        raise BuildError("geometry contains no coordinates")
    for longitude, latitude in coordinates:
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise BuildError("geometry contains non-finite coordinates")
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise BuildError("geometry coordinate is outside CRS84 bounds")
    longitudes = [item[0] for item in coordinates]
    latitudes = [item[1] for item in coordinates]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def intersects(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] < right[0]
        or left[0] > right[2]
        or left[3] < right[1]
        or left[1] > right[3]
    )


def feature_collection(path: Path) -> list[dict[str, Any]]:
    value = load_json(path)
    ensure_finite(value)
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
        raise BuildError(f"{path.name} is not a FeatureCollection")
    crs = value.get("crs")
    if crs is not None and crs != {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}:
        raise BuildError(f"{path.name}: expected CRS84 geographic coordinates")
    features = value.get("features")
    if not isinstance(features, list):
        raise BuildError(f"{path.name}.features is not a list")
    result: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise BuildError(f"{path.name}: invalid feature #{index}")
        if not isinstance(feature.get("properties"), dict):
            raise BuildError(f"{path.name}: feature #{index} has no properties")
        if not isinstance(feature.get("geometry"), dict):
            raise BuildError(f"{path.name}: feature #{index} has no geometry")
        geometry_bbox(feature["geometry"])
        result.append(feature)
    return result


def stable_id(properties: dict[str, Any], candidates: tuple[str, ...], context: str) -> str:
    value = pget(properties, *candidates)
    result = clean_text(value)
    if result is None:
        raise BuildError(f"{context}: stable identifier is absent")
    return result


def name_fields(
    properties: dict[str, Any],
    *,
    override: str | None = None,
) -> tuple[str, str | None, str | None]:
    name = clean_text(
        pget(properties, "NAME", "name", "NAME_EN", "name_en", "GN_NAME", "gn_name")
    )
    name_en = clean_text(pget(properties, "NAME_EN", "name_en", "NAME", "name"))
    name_ru = clean_text(pget(properties, "NAME_RU", "name_ru"))
    if not name_ru and override:
        name_ru = override
    if name is None:
        name = name_en or name_ru
    if name is None:
        raise BuildError("feature name is absent")
    return name, name_ru, name_en


def label_coordinates(properties: dict[str, Any], geometry: dict[str, Any]) -> tuple[float, float] | None:
    longitude = pget(
        properties,
        "LABEL_X",
        "label_x",
        "LONGITUDE",
        "longitude",
        "LON",
        "lon",
    )
    latitude = pget(
        properties,
        "LABEL_Y",
        "label_y",
        "LATITUDE",
        "latitude",
        "LAT",
        "lat",
    )
    try:
        if longitude is not None and latitude is not None:
            x, y = float(longitude), float(latitude)
            if math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90:
                return x, y
    except (TypeError, ValueError):
        pass
    if geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates")
        if (
            isinstance(coordinates, list)
            and len(coordinates) >= 2
            and all(isinstance(item, (int, float)) for item in coordinates[:2])
        ):
            return float(coordinates[0]), float(coordinates[1])
    return None


def output_feature(
    feature_id: str,
    geometry: dict[str, Any],
    properties: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": feature_id,
        "properties": properties,
        "geometry": geometry,
    }


def build_admin0(
    features: list[dict[str, Any]],
    approved: frozenset[str],
    overrides: dict[str, str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for feature in features:
        source = feature["properties"]
        code = clean_code(pget(source, "ADM0_A3", "adm0_a3", "ISO_A3", "iso_a3"))
        if code not in approved:
            continue
        if code in seen:
            raise BuildError(f"admin0 duplicate country code: {code}")
        seen.add(code)
        name, name_ru, name_en = name_fields(source, override=overrides.get(code))
        label = label_coordinates(source, feature["geometry"])
        properties = {
            "feature_id": code,
            "adm0_a3": code,
            "name": name,
            "name_ru": name_ru,
            "source_name_ru": clean_text(pget(source, "NAME_RU", "name_ru")),
            "name_en": name_en,
            "sovereignt": clean_text(pget(source, "SOVEREIGNT", "sovereignt")),
            "type": clean_text(pget(source, "TYPE", "type")),
            "ne_id": clean_text(pget(source, "NE_ID", "ne_id")),
            "label_lon": label[0] if label else None,
            "label_lat": label[1] if label else None,
            "min_zoom": pget(source, "MIN_ZOOM", "min_zoom"),
        }
        rows.append(output_feature(code, feature["geometry"], properties))
    missing = sorted(approved - seen)
    if missing:
        raise BuildError(f"admin0 approved countries are absent: {', '.join(missing)}")
    return {
        "type": "FeatureCollection",
        "name": "central_asia_admin0",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": sorted(rows, key=lambda row: str(row["id"])),
    }


def build_admin1(features: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for feature in features:
        source = feature["properties"]
        country = clean_code(
            pget(source, "ADM0_A3", "adm0_a3", "SOV_A3", "sov_a3", "ISO_A3", "iso_a3")
        )
        if country != "KAZ":
            continue
        identity = stable_id(
            source,
            (
                "NE_ID",
                "ne_id",
                "ADM1_CODE",
                "adm1_code",
                "CODE_HASC",
                "code_hasc",
                "gn_id",
                "GN_ID",
            ),
            "Kazakhstan ADM1",
        )
        if identity in seen:
            raise BuildError(f"admin1 duplicate identifier: {identity}")
        seen.add(identity)
        name, name_ru, name_en = name_fields(source)
        label = label_coordinates(source, feature["geometry"])
        properties = {
            "feature_id": identity,
            "adm0_a3": "KAZ",
            "iso_3166_2": clean_text(pget(source, "ISO_3166_2", "iso_3166_2")),
            "adm1_code": clean_text(pget(source, "ADM1_CODE", "adm1_code")),
            "name": name,
            "name_ru": name_ru,
            "source_name_ru": clean_text(pget(source, "NAME_RU", "name_ru")),
            "name_en": name_en,
            "type": clean_text(pget(source, "TYPE", "type", "TYPE_EN", "type_en")),
            "type_ru": clean_text(pget(source, "TYPE_RU", "type_ru")),
            "postal": clean_text(pget(source, "POSTAL", "postal")),
            "region": clean_text(pget(source, "REGION", "region")),
            "region_code": clean_text(pget(source, "REGION_COD", "region_cod")),
            "ne_id": clean_text(pget(source, "NE_ID", "ne_id")),
            "label_lon": label[0] if label else None,
            "label_lat": label[1] if label else None,
        }
        rows.append(output_feature(identity, feature["geometry"], properties))
    if not rows:
        raise BuildError("Natural Earth contains no Kazakhstan ADM1 features")
    return {
        "type": "FeatureCollection",
        "name": "kazakhstan_admin1",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": sorted(rows, key=lambda row: str(row["id"])),
    }


def build_disputed(
    features: list[dict[str, Any]],
    extent: tuple[float, float, float, float],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for feature in features:
        if not intersects(geometry_bbox(feature["geometry"]), extent):
            continue
        source = feature["properties"]
        identity = stable_id(source, ("NE_ID", "ne_id", "BRK_A3", "brk_a3"), "disputed line")
        if identity in seen:
            raise BuildError(f"disputed duplicate identifier: {identity}")
        seen.add(identity)
        properties = {
            "feature_id": identity,
            "feature_class": clean_text(pget(source, "FEATURECLA", "featurecla")),
            "name": clean_text(pget(source, "NAME", "name")),
            "note": clean_text(pget(source, "NOTE", "note", "COMMENT", "comment")),
            "adm0_a3_left": clean_code(pget(source, "ADM0_A3_L", "adm0_a3_l")),
            "adm0_a3_right": clean_code(pget(source, "ADM0_A3_R", "adm0_a3_r")),
            "fclass_ru": clean_text(pget(source, "FCLASS_RU", "fclass_ru")),
            "ne_id": clean_text(pget(source, "NE_ID", "ne_id")),
        }
        properties.update({str(key).upper(): value for key, value in source.items()
                           if str(key).upper().startswith("FCLASS_")})
        rows.append(output_feature(identity, feature["geometry"], properties))
    return {
        "type": "FeatureCollection",
        "name": "central_asia_disputed_lines",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": sorted(rows, key=lambda row: str(row["id"])),
    }


def build_places(
    features: list[dict[str, Any]],
    approved: frozenset[str],
    extent: tuple[float, float, float, float],
    place_overrides: dict[str, str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for feature in features:
        if feature["geometry"].get("type") != "Point":
            continue
        point_bbox = geometry_bbox(feature["geometry"])
        if not intersects(point_bbox, extent):
            continue
        source = feature["properties"]
        country = clean_code(
            pget(source, "ADM0_A3", "adm0_a3", "SOV_A3", "sov_a3", "ISO_A3", "iso_a3")
        )
        if country not in approved:
            continue
        rank_value = pget(source, "SCALERANK", "scalerank")
        try:
            rank = int(rank_value)
        except (TypeError, ValueError):
            rank = 99
        raw_name = clean_text(pget(source, "NAME_EN", "name_en", "NAME", "name")) or ""
        normalized = normalized_name(raw_name)
        override = place_overrides.get(normalized)
        is_important = bool(
            pget(source, "CAPIN", "capin", "WORLDCITY", "worldcity", "MEGACITY", "megacity")
        )
        if rank > 7 and not override and not is_important:
            continue
        identity = stable_id(source, ("NE_ID", "ne_id", "WIKIDATAID", "wikidataid"), "place")
        if identity in seen:
            raise BuildError(f"place duplicate identifier: {identity}")
        seen.add(identity)
        name, name_ru, name_en = name_fields(source, override=override)
        coordinates = feature["geometry"]["coordinates"]
        properties = {
            "feature_id": identity,
            "adm0_a3": country,
            "name": name,
            "name_ru": name_ru,
            "source_name_ru": clean_text(pget(source, "NAME_RU", "name_ru")),
            "name_en": name_en,
            "scalerank": rank,
            "capital": clean_text(pget(source, "CAPIN", "capin")),
            "worldcity": pget(source, "WORLDCITY", "worldcity"),
            "megacity": pget(source, "MEGACITY", "megacity"),
            "ne_id": clean_text(pget(source, "NE_ID", "ne_id")),
            "longitude": float(coordinates[0]),
            "latitude": float(coordinates[1]),
        }
        rows.append(output_feature(identity, feature["geometry"], properties))
    if not rows:
        raise BuildError("places output is empty")
    return {
        "type": "FeatureCollection",
        "name": "central_asia_places",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": sorted(rows, key=lambda row: str(row["id"])),
    }


def build_labels(
    admin0: dict[str, Any],
    admin1: dict[str, Any],
    places: dict[str, Any],
    project_labels: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for dataset, collection in (
        ("admin0", admin0),
        ("admin1", admin1),
        ("places", places),
    ):
        for feature in collection["features"]:
            properties = feature["properties"]
            name_ru = clean_text(properties.get("name_ru"))
            if not name_ru:
                continue
            row = {
                "dataset": dataset,
                "feature_id": str(feature["id"]),
                "name_ru": name_ru,
                "label_lon": properties.get("label_lon", properties.get("longitude")),
                "label_lat": properties.get("label_lat", properties.get("latitude")),
            }
            rows.append(row)
    rows.sort(key=lambda row: (row["dataset"], row["feature_id"]))
    return {
        "schema": "CONFLICT_MAP_LABELS_RU_V1",
        "version": "1.0.0",
        "labels": rows,
        "project_labels": project_labels,
    }


def build_style() -> dict[str, Any]:
    return {
        "version": 8,
        "name": "Conflict Central Asia Political R1",
        "metadata": {
            "dataset_code": DATASET_CODE,
            "dataset_version": DATASET_VERSION,
            "boundary_policy_version": BOUNDARY_POLICY_VERSION,
            "labels": "HTML/DOM overlay from labels_ru.json; no remote glyph service",
        },
        "sources": {
            "admin0": {
                "type": "geojson",
                "data": f"{STATIC_MAP_BASE}/central_asia_admin0.geojson",
            },
            "disputed": {
                "type": "geojson",
                "data": f"{STATIC_MAP_BASE}/central_asia_disputed_lines.geojson",
            },
            "admin1": {
                "type": "geojson",
                "data": f"{STATIC_MAP_BASE}/kazakhstan_admin1.geojson",
            },
            "places": {
                "type": "geojson",
                "data": f"{STATIC_MAP_BASE}/central_asia_places.geojson",
            },
        },
        "layers": [
            {"id": "background", "type": "background", "paint": {"background-color": "#dceaf5"}},
            {
                "id": "countries-fill",
                "type": "fill",
                "source": "admin0",
                "paint": {"fill-color": "#f3efe4", "fill-opacity": 1},
            },
            {
                "id": "countries-boundary",
                "type": "line",
                "source": "admin0",
                "paint": {"line-color": "#45586a", "line-width": 1.25},
            },
            {
                "id": "kazakhstan-admin1-fill",
                "type": "fill",
                "source": "admin1",
                "paint": {"fill-color": "#c9ddef", "fill-opacity": 0.18},
            },
            {
                "id": "kazakhstan-admin1-boundary",
                "type": "line",
                "source": "admin1",
                "paint": {"line-color": "#7695ad", "line-width": 0.8},
            },
            {
                "id": "disputed-lines",
                "type": "line",
                "source": "disputed",
                "paint": {
                    "line-color": "#ad6b16",
                    "line-width": 1.4,
                    "line-dasharray": [3, 2],
                },
            },
            {
                "id": "places-circle",
                "type": "circle",
                "source": "places",
                "paint": {
                    "circle-radius": 2.5,
                    "circle-color": "#245888",
                    "circle-stroke-color": "#ffffff",
                    "circle-stroke-width": 0.8,
                },
            },
        ],
    }


def boundary_policy() -> str:
    return f"""# Политика отображения государственных и спорных границ

**Версия:** `{BOUNDARY_POLICY_VERSION}`

**Набор:** `{DATASET_CODE}` / `{DATASET_VERSION}`

1. Государственные и административные линии берутся из exact Natural Earth source pin.
2. Обычная государственная граница отображается сплошной линией.
3. Спорная, претензионная или reference line отображается пунктиром.
4. Спорные линии не преобразуются в обычные границы и не скрываются.
5. Картографический слой отражает выбранную версию набора данных и не является
   юридическим заключением о статусе спорных территорий.
6. Любая замена source commit, фильтра или стиля требует новой dataset version.
7. Русские подписи не изменяют геометрию и хранятся отдельным versioned слоем.
"""


def dataset_licenses(source_lock: dict[str, Any]) -> str:
    return f"""# Источники и лицензии картографических данных

## Natural Earth

- Repository: `{source_lock["repository"]}`
- Tag: `{source_lock["tag"]}`
- Commit: `{source_lock["commit"]}`
- Commit date: `{source_lock["commit_date"]}`
- License: Public Domain
- Runtime attribution (recommended): `Картографическая основа: Natural Earth.`

В runtime R1 не используются geoBoundaries, OpenStreetMap-derived data,
PMTiles, Яндекс-Карты, CDN или публичные tile endpoints.

Raw и derived SHA-256 находятся в `MAP_DATASET_MANIFEST.json`.
"""


def source_url(source_lock: dict[str, Any], relative_path: str) -> str:
    commit = source_lock["commit"]
    return (
        "https://raw.githubusercontent.com/"
        f"{source_lock['repository']}/{commit}/{relative_path}"
    )


def download(url: str, destination: Path) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com":
        raise BuildError(f"download host is not allowed: {url}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Conflict-MVP7-R1-MapBuilder/1.0"},
    )
    context = ssl.create_default_context()
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=90, context=context) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise BuildError(f"unexpected redirect: {response.geturl()}")
        if getattr(response, "status", 200) != 200:
            raise BuildError(f"download failed with HTTP {response.status}: {url}")
        with temporary.open("wb") as stream:
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 200 * 1024 * 1024:
                    raise BuildError(f"source is unexpectedly large: {url}")
                stream.write(chunk)
    temporary.replace(destination)


def ensure_raw_sources(
    source_lock: dict[str, Any],
    raw_dir: Path,
    *,
    offline: bool,
) -> list[dict[str, Any]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for source in source_lock["sources"]:
        relative = source["path"]
        filename = Path(relative).name
        destination = raw_dir / filename
        url = source_url(source_lock, relative)
        if not destination.exists():
            if offline:
                raise BuildError(f"offline raw source is absent: {destination}")
            download(url, destination)
        rows.append(
            {
                "key": source["key"],
                "path": relative,
                "filename": filename,
                "url": url,
                "theme_version": source["theme_version"],
                "bytes": destination.stat().st_size,
                "sha256": sha256_file(destination),
                "license": source_lock["license"],
            }
        )
    return rows


def write_output(path: Path, value: Any, *, pretty: bool = False) -> None:
    data = pretty_bytes(value) if pretty else canonical_bytes(value)
    path.write_bytes(data)


def assemble(
    *,
    source_lock: dict[str, Any],
    overrides: dict[str, Any],
    raw_dir: Path,
    output_dir: Path,
    offline: bool,
) -> dict[str, str]:
    raw_rows = ensure_raw_sources(source_lock, raw_dir, offline=offline)
    by_key = {row["key"]: row for row in raw_rows}
    raw_paths = {row["key"]: raw_dir / row["filename"] for row in raw_rows}

    approved = frozenset(source_lock["approved_iso_a3"])
    extent = tuple(float(item) for item in source_lock["extent"])
    country_overrides = dict(overrides["countries_by_iso_a3"])
    place_overrides = {
        normalized_name(key): value
        for key, value in overrides["places_by_normalized_name"].items()
    }

    admin0 = build_admin0(feature_collection(raw_paths["admin0"]), approved, country_overrides)
    disputed = build_disputed(feature_collection(raw_paths["disputed"]), extent)
    admin1 = build_admin1(feature_collection(raw_paths["admin1"]))
    places = build_places(
        feature_collection(raw_paths["places"]),
        approved,
        extent,
        place_overrides,
    )
    labels = build_labels(admin0, admin1, places, list(overrides["project_labels"]))
    style = build_style()

    output_dir.mkdir(parents=True, exist_ok=True)
    write_output(output_dir / "central_asia_admin0.geojson", admin0)
    write_output(output_dir / "central_asia_disputed_lines.geojson", disputed)
    write_output(output_dir / "kazakhstan_admin1.geojson", admin1)
    write_output(output_dir / "central_asia_places.geojson", places)
    write_output(output_dir / "labels_ru.json", labels, pretty=True)
    write_output(output_dir / "map_style.json", style, pretty=True)
    shutil.copyfile(raw_paths["license"], output_dir / "NATURAL_EARTH_TERMS.txt")
    (output_dir / "DATASET_LICENSES_RU.md").write_bytes(dataset_licenses(source_lock).encode("utf-8"))
    (output_dir / "BOUNDARY_POLICY_RU.md").write_bytes(boundary_policy().encode("utf-8"))

    transformations = {
        "central_asia_admin0.geojson": [
            "filter approved ISO-A3 set",
            "retain stable Natural Earth IDs",
            "retain NAME_RU and label coordinates",
            "canonical JSON serialization",
        ],
        "central_asia_disputed_lines.geojson": [
            "filter by approved Central Asia extent",
            "retain dispute classification and Natural Earth IDs",
            "canonical JSON serialization",
        ],
        "kazakhstan_admin1.geojson": [
            "filter Kazakhstan ADM0_A3=KAZ",
            "retain stable ADM1/Natural Earth IDs",
            "retain NAME_RU and label coordinates",
            "canonical JSON serialization",
        ],
        "central_asia_places.geojson": [
            "filter approved Central Asia extent and countries",
            "retain scalerank<=7 or important/override places",
            "retain Natural Earth IDs and NAME_RU",
            "canonical JSON serialization",
        ],
        "labels_ru.json": [
            "prefer Natural Earth NAME_RU",
            "apply versioned project overrides",
            "do not change geometry",
        ],
        "map_style.json": [
            "same-origin GeoJSON sources only",
            "no glyphs, sprites, tiles, CDN or external URL",
            "labels rendered by local DOM overlay",
        ],
    }
    source_by_output = {
        source["output"]: by_key[source["key"]]
        for source in source_lock["sources"]
        if source["key"] != "license"
    }

    manifest_files: list[dict[str, Any]] = []
    for filename in (
        "central_asia_admin0.geojson",
        "central_asia_disputed_lines.geojson",
        "kazakhstan_admin1.geojson",
        "central_asia_places.geojson",
        "labels_ru.json",
        "map_style.json",
        "NATURAL_EARTH_TERMS.txt",
        "DATASET_LICENSES_RU.md",
        "BOUNDARY_POLICY_RU.md",
    ):
        path = output_dir / filename
        source = source_by_output.get(filename)
        row: dict[str, Any] = {
            "path": filename,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "license": "Public Domain" if source or filename == "NATURAL_EARTH_TERMS.txt" else "Project asset",
            "transformations": transformations.get(filename, ["copied or generated deterministically"]),
        }
        if source:
            row.update(
                {
                    "source": "Natural Earth",
                    "source_repository": source_lock["repository"],
                    "source_commit": source_lock["commit"],
                    "source_path": source["path"],
                    "source_url": source["url"],
                    "source_theme_version": source["theme_version"],
                    "raw_source_bytes": source["bytes"],
                    "raw_source_sha256": source["sha256"],
                }
            )
        else:
            row["source"] = "Natural Earth exact license snapshot" if filename == "NATURAL_EARTH_TERMS.txt" else "Conflict project deterministic asset"
        manifest_files.append(row)

    manifest: dict[str, Any] = {
        "schema": "CONFLICT_MAP_DATASET_MANIFEST_V1",
        "dataset_code": DATASET_CODE,
        "dataset_version": DATASET_VERSION,
        "boundary_policy_version": BOUNDARY_POLICY_VERSION,
        "builder_version": BUILDER_VERSION,
        "generated_at": source_lock["commit_date"],
        "source_repository": source_lock["repository"],
        "source_tag": source_lock["tag"],
        "source_commit": source_lock["commit"],
        "source_tree": source_lock["tree"],
        "source_commit_date": source_lock["commit_date"],
        "approved_iso_a3": sorted(approved),
        "extent": list(extent),
        "geoboundaries_used": False,
        "osm_derived_data_used": False,
        "odbl_data_used": False,
        "pmtiles_used": False,
        "runtime_network": "OFFLINE_ONLY",
        "files": sorted(manifest_files, key=lambda row: row["path"]),
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_bytes(manifest))
    manifest_path = output_dir / "MAP_DATASET_MANIFEST.json"
    manifest_path.write_bytes(pretty_bytes(manifest))
    (output_dir / "MAP_DATASET_MANIFEST.json.sha256").write_bytes(
        f"{sha256_file(manifest_path)}  MAP_DATASET_MANIFEST.json\n".encode("ascii")
    )

    missing = [name for name in REQUIRED_OUTPUTS if not (output_dir / name).is_file()]
    if missing:
        raise BuildError(f"required outputs are absent: {missing}")
    return {name: sha256_file(output_dir / name) for name in REQUIRED_OUTPUTS}


def synthetic_raw(raw_dir: Path, source_lock: dict[str, Any]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    admin0 = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "ADM0_A3": code,
                    "NAME": code,
                    "NAME_EN": code,
                    "NAME_RU": None,
                    "NE_ID": index,
                    "LABEL_X": 60 + index,
                    "LABEL_Y": 45,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[50 + index, 40], [51 + index, 40], [51 + index, 41], [50 + index, 40]]],
                },
            }
            for index, code in enumerate(source_lock["approved_iso_a3"])
        ],
    }
    disputed = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"NE_ID": 1, "FEATURECLA": "Claim boundary", "NAME": "Test"},
                "geometry": {"type": "LineString", "coordinates": [[47, 40], [48, 41]]},
            },
            {
                "type": "Feature",
                "properties": {"NE_ID": 2, "FEATURECLA": "Outside", "NAME": "Outside"},
                "geometry": {"type": "LineString", "coordinates": [[-100, -40], [-90, -30]]},
            },
        ],
    }
    admin1 = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "ADM0_A3": "KAZ",
                    "iso_3166_2": "KZ-47",
                    "NAME": "Mangystau",
                    "NAME_RU": "Мангистауская область",
                    "NE_ID": 47,
                    "LABEL_X": 52,
                    "LABEL_Y": 44,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[50, 42], [55, 42], [55, 46], [50, 42]]],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "ADM0_A3": "USA",
                    "iso_3166_2": "US-X",
                    "NAME": "Outside",
                    "NE_ID": 99,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-100, 40], [-99, 40], [-99, 41], [-100, 40]]],
                },
            },
        ],
    }
    places = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "ADM0_A3": "KAZ",
                    "NAME": "Astana",
                    "NAME_EN": "Astana",
                    "NAME_RU": "Астана",
                    "NE_ID": 100,
                    "SCALERANK": 3,
                    "CAPIN": "World",
                },
                "geometry": {"type": "Point", "coordinates": [71.43, 51.13]},
            },
            {
                "type": "Feature",
                "properties": {
                    "ADM0_A3": "USA",
                    "NAME": "Outside",
                    "NE_ID": 101,
                    "SCALERANK": 1,
                },
                "geometry": {"type": "Point", "coordinates": [-74, 40]},
            },
        ],
    }
    payloads = {
        "ne_10m_admin_0_countries.geojson": admin0,
        "ne_10m_admin_0_boundary_lines_disputed_areas.geojson": disputed,
        "ne_10m_admin_1_states_provinces.geojson": admin1,
        "ne_10m_populated_places.geojson": places,
    }
    for filename, payload in payloads.items():
        (raw_dir / filename).write_bytes(canonical_bytes(payload))
    (raw_dir / "LICENSE.md").write_bytes(b"# Everything here is public domain.\n")


def self_test(source_lock: dict[str, Any], overrides: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory(prefix="conflict-map-builder-selftest-") as temp:
        root = Path(temp)
        raw = root / "raw"
        synthetic_raw(raw, source_lock)
        first, second = root / "first", root / "second"
        hashes_first = assemble(
            source_lock=source_lock,
            overrides=overrides,
            raw_dir=raw,
            output_dir=first,
            offline=True,
        )
        hashes_second = assemble(
            source_lock=source_lock,
            overrides=overrides,
            raw_dir=raw,
            output_dir=second,
            offline=True,
        )
        if hashes_first != hashes_second:
            raise BuildError("self-test reproducibility failed")
        manifest = load_json(first / "MAP_DATASET_MANIFEST.json")
        if manifest.get("geoboundaries_used") is not False:
            raise BuildError("self-test geoboundaries flag failed")
        if manifest.get("odbl_data_used") is not False:
            raise BuildError("self-test ODbL flag failed")
        print(json.dumps(
            {
                "schema": "CONFLICT_MVP7_R1_MAP_BUILDER_SELFTEST_V1",
                "status": "PASS",
                "output_hashes": hashes_first,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--raw-cache", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verify-reproducible", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    source_lock = load_json(SOURCE_LOCK_PATH)
    overrides = load_json(LABEL_OVERRIDES_PATH)

    if args.self_test:
        self_test(source_lock, overrides)
        return 0
    if args.output_dir is None:
        parser.error("--output-dir is required unless --self-test is used")

    output = args.output_dir.resolve()
    raw_cache = (
        args.raw_cache.resolve()
        if args.raw_cache
        else output.parent / ".natural-earth-v5.1.2-raw"
    )
    if output.exists() and any(output.iterdir()) and not args.force:
        raise BuildError(f"output directory is not empty: {output}")

    with tempfile.TemporaryDirectory(
        prefix="conflict-map-build-",
        dir=str(output.parent),
    ) as temp:
        staging = Path(temp) / "output"
        hashes = assemble(
            source_lock=source_lock,
            overrides=overrides,
            raw_dir=raw_cache,
            output_dir=staging,
            offline=args.offline,
        )
        if args.verify_reproducible:
            second = Path(temp) / "second"
            hashes_second = assemble(
                source_lock=source_lock,
                overrides=overrides,
                raw_dir=raw_cache,
                output_dir=second,
                offline=True,
            )
            if hashes != hashes_second:
                raise BuildError("second deterministic build produced different hashes")
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(staging, output)

    print(json.dumps(
        {
            "schema": "CONFLICT_MVP7_R1_MAP_BUILD_RESULT_V1",
            "status": "PASS",
            "output_dir": str(output),
            "source_commit": source_lock["commit"],
            "hashes": hashes,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(json.dumps(
            {
                "schema": "CONFLICT_MVP7_R1_MAP_BUILD_RESULT_V1",
                "status": "FAIL",
                "error": str(exc),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ))
        raise SystemExit(1)
