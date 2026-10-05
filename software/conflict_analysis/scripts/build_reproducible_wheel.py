#!/usr/bin/env python3
"Build and verify one byte-reproducible Conflict Analysis application wheel."

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile


# Earliest DOS/ZIP timestamp. One constant prevents checkout/build time from
# entering the application wheel while source bytes and RECORD still determine
# its identity.
CANONICAL_SOURCE_DATE_EPOCH = 315_532_800
CANONICAL_ZIP_DATETIME = (1980, 1, 1, 0, 0, 0)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_wheel(
    *,
    project_root: Path,
    output_dir: Path,
    metadata_out: Path | None,
) -> dict[str, object]:
    project_root = project_root.resolve(strict=True)
    output_dir = output_dir.resolve()
    _require(
        output_dir != project_root and project_root not in output_dir.parents,
        "output directory must be outside the project source tree",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _require(not list(output_dir.glob("*.whl")), "output directory already contains a wheel")

    environment = os.environ.copy()
    supplied_epoch = environment.get("SOURCE_DATE_EPOCH")
    canonical_epoch = str(CANONICAL_SOURCE_DATE_EPOCH)
    _require(
        supplied_epoch in (None, "", canonical_epoch),
        f"SOURCE_DATE_EPOCH must be absent or {canonical_epoch}",
    )
    environment["SOURCE_DATE_EPOCH"] = canonical_epoch

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-input",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(output_dir),
            ".",
        ],
        cwd=project_root,
        env=environment,
        check=True,
    )

    wheels = sorted(output_dir.glob("*.whl"))
    _require(len(wheels) == 1, f"expected exactly one application wheel, found {len(wheels)}")
    wheel = wheels[0]
    with ZipFile(wheel) as archive:
        infos = archive.infolist()
        timestamp_mismatches = sorted(
            info.filename
            for info in infos
            if info.date_time != CANONICAL_ZIP_DATETIME
        )
    _require(infos, "application wheel is empty")
    _require(
        not timestamp_mismatches,
        f"wheel contains non-canonical ZIP timestamps: {timestamp_mismatches[:10]}",
    )

    payload: dict[str, object] = {
        "status": "PASS",
        "wheel": wheel.name,
        "wheel_path": str(wheel),
        "bytes": wheel.stat().st_size,
        "sha256": _sha256(wheel),
        "entries": len(infos),
        "source_date_epoch": CANONICAL_SOURCE_DATE_EPOCH,
        "zip_datetime": list(CANONICAL_ZIP_DATETIME),
    }
    if metadata_out is not None:
        metadata_out = metadata_out.resolve()
        metadata_out.parent.mkdir(parents=True, exist_ok=True)
        metadata_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--metadata-out", type=Path)
    return result


def main() -> None:
    args = parser().parse_args()
    build_wheel(
        project_root=args.project_root,
        output_dir=args.output_dir,
        metadata_out=args.metadata_out,
    )


if __name__ == "__main__":
    main()
