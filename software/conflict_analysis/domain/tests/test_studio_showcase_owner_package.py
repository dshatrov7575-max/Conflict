from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from studio_showcase.owner_test.build_owner_test_package import (
    ARCHIVE_ROOT,
    FORMAT,
    create_package_files,
    write_deterministic_zip,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
HEAD = "1" * 40
TREE = "2" * 40
ZIP_NAME = f"ConflictAnalysis-Studio-OWNER-TEST-{HEAD[:12]}.zip"


def _read_worktree_source(relative_path: str) -> bytes:
    path = REPOSITORY_ROOT / relative_path
    assert path.is_file(), f"required package source is missing: {relative_path}"
    return path.read_bytes()


def _package_files() -> tuple[dict[str, bytes], str]:
    return create_package_files(
        _read_worktree_source,
        head=HEAD,
        tree=TREE,
        zip_name=ZIP_NAME,
    )


def test_owner_package_has_required_launcher_payload_evidence_and_boundaries():
    files, manifest_hash = _package_files()

    required = {
        "START_HERE_RU.txt",
        "KNOWN_LIMITATIONS_RU.md",
        "CLEANUP_RU.md",
        "VERIFY_CONTENT.ps1",
        "MANIFEST.json",
        "MANIFEST.sha256",
        "app/manage.py",
        "app/requirements-owner-test.txt",
        "app/scripts/run_studio_showcase.ps1",
        "app/conflict_analysis/studio_showcase_settings.py",
        "app/studio_showcase/session.py",
        "app/studio_showcase/templates/studio_showcase/index.html",
        "app/studio_showcase/static/studio_showcase/studio.js",
        "app/shared_ui/static/shared_ui/tokens.css",
        "screenshots/README.md",
    }
    assert required <= files.keys()
    assert len(
        [path for path in files if path.startswith("screenshots/") and path != "screenshots/README.md"]
    ) == 6

    start_here = files["START_HERE_RU.txt"].decode()
    assert HEAD in start_here
    assert TREE in start_here
    assert ZIP_NAME in start_here
    assert "@@" not in start_here
    limitations = files["KNOWN_LIMITATIONS_RU.md"].decode()
    assert "500" in limitations
    assert "10 000" in limitations
    for boundary in ("Foundation ORM", "Power", "прогноза"):
        assert boundary in limitations

    manifest = json.loads(files["MANIFEST.json"])
    assert manifest["format"] == FORMAT
    assert manifest["head"] == HEAD
    assert manifest["tree"] == TREE
    assert manifest["boundary"] == {
        "research_prototype": True,
        "session_only": True,
        "publication": False,
        "foundation_mutation": False,
        "formula_power_prediction": False,
    }
    assert manifest["package_sha256_record"] == f"{ZIP_NAME}.sha256"
    assert files["MANIFEST.sha256"].decode() == (
        f"{manifest_hash}  MANIFEST.json\n"
    )

    manifested = {entry["path"]: entry for entry in manifest["files"]}
    assert set(manifested) == set(files) - {"MANIFEST.json", "MANIFEST.sha256"}
    for path, entry in manifested.items():
        assert entry["size"] == len(files[path])
        assert entry["sha256"] == hashlib.sha256(files[path]).hexdigest()


def test_owner_package_zip_is_byte_reproducible_and_has_stable_metadata(tmp_path: Path):
    files, _ = _package_files()
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    write_deterministic_zip(first, files)
    write_deterministic_zip(second, dict(reversed(list(files.items()))))

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert all(name.startswith(f"{ARCHIVE_ROOT}/") for name in names)
        assert all(info.date_time == (2020, 1, 1, 0, 0, 0) for info in archive.infolist())
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        extracted_manifest = json.loads(
            archive.read(f"{ARCHIVE_ROOT}/MANIFEST.json")
        )
        assert extracted_manifest["head"] == HEAD
        assert extracted_manifest["tree"] == TREE


def test_packaging_wrapper_requires_exact_head_tree_and_never_commits_an_archive():
    wrapper = (
        REPOSITORY_ROOT
        / "software/conflict_analysis/studio_showcase/owner_test/build_owner_test_package.ps1"
    ).read_text(encoding="utf-8")
    builder = (
        REPOSITORY_ROOT
        / "software/conflict_analysis/studio_showcase/owner_test/build_owner_test_package.py"
    ).read_text(encoding="utf-8")

    assert wrapper.count("ValidatePattern('^[0-9a-f]{40}$')") == 2
    assert "--head $Head --tree $Tree" in wrapper
    assert '"rev-parse", "HEAD^{tree}"' in builder
    assert '"show", f"{head}:{source_path}"' in builder
    assert not list(REPOSITORY_ROOT.rglob("*.zip"))
