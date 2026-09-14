"""Six frozen portable nodes; Linux operations run on the actual exported rootfs."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import uuid

import pytest

APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP/"scripts"))
import build_owner_alpha_package as build
import verify_owner_alpha_package as verify

def command(args,input=None,success=True):
    result=subprocess.run([str(x) for x in args],input=input,capture_output=True)
    if success: assert result.returncode==0, "isolated Linux command failed (private stderr withheld)"
    return result

class Runtime:
    def __init__(self,image,port=8765,empty=False):
        self.name="g10-test-"+uuid.uuid4().hex
        self.port=port
        command(["docker","run","--name",self.name,"--network=none","-d","--entrypoint","/bin/sleep",image,"infinity"])
        self.invoke("restore-empty" if empty else "initialize",str(port))
    def raw(self,*args,input=None,success=True):
        return command(["docker","exec","-i",self.name,"/opt/owner-alpha/owner-alpha-supervisor.sh",*args],
                       input=input,success=success)
    def invoke(self,*args):
        return json.loads(self.raw(*args).stdout)
    def sql(self,text):
        return command(["docker","exec","-i","-u","postgres",self.name,"/usr/lib/postgresql/18/bin/psql",
                        "-X","-A","-t","-v","ON_ERROR_STOP=1","-h","/run/owner-alpha-pg",
                        "-d","conflict_analysis"],input=text.encode()).stdout
    def close(self):
        command(["docker","rm","-f",self.name])

@pytest.fixture(scope="module")
def built():
    output=Path(os.environ["G10_ARTIFACT_DIR"])
    rootfs=output/build.ROOTFS_NAME
    image="g10-contract:"+uuid.uuid4().hex
    command(["docker","import",rootfs,image])
    runtime=Runtime(image)
    try: yield output,rootfs,image,runtime
    finally:
        runtime.close()
        command(["docker","image","rm",image])

def test_rootfs_has_exact_runtime_versions_users_permissions_and_no_secrets_build_tools_or_source_tree(built):
    output,rootfs,image,runtime=built
    inventory=verify.rootfs_inventory(rootfs)
    by_name={item["path"]:item for item in inventory["files"]}
    assert by_name["var/lib/owner-alpha"]["mode"]==0o700
    assert not any(p.startswith(("inputs/","source/","root/.cache/","var/lib/owner-alpha/")) for p in by_name)
    for executable in ("usr/bin/gcc","usr/bin/g++","usr/bin/make","usr/local/bin/pip3"):
        assert executable not in by_name
    report=json.loads((output/"runtime-report-1.json").read_bytes())
    assert report["python"]=="3.12.14" and report["postgresql"].startswith("postgres (PostgreSQL) 18.4")
    assert report["nginx"]=="nginx version: nginx/1.26.3"
    actual=runtime.invoke("identity")
    assert actual["wheel"]==report["wheel"]
    assert actual["source"]==report["source"]
    passwd=command(["docker","exec",runtime.name,"cat","/etc/passwd"]).stdout.decode()
    assert "owneralpha:x:18001:18001:" in passwd and "postgres:x:999:" in passwd

def test_postgresql_socket_nginx_static_gunicorn_loopback_and_no_lan_configuration_are_exact(built):
    _,_,_,runtime=built
    health=runtime.invoke("start")
    assert health["phase"]=="READY" and health["tcp_listeners"]==[["127.0.0.1",runtime.port]]
    assert runtime.sql("SHOW listen_addresses;").decode().strip()==""
    assert runtime.sql("SHOW unix_socket_directories;").decode().strip()=="/run/owner-alpha-pg"
    for socket in ("/run/owner-alpha-pg/.s.PGSQL.5432","/run/owner-alpha/gunicorn.sock"):
        command(["docker","exec",runtime.name,"test","-S",socket])
    result=command(["docker","exec",runtime.name,"/opt/owner-alpha/venv/bin/python","-c",
        "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8765/static/production_player/player.css'); assert r.status==200"])
    assert result.returncode==0

def test_clean_rootfs_runs_migrations_collectstatic_help_and_readiness_without_schema_drift(built):
    _,_,_,runtime=built
    result=runtime.invoke("start")
    assert result["phase"]=="READY"
    migrations=runtime.sql("SELECT name FROM django_migrations WHERE app='domain' ORDER BY name;").decode().splitlines()
    assert migrations[-1]=="0018_workspace_assessment_projection" and len(migrations)==18
    assert int(runtime.sql("SELECT count(*) FROM domain_helptopic;"))>0
    before=runtime.invoke("graph")
    runtime.invoke("stop")
    runtime.invoke("start")
    after=runtime.invoke("graph")
    assert before==after
    # Production runtime can never fall back to SQLite after a DB failure.
    assert b"django.db.backends.sqlite3" not in (APP/"owner_alpha_package/linux/owner-alpha-supervisor.sh").read_bytes()

def test_access_secret_transport_public_receipt_and_three_profile_material_never_leak(built):
    output,rootfs,image,runtime=built
    runtime.invoke("start")
    first=runtime.invoke("access")
    pks={p["profile"]:p["user_pk"] for p in first["profiles"]}
    assert set(pks)==set(verify.PROFILE_NAMES) and len(set(pks.values()))==3
    second=runtime.invoke("access")
    assert pks=={p["profile"]:p["user_pk"] for p in second["profiles"]}
    assert set(p["value"] for p in first["profiles"]).isdisjoint(p["value"] for p in second["profiles"])
    for old in first["profiles"]:
        assert int(runtime.sql("SELECT count(*) FROM django_session WHERE session_key='"+old["value"]+"';"))==0
    public=json.dumps(runtime.invoke("health"))
    for cookie in first["profiles"]+second["profiles"]:
        assert cookie["value"] not in public
        assert cookie["value"].encode() not in (output/"runtime-report-1.json").read_bytes()
        assert cookie["httpOnly"] is True and cookie["sameSite"]=="Lax"
    # Revoked canonical users are refused, not reactivated or replaced.
    pk=pks["STUDIO_EDITOR"]
    runtime.sql(f"UPDATE auth_user SET is_active=false WHERE id={pk};")
    denied=runtime.raw("access",success=False)
    assert denied.returncode!=0 and b"BLOCKED_G10_ACCESS_PROVISIONING_GAP" in denied.stderr
    assert runtime.sql(f"SELECT is_active FROM auth_user WHERE id={pk};").strip()==b"f"
    runtime.sql(f"UPDATE auth_user SET is_active=true WHERE id={pk};")  # test fixture cleanup only
    assert pks=={p["profile"]:p["user_pk"] for p in runtime.invoke("access")["profiles"]}

def test_backup_restore_stop_reset_and_uninstall_have_exact_nondestructive_or_destructive_boundaries(built,tmp_path):
    _,_,image,runtime=built
    runtime.invoke("start")
    runtime.invoke("access")
    # Synthetic DB-owned bytes, FK, trigger and sequence exercise full R2
    # outside the immutable product/domain source. No user data enters CI.
    runtime.sql("""
