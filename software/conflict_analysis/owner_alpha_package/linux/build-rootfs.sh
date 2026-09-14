#!/bin/bash
# Runs only in the pinned Linux build image, never on the Windows host.
set -euo pipefail
umask 022
export LD_LIBRARY_PATH=/opt/python-libs
cd /inputs
test "$(python3.12 --version)" = "Python 3.12.14"
test "$(postgres --version)" = "postgres (PostgreSQL) 18.4 (Debian 18.4-1.pgdg13+1)" || postgres --version | grep -E '^postgres \(PostgreSQL\) 18\.4( |$)'
python3.12 - <<'PY'
import hashlib, json, pathlib
pins = json.loads(pathlib.Path("pins.json").read_bytes())
for kind, folder in (("wheels","wheels"),("debs","debs")):
    for pin in pins[kind]:
        path=pathlib.Path(folder)/pin["filename"]
        assert path.stat().st_size == pin["bytes"]
        assert hashlib.file_digest(path.open("rb"), "sha256").hexdigest() == pin["sha256"]
wheel=json.loads(pathlib.Path("wheel.json").read_bytes())
path=pathlib.Path(wheel["filename"])
assert path.stat().st_size == wheel["bytes"]
assert hashlib.file_digest(path.open("rb"), "sha256").hexdigest() == wheel["sha256"]
PY
# Extract exact nginx runtime files; no maintainer scripts, apt resolver or
# package installation service is invoked. Shared-library dependencies below
# must all resolve from the pinned OCI filesystem.
for archive in /inputs/debs/*.deb; do dpkg-deb --extract "$archive" /; done
test "$(nginx -v 2>&1)" = "nginx version: nginx/1.26.3"
if ldd /usr/sbin/nginx | grep -q 'not found'; then exit 41; fi
python3.12 -m venv --copies /opt/owner-alpha/venv
/opt/owner-alpha/venv/bin/python -m pip install --no-index --no-deps --require-hashes --find-links=/inputs/wheels -r runtime.lock
/opt/owner-alpha/venv/bin/python -m pip install --no-index --no-deps --require-hashes -r application.lock
/opt/owner-alpha/venv/bin/python -m pip check
groupadd --gid 18001 owneralpha
useradd --uid 18001 --gid 18001 --no-create-home --shell /usr/sbin/nologin owneralpha
test "$(id -u postgres)" = 999
usermod -a -G owneralpha postgres
install -d -o owneralpha -g owneralpha -m 0700 /var/lib/owner-alpha
install -d -m 0755 /opt/owner-alpha/static
cp /inputs/{wheel,pins,source}.json /opt/owner-alpha/
cp /opt/owner-alpha/wsl.conf /etc/wsl.conf
printf '127.0.0.1 localhost\n::1 localhost\n' > /etc/hosts
: > /etc/resolv.conf
/opt/owner-alpha/venv/bin/python - <<'PY'
import hashlib, importlib.metadata as m, json, pathlib, subprocess, sys
root=pathlib.Path("/opt/owner-alpha")
wheel=json.loads((root/"wheel.json").read_bytes())
source=json.loads((root/"source.json").read_bytes())
pins=json.loads((root/"pins.json").read_bytes())
versions={p["name"]:m.version(p["name"]) for p in pins["wheels"]
          if p["name"].lower().replace("_","-") not in
          {"build","setuptools","wheel","pyproject-hooks","pytest","pytest-django","pluggy","iniconfig","pygments","colorama"}}
for p in pins["wheels"]:
    if p["name"] in versions: assert versions[p["name"]]==p["version"]
# The accepted wheel deliberately excludes the separately pinned Studio Help
# catalog. Its bytes are carried as an exact source-tree sidecar.
import domain
from django.conf import settings
import os
os.environ.update(DJANGO_SETTINGS_MODULE="conflict_analysis.settings",DJANGO_DEBUG="false",
                  POSTGRES_HOST="/run/owner-alpha-pg",POSTGRES_PASSWORD="")
import django
django.setup()
from django.core.management import call_command
call_command("collectstatic", interactive=False, verbosity=0)
import shutil
shutil.copytree(settings.STATIC_ROOT,root/"static",dirs_exist_ok=True)
shutil.rmtree(settings.STATIC_ROOT)
site=pathlib.Path(domain.__file__).parent.parent
for component in ("domain","production_studio","production_player"):
    assert (site/component).is_dir()
assert (site/"domain/migrations/0018_workspace_assessment_projection.py").is_file()
notices=[]
for path in sorted(pathlib.Path("/usr/share/doc").glob("*/copyright")):
    notices.append(str(path)+"\n"+path.read_text(errors="replace"))
for dist in m.distributions():
    for f in dist.files or []:
        if "license" in str(f).lower() or "copying" in str(f).lower():
            path=dist.locate_file(f)
            if path.is_file(): notices.append(str(f)+"\n"+path.read_text(errors="replace"))
report={"schema":"G10_RUNTIME_REPORT_V1","source":source,"wheel":wheel,
        "python":sys.version.split()[0],"versions":versions,
        "postgresql":subprocess.check_output(["postgres","--version"],text=True).strip(),
        "nginx":subprocess.run(["nginx","-v"],capture_output=True,text=True,check=True).stderr.strip(),
        "debian_inventory":subprocess.check_output(["dpkg-query","-W","-f=${Package}=${Version}\n"],text=True),
        "nginx_archive_pins":pins["debs"],"notices":"\n\n".join(notices),
        "help_sha256":hashlib.sha256((root/"studio_help_ru_v1.json").read_bytes()).hexdigest()}
(root/"runtime-report.json").write_text(json.dumps(report,sort_keys=True,separators=(",",":"))+"\n")
PY
# Build tools and installer caches do not enter the owner runtime.
rm -rf /inputs /root/.cache /var/lib/apt/lists/* /var/cache/apt/* /var/log/* /usr/local/include /usr/local/lib/pkgconfig
find /opt/owner-alpha/venv /usr/local/lib -type d \( -name __pycache__ -o -name ensurepip -o -name pip -o -name 'pip-*.dist-info' \) -prune -exec rm -rf '{}' +
rm -f /opt/owner-alpha/venv/bin/pip* /usr/local/bin/pip* /opt/owner-alpha/build-rootfs.sh
chmod 0755 /opt/owner-alpha/owner-alpha-*.sh
find / -xdev -type f -perm /6000 -exec chmod a-s '{}' +
# Empty state at build time; application secrets are generated only at install.
test -z "$(find /var/lib/owner-alpha -mindepth 1 -print -quit)"
