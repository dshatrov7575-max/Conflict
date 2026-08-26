from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Callable
import zipfile


FORMAT = "CA_STUDIO_OWNER_TEST_PACKAGE_V1"
ARCHIVE_ROOT = "ConflictAnalysis-Studio-OWNER-TEST"
FIXED_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
HEX_OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")
APP_PREFIX = "software/conflict_analysis/"

PAYLOAD_PATHS = (
    "software/conflict_analysis/manage.py",
    "software/conflict_analysis/conflict_analysis/__init__.py",
    "software/conflict_analysis/conflict_analysis/studio_showcase_settings.py",
    "software/conflict_analysis/conflict_analysis/studio_showcase_urls.py",
    "software/conflict_analysis/scripts/run_studio_showcase.ps1",
    "software/conflict_analysis/shared_ui/__init__.py",
    "software/conflict_analysis/shared_ui/apps.py",
    "software/conflict_analysis/shared_ui/static/shared_ui/tokens.css",
    "software/conflict_analysis/studio_showcase/__init__.py",
    "software/conflict_analysis/studio_showcase/apps.py",
    "software/conflict_analysis/studio_showcase/session.py",
    "software/conflict_analysis/studio_showcase/urls.py",
    "software/conflict_analysis/studio_showcase/views.py",
    "software/conflict_analysis/studio_showcase/static/studio_showcase/studio.css",
    "software/conflict_analysis/studio_showcase/static/studio_showcase/studio.js",
    "software/conflict_analysis/studio_showcase/templates/studio_showcase/index.html",
    "software/conflict_analysis/studio_showcase/screenshots/README.md",
    "software/conflict_analysis/studio_showcase/screenshots/01-welcome-1440x900.png",
    "software/conflict_analysis/studio_showcase/screenshots/02-editor-6x8-browser.jpg",
    "software/conflict_analysis/studio_showcase/screenshots/03-validation-errors-browser.jpg",
    "software/conflict_analysis/studio_showcase/screenshots/04-evidence-trace-browser.jpg",
    "software/conflict_analysis/studio_showcase/screenshots/05-help-validation-browser.jpg",
    "software/conflict_analysis/studio_showcase/screenshots/06-editor-3x4-browser.jpg",
)

SCREENSHOT_PATHS = tuple(
    path
    for path in PAYLOAD_PATHS
    if path.startswith("software/conflict_analysis/studio_showcase/screenshots/")
    and not path.endswith("/README.md")
)

