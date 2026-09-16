"""Build pinned Natural Earth assets; preserve the Foundation manifest contract.

Raw data remain outside the repository. The supplied output verifier runs
against a flattened view of the actual runtime files and builder receipt.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import BUILD_NATURAL_EARTH_R1 as builder

HERE = Path(__file__).resolve().parent
RECEIPT = "NATURAL_EARTH_BUILD_MANIFEST.json"
LICENSES = ("NATURAL_EARTH_TERMS.txt", "DATASET_LICENSES_RU.md", "BOUNDARY_POLICY_RU.md")
COMMIT = "f1890d9f152c896d250a77557a5751a93d494776"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_sources(raw, offline):
    lock = builder.load_json(HERE / "RAW_SOURCES_LOCK.json")
    assert lock["source_commit"] == COMMIT and len(lock["sources"]) == 5
    raw.mkdir(parents=True, exist_ok=True)
    for row in lock["sources"]:
        target = raw / Path(row["path"]).name
        url = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{COMMIT}/{row['path']}"
        assert row["url"] == url and row["license"] == "Public Domain"
        if not target.is_file():
            if offline:
                raise builder.BuildError(f"Offline source absent: {target.name}")
            builder.download(url, target)
        if target.stat().st_size != row["bytes"] or sha(target) != row["sha256"]:
            raise builder.BuildError(f"Pinned raw SHA-256 mismatch: {target.name}")
    return lock["sources"]


def verify_output(static):
    """Verify the exact installed data bytes with the supplied verifier."""
    maps = static / "maps"
    with tempfile.TemporaryDirectory(prefix="natural-earth-output-verify-") as temp:
        flattened = Path(temp)
        receipt = builder.load_json(maps / RECEIPT)
        for row in receipt["files"]:
            name = row["path"]
            assert Path(name).name == name
            source = static / "licenses" / name if name in LICENSES else maps / name
            shutil.copyfile(source, flattened / name)
        target = flattened / "MAP_DATASET_MANIFEST.json"
        shutil.copyfile(maps / RECEIPT, target)
        (flattened / "MAP_DATASET_MANIFEST.json.sha256").write_bytes(f"{sha(target)}  MAP_DATASET_MANIFEST.json\n".encode("ascii"))
        subprocess.run([sys.executable, "-B", str(HERE / "VERIFY_NATURAL_EARTH_R1_OUTPUT.py"), str(flattened)], check=True)


def verify_source_lineage(raw, output, lock):
    """Every emitted geometry and source Russian label must match the raw pin."""
    for entry in lock["sources"]:
        if entry["key"] == "license":
            continue
        incoming = builder.feature_collection(raw / Path(entry["path"]).name)
        index = {}
        for feature in incoming:
            props = feature["properties"]
            identity = builder.pget(props, "ADM0_A3") if entry["key"] == "admin0" else builder.pget(props, "NE_ID")
            if identity is not None:
                index[str(identity)] = feature
        emitted = builder.load_json(output / entry["output"])["features"]
        for feature in emitted:
            source = index[feature["id"]]
            assert feature["geometry"] == source["geometry"], feature["id"]
            expected_ru = builder.clean_text(builder.pget(source["properties"], "NAME_RU"))
            if expected_ru:
                assert feature["properties"].get("name_ru") == expected_ru, feature["id"]
        if entry["key"] == "places":
            required = {"zhangaozen", "aqtau", "atyrau", "nur sultan", "almaty"}
            names = {builder.normalized_name(f["properties"]["name"]) for f in emitted}
            assert required <= names, required - names


def build(static, raw, offline):
    rows = raw_sources(raw, offline)
    lock = builder.load_json(HERE / "NATURAL_EARTH_SOURCE_LOCK.json")
    overrides = builder.load_json(HERE / "LABEL_OVERRIDES_RU.json")
    assert lock["commit"] == COMMIT and lock["tag"] == "v5.1.2"
    maps, licenses = static / "maps", static / "licenses"
    maps.mkdir(parents=True, exist_ok=True)
    licenses.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="natural-earth-derived-") as temp:
        output = Path(temp)
        builder.assemble(source_lock=lock, overrides=overrides, raw_dir=raw, output_dir=output, offline=True)
        verify_source_lineage(raw, output, lock)
        for name in builder.REQUIRED_OUTPUTS:
            if not name.startswith("MAP_DATASET_MANIFEST"):
                shutil.copyfile(output / name, (licenses if name in LICENSES else maps) / name)
        shutil.copyfile(output / "MAP_DATASET_MANIFEST.json", maps / RECEIPT)
    for script in sorted(HERE.iterdir()):
        if script.suffix == ".py" or script.name in ("RAW_SOURCES_LOCK.json", "NATURAL_EARTH_SOURCE_LOCK.json", "LABEL_OVERRIDES_RU.json", "BUILDER_PATCHES_RU.md"):
            if script.resolve() != (maps / script.name).resolve():
                shutil.copyfile(script, maps / script.name)
    # The unchanged MapLibre renderer is not a geographic data source.
    source_vendor = HERE.parent / "vendor/maplibre"
    target_vendor = static / "vendor/maplibre"
    target_vendor.mkdir(parents=True, exist_ok=True)
    for path in source_vendor.iterdir():
        if path.is_file() and path.resolve() != (target_vendor / path.name).resolve():
            shutil.copyfile(path, target_vendor / path.name)
    receipt = builder.load_json(maps / RECEIPT)
    derived = {row["path"]: row for row in receipt["files"]}
    manifest = {key: value for key, value in receipt.items() if key not in ("manifest_sha256", "files")}
    manifest.update(raw_sources=rows, crs="CRS84 / EPSG:4326", simplification_tolerance_degrees=0,
                    geometry_transform="filter only; exact Natural Earth coordinates retained",
                    manifest_canonicalization="Foundation canonical JSON, UTF-8, no terminal LF",
                    builder_receipt=RECEIPT, files=[])
    for directory in (maps, licenses, target_vendor):
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.name.startswith("MAP_DATASET_MANIFEST"):
                continue
            detail = dict(derived.get(path.name, {}))
            detail.update(path=path.relative_to(static).as_posix(), bytes=path.stat().st_size, sha256=sha(path))
            if "source" not in detail:
                detail["source"] = "MapLibre GL JS 5.6.2" if directory == target_vendor else "Conflict Natural Earth reproducible build tooling"
                detail["license"] = "BSD-3-Clause" if directory == target_vendor else "Project asset"
            manifest["files"].append(detail)
    manifest["files"].sort(key=lambda row: row["path"])
    manifest["manifest_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
    (maps / "MAP_DATASET_MANIFEST.json").write_bytes(canonical(manifest) + b"\n")
    (maps / "MAP_DATASET_MANIFEST.json.sha256").write_bytes(f"{sha(maps / 'MAP_DATASET_MANIFEST.json')}  MAP_DATASET_MANIFEST.json\n".encode("ascii"))
    verify_output(static)
    return {p.relative_to(static).as_posix(): sha(p) for p in static.rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-cache", required=True, type=Path)
    parser.add_argument("--output-static", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--verify-reproducible", action="store_true")
    args = parser.parse_args()
    output = args.output_static.resolve()
    if output.exists() and any(output.iterdir()):
        raise builder.BuildError("Output must be an empty, separate build directory")
    first = build(output, args.raw_cache.resolve(), args.offline)
    if args.verify_reproducible:
        with tempfile.TemporaryDirectory(prefix="natural-earth-second-build-") as temp:
            second = build(Path(temp), args.raw_cache.resolve(), True)
            if first != second:
                raise builder.BuildError("Two runtime builds differ")
    print(json.dumps({"result": "PASS", "files": len(first), "hashes": first}, sort_keys=True))


if __name__ == "__main__":
    main()