CREATE TABLE g10_parent(id uuid PRIMARY KEY, original bytea NOT NULL, unknown_value numeric, zero_value numeric NOT NULL);
CREATE TABLE g10_child(id bigserial PRIMARY KEY, parent_id uuid REFERENCES g10_parent(id), receipt text NOT NULL);
INSERT INTO g10_parent VALUES ('11111111-1111-4111-8111-111111111111',decode('00ff00deadbeef','hex'),NULL,0);
INSERT INTO g10_child(parent_id,receipt) VALUES ('11111111-1111-4111-8111-111111111111','synthetic immutable receipt');
ALTER TABLE g10_parent OWNER TO owneralpha;
ALTER TABLE g10_child OWNER TO owneralpha;
""")
    before=runtime.invoke("graph")
    archive=runtime.raw("backup").stdout
    assert archive
    candidate=Runtime(image,8766,empty=True)
    try:
        result=candidate.raw("restore",input=archive)
        proof=json.loads(result.stdout)
        assert proof["full_graph_verified"] is True and proof["old_sessions"]==0
        assert candidate.invoke("graph")==before
        assert runtime.invoke("graph")==before
        assert int(candidate.sql("SELECT count(*) FROM django_session;"))==0
        assert candidate.sql("SELECT unknown_value IS NULL,zero_value,encode(original,'hex') FROM g10_parent;").strip()==b"t|0|00ff00deadbeef"
        original_pks=runtime.sql("SELECT id FROM auth_user WHERE username LIKE 'owner-alpha:%' ORDER BY username;")
        assert candidate.sql("SELECT id FROM auth_user WHERE username LIKE 'owner-alpha:%' ORDER BY username;")==original_pks
        assert candidate.invoke("start")["phase"]=="READY"
    finally: candidate.close()
    # Truncation and same-shape receipt corruption both fail in fresh candidates.
    for damaged in (archive[:len(archive)//2],archive.replace(b"PRIVATE_BACKUP",b"PRIVATE_BACXUP",1)):
        candidate=Runtime(image,8766,empty=True)
        try:
            result=candidate.raw("restore",input=damaged,success=False)
            assert result.returncode!=0
            assert runtime.invoke("graph")==before
        finally: candidate.close()
    runtime.invoke("stop")
    assert runtime.invoke("stop")["phase"]=="STOPPED"
    runtime.invoke("start")
    assert runtime.invoke("graph")==before

def test_showcase_sqlite_runserver_mutable_download_and_unaccepted_artifacts_are_absent(built):
    _,rootfs,_,runtime=built
    text=(APP/"owner_alpha_package/linux/owner-alpha-supervisor.sh").read_text()
    for forbidden in ("runserver","seed_zhanaozen_demo","curl ","wget ","pip install","apt-get"):
        assert forbidden not in text
    assert 'USE_SQLITE="false"' in text and 'DJANGO_DEBUG="false"' in text
    with tarfile.open(rootfs) as archive:
        names=archive.getnames()
        assert not any(name.endswith((".sqlite3",".git/config")) for name in names)
        wsl=archive.extractfile("etc/wsl.conf").read().decode()
        assert "enabled=false" in wsl and "appendWindowsPath=false" in wsl
    identity=runtime.invoke("identity")
    assert identity["source"]["base_head"]==verify.CONTROL["base_head"]