TEMPLATES = {
    "START_HERE_RU.txt": "START_HERE_RU.txt",
    "KNOWN_LIMITATIONS_RU.md": "KNOWN_LIMITATIONS_RU.md",
    "CLEANUP_RU.md": "CLEANUP_RU.md",
    "VERIFY_CONTENT.ps1": "VERIFY_CONTENT.ps1",
    "RUN_BROWSER_SMOKE.ps1": "RUN_BROWSER_SMOKE.ps1",
    "app/requirements-owner-test.txt": "requirements-owner-test.txt",
}
TEMPLATE_PREFIX = (
    "software/conflict_analysis/studio_showcase/owner_test/templates/"
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _git(repository_root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        check=True,
        capture_output=True,
    ).stdout


def verify_exact_revision(repository_root: Path, head: str, tree: str) -> None:
    if not HEX_OBJECT_ID.fullmatch(head) or not HEX_OBJECT_ID.fullmatch(tree):
        raise ValueError("HEAD and TREE must be exact lowercase 40-character Git IDs")
    actual_head = _git(repository_root, "rev-parse", "HEAD").decode().strip()
    actual_tree = _git(repository_root, "rev-parse", "HEAD^{tree}").decode().strip()
    if (head != actual_head or tree != actual_tree):
        raise ValueError(
            f"Exact revision mismatch: requested {head}/{tree}, "
            f"checkout is {actual_head}/{actual_tree}"
        )


def _destination_for_payload(source_path: str) -> str:
    relative = source_path.removeprefix(APP_PREFIX)
    if relative.startswith("studio_showcase/screenshots/"):
        return relative.removeprefix("studio_showcase/")
    return f"app/{relative}"


def create_package_files(
    read_source: Callable[[str], bytes],
    *,
    head: str,
    tree: str,
    zip_name: str,
) -> tuple[dict[str, bytes], str]:
    files = {
        _destination_for_payload(source): read_source(source)
        for source in PAYLOAD_PATHS
    }
    replacements = {
        "@@HEAD@@": head,
        "@@TREE@@": tree,
        "@@ZIP_NAME@@": zip_name,
    }
    for destination, template_name in TEMPLATES.items():
        content = read_source(f"{TEMPLATE_PREFIX}{template_name}")
        text = content.decode("utf-8")
        for marker, value in replacements.items():
            text = text.replace(marker, value)
        files[destination] = text.replace("\r\n", "\n").encode("utf-8")

    screenshot_register = "".join(
        f"{sha256_bytes(files[_destination_for_payload(source)])}  "
        f"{Path(source).name}\n"
        for source in sorted(SCREENSHOT_PATHS)
    )
    files["screenshots/SHA256SUMS.txt"] = screenshot_register.encode("ascii")

    entries = [
        {
            "path": path,
            "size_bytes": len(content),
            "sha256": sha256_bytes(content),
        }
        for path, content in sorted(files.items())
    ]
    manifest = {
        "format": FORMAT,
        "head": head,
        "tree": tree,
        "build_environment": {
            "archive": "deterministic ZIP_STORED",
            "builder": "CPython 3.12 standard library",
            "target": "Windows 10/11, PowerShell 5.1+, Python 3.12",
            "dependency_install_requires_network": True,
            "dependency_source": "PyPI (network required unless already cached)",
        },
        "boundary": {
            "research_prototype": True,
            "session_only": True,
            "publication": False,
            "foundation_mutation": False,
            "formula_power_prediction": False,
        },
        "package_sha256_record": f"{zip_name}.sha256",
        "manifest_sha256_record": f"{zip_name}.manifest.sha256",
        "screenshot_sha256_register": "screenshots/SHA256SUMS.txt",
        "files": entries,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    manifest_sha256 = sha256_bytes(manifest_bytes)
    files["MANIFEST.json"] = manifest_bytes
    return files, manifest_sha256


def write_deterministic_zip(path: Path, files: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative_path, content in sorted(files.items()):
            member = str(PurePosixPath(ARCHIVE_ROOT, relative_path))
            info = zipfile.ZipInfo(member, date_time=FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits |= 0x800
            archive.writestr(info, content)


def build_package(
    repository_root: Path,
    *,
    head: str,
    tree: str,
    output_directory: Path,
) -> dict[str, str | int]:
    repository_root = repository_root.resolve()
    verify_exact_revision(repository_root, head, tree)
    zip_name = f"ConflictAnalysis-Studio-OWNER-TEST-{head[:12]}.zip"

    def read_tracked(source_path: str) -> bytes:
        return _git(repository_root, "show", f"{head}:{source_path}")

    files, manifest_hash = create_package_files(
        read_tracked,
        head=head,
        tree=tree,
        zip_name=zip_name,
    )
    zip_path = output_directory.resolve() / zip_name
    write_deterministic_zip(zip_path, files)
    zip_hash = sha256_bytes(zip_path.read_bytes())
    hash_path = zip_path.with_name(f"{zip_path.name}.sha256")
    manifest_hash_path = zip_path.with_name(
        f"{zip_path.name}.manifest.sha256"
    )
    hash_path.write_bytes(f"{zip_hash}  {zip_path.name}\n".encode("ascii"))
    manifest_hash_path.write_bytes(
        f"{manifest_hash}  MANIFEST.json\n".encode("ascii")
    )
    return {
        "zip_path": str(zip_path),
        "zip_sha256": zip_hash,
        "manifest_sha256": manifest_hash,
        "sha256_record": str(hash_path),
        "manifest_sha256_record": str(manifest_hash_path),
        "file_count": len(files),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    result = build_package(
        arguments.repository_root,
        head=arguments.head,
        tree=arguments.tree,
        output_directory=arguments.output_directory,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
