"""Seven portable packaging nodes; Linux operations run on the actual exported rootfs."""
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
    # Inventory assertions retain the former standalone forbidden-artifact coverage.
    text=(APP/"owner_alpha_package/linux/owner-alpha-supervisor.sh").read_text()
    for forbidden in ("runserver","curl ","wget ","pip install","apt-get"):
        assert forbidden not in text
    assert "seed_demo()" in text and "install_pinned_geographic_areas()" in text
    assert 'USE_SQLITE="false"' in text and 'DJANGO_DEBUG="false"' in text
    with tarfile.open(rootfs) as archive:
        names=archive.getnames()
        assert not any(name.endswith((".sqlite3",".git/config")) for name in names)
        wsl=archive.extractfile("etc/wsl.conf").read().decode()
        assert "enabled=false" in wsl and "appendWindowsPath=false" in wsl
    identity=runtime.invoke("identity")
    assert identity["source"]["base_head"]==verify.CONTROL["base_head"]

def test_postgresql_socket_nginx_static_gunicorn_loopback_and_no_lan_configuration_are_exact(built):
    _,_,_,runtime=built
    health=runtime.invoke("start")
    assert health["phase"]=="READY" and health["tcp_listeners"]==[["127.0.0.1",runtime.port]]
    _assert_actual_daemon_readiness(runtime)
    # The actual package runtime, under umask(0077), must expose only its loopback socket.
    command(["docker","exec",runtime.name,"runuser","-u","owneralpha","--",
             "nginx","-t","-c","/run/owner-alpha/nginx.conf"])
    proof=r"""
import os,re
from pathlib import Path
root=Path('/run/owner-alpha')
names={'client_body_temp_path':'client','proxy_temp_path':'proxy','fastcgi_temp_path':'fastcgi',
       'uwsgi_temp_path':'uwsgi','scgi_temp_path':'scgi'}
rows=re.findall(r'^\s*(\w+_temp_path)\s+([^;]+);',(root/'nginx.conf').read_text(),re.M)
assert len(rows)==5 and dict(rows)=={k:str(root/v) for k,v in names.items()}
for directory in (root,*(root/name for name in names.values())):
    st=directory.stat()
    assert not directory.is_symlink() and (st.st_uid,st.st_gid,st.st_mode & 0o7777)==(18001,18001,0o700)
st=Path('/run/owner-alpha-pg').stat()
assert (st.st_uid,st.st_gid,st.st_mode & 0o7777)==(999,18001,0o710)
for service in ('nginx','gunicorn'):
    pid=int((root/(service+'.pid')).read_text().strip());os.kill(pid,0)
    assert service.encode() in Path('/proc/'+str(pid)+'/cmdline').read_bytes()
assert (root/'gunicorn.sock').is_socket()
print('PRIVATE_SERVICE_PATHS=PASS')
"""
    command(["docker","exec",runtime.name,"env","LD_LIBRARY_PATH=/opt/python-libs","/opt/owner-alpha/venv/bin/python","-c",proof])
    denied=command(["docker","exec",runtime.name,"runuser","-u","owneralpha","--",
                    "test","-w","/var/lib/nginx"],success=False)
    assert denied.returncode==1
    assert runtime.sql("SHOW listen_addresses;").decode().strip()==""
    assert runtime.sql("SHOW unix_socket_directories;").decode().strip()=="/run/owner-alpha-pg"
    for socket in ("/run/owner-alpha-pg/.s.PGSQL.5432","/run/owner-alpha/gunicorn.sock"):
        command(["docker","exec",runtime.name,"test","-S",socket])
    result=command(["docker","exec",runtime.name,"env","LD_LIBRARY_PATH=/opt/python-libs","/opt/owner-alpha/venv/bin/python","-c",
        "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8765/static/production_player/player.css'); assert r.status==200"])
    assert result.returncode==0

def test_clean_rootfs_runs_migrations_collectstatic_help_and_readiness_without_schema_drift(built):
    _,_,_,runtime=built
    result=runtime.invoke("start")
    assert result["phase"]=="READY"
    migrations=runtime.sql("SELECT name FROM django_migrations WHERE app='domain' ORDER BY name;").decode().splitlines()
    assert migrations[-1]=="0019_analysis_geography" and len(migrations)==19
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
ALTER TABLE g10_parent ADD CONSTRAINT g10_zero_check CHECK (zero_value >= 0);
CREATE FUNCTION public.g10_restore_trigger() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
ALTER FUNCTION public.g10_restore_trigger() OWNER TO owneralpha;
CREATE TRIGGER g10_user_trigger BEFORE INSERT ON g10_child
FOR EACH ROW WHEN (NEW.receipt IS NOT NULL) EXECUTE FUNCTION public.g10_restore_trigger('original');
""")
    before=runtime.invoke("graph")
    archive=runtime.raw("backup").stdout
    assert archive
    with tarfile.open(fileobj=io.BytesIO(archive)) as backup:
        full=json.load(backup.extractfile('logical.json'))
        without_sessions=json.load(backup.extractfile('logical-without-sessions.json'))
    assert full['django_session']['rows']>0
    assert {k:value for k,value in full.items() if k!='django_session'}==without_sessions==before
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
        _assert_restore_graph_sensitivity(candidate,before)
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

def _assert_restore_graph_sensitivity(candidate,before):
    """Actual catalog mutations in the disposable restored candidate, never product data."""
    internal_sql="SELECT tgname FROM pg_trigger WHERE tgrelid='g10_child'::regclass AND tgisinternal ORDER BY tgname;"
    internal_before=candidate.sql(internal_sql)
    assert internal_before
    candidate.sql("ALTER TABLE g10_child DROP CONSTRAINT g10_child_parent_id_fkey;")
    assert candidate.invoke("graph")["$constraints"]!=before["$constraints"]
    candidate.sql("ALTER TABLE g10_child ADD CONSTRAINT g10_child_parent_id_fkey FOREIGN KEY(parent_id) REFERENCES g10_parent(id);")
    # Newly generated RI names/OIDs must not defeat an unchanged FK graph.
    assert candidate.sql(internal_sql)!=internal_before
    assert candidate.invoke("graph")==before
    candidate.sql("ALTER TABLE g10_child ALTER CONSTRAINT g10_child_parent_id_fkey DEFERRABLE INITIALLY DEFERRED;")
    assert candidate.invoke("graph")["$constraints"]!=before["$constraints"]
    candidate.sql("ALTER TABLE g10_child ALTER CONSTRAINT g10_child_parent_id_fkey NOT DEFERRABLE;")
    assert candidate.invoke("graph")==before
    candidate.sql("ALTER TABLE g10_parent DROP CONSTRAINT g10_zero_check; ALTER TABLE g10_parent ADD CONSTRAINT g10_zero_check CHECK (zero_value >= -1);")
    assert candidate.invoke("graph")["$constraints"]!=before["$constraints"]
    candidate.sql("ALTER TABLE g10_parent DROP CONSTRAINT g10_zero_check; ALTER TABLE g10_parent ADD CONSTRAINT g10_zero_check CHECK (zero_value >= 0);")
    assert candidate.invoke("graph")==before
    candidate.sql("ALTER TABLE g10_child DISABLE TRIGGER g10_user_trigger;")
    assert candidate.invoke("graph")["$triggers"]!=before["$triggers"]
    candidate.sql("ALTER TABLE g10_child ENABLE TRIGGER g10_user_trigger;")
    assert candidate.invoke("graph")==before
    # WHEN and argument changes, with all other identities unchanged, are detected.
    for condition,argument in (("NEW.receipt IS NULL","original"),("NEW.receipt IS NOT NULL","changed")):
        candidate.sql("DROP TRIGGER g10_user_trigger ON g10_child; CREATE TRIGGER g10_user_trigger BEFORE INSERT ON g10_child FOR EACH ROW WHEN ("+condition+") EXECUTE FUNCTION public.g10_restore_trigger('"+argument+"');")
        assert candidate.invoke("graph")["$triggers"]!=before["$triggers"]
    candidate.sql("DROP TRIGGER g10_user_trigger ON g10_child; CREATE TRIGGER g10_user_trigger BEFORE INSERT ON g10_child FOR EACH ROW WHEN (NEW.receipt IS NOT NULL) EXECUTE FUNCTION public.g10_restore_trigger('original');")
    assert candidate.invoke("graph")==before


def test_preexisting_empty_private_pid_files_start_and_restart_without_traceback(built):
    """Fresh rootfs, both empty PID files; use the unchanged public start command."""
    _,_,image,_=built
    runtime=Runtime(image)
    try:
        prepare=r"""
import os
from pathlib import Path
root=Path('/run/owner-alpha');root.mkdir(mode=0o700,exist_ok=True)
os.chown(root,18001,18001);os.chmod(root,0o700)
for name in ('gunicorn','nginx'):
    path=root/(name+'.pid')
    with path.open('xb'):pass
    os.chown(path,18001,18001);os.chmod(path,0o600)
    assert path.stat().st_size==0 and not path.is_symlink()
"""
        command(["docker","exec",runtime.name,"env","LD_LIBRARY_PATH=/opt/python-libs","/opt/owner-alpha/venv/bin/python","-c",prepare])
        for attempt in range(2):
            result=runtime.raw("start")
            assert b"Traceback" not in result.stderr and b"IndexError" not in result.stderr
            health=json.loads(result.stdout)
            assert health["phase"]=="READY" and health["tcp_listeners"]==[["127.0.0.1",runtime.port]]
            _assert_actual_daemon_readiness(runtime)
            assert runtime.invoke("health")["phase"]=="READY"  # Includes /player/ HTTP predicate.
            assert runtime.invoke("stop")["phase"]=="STOPPED"
    finally: runtime.close()


def _assert_actual_daemon_readiness(runtime):
    proof=r"""
import ast,os,re,stat,time
from pathlib import Path
RUN=Path('/run/owner-alpha')
code=Path('/opt/owner-alpha/owner-alpha-supervisor.sh').read_text().split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
names={'Halt','need','read_pid','pid_alive','proc_alive','daemon_pid','daemon_ready','wait_daemon'}
nodes=[n for n in ast.parse(code).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
exec(compile(ast.Module(body=nodes,type_ignores=[]),'exact-runtime-helpers','exec'))
for name in ('gunicorn','nginx'):
    before=time.monotonic();wait_daemon(name)
    assert time.monotonic()-before<=15 and daemon_ready(name)
    assert daemon_pid(name) is not None
assert (RUN/'gunicorn.sock').is_socket()
# A link, directory and FIFO cannot certify a live PID; reads must not block.
folder=RUN/'pid-contract';folder.mkdir(mode=0o700)
try:
    live=folder/'live';live.write_text(str(os.getpid())+'\n')
    assert proc_alive(live)
    linked=folder/'linked';linked.symlink_to(live)
    assert not proc_alive(linked) and not proc_alive(folder)
    fifo=folder/'fifo';os.mkfifo(fifo);assert not proc_alive(fifo)
    hard=folder/'hard';os.link(live,hard);assert not proc_alive(live)
finally:
    for child in folder.iterdir():child.unlink()
    folder.rmdir()
print('BOUNDED_DAEMON_READINESS=PASS')
"""
    command(["docker","exec",runtime.name,"env","LD_LIBRARY_PATH=/opt/python-libs","/opt/owner-alpha/venv/bin/python","-c",proof])


def test_mvp7_zero_permission_profile_matrix_geography_write_and_restart_persistence(built):
    """Real loopback HTTP in the exported rootfs with --network=none."""
    _,_,image,_=built
    runtime=Runtime(image)
    try:
        runtime.invoke("start")
        project=runtime.sql("SELECT id FROM domain_project;").decode().strip()
        assert str(uuid.UUID(project))==project
        granted=runtime.invoke("grant",project)
        assert granted["project_id"]==project and granted["granted"]==["STUDIO_PUBLISHER","PLAYER_ASSESSOR"]
        assert int(runtime.sql("SELECT count(*) FROM auth_user;"))==3
        workspace=runtime.sql("SELECT id FROM domain_projectworkspace WHERE project_id='"+project+"' AND definition_version_id IS NOT NULL ORDER BY id;").decode().splitlines()
        assert workspace
        # Typed demo workspace is the Analysis-ready one.
        from_source = command(["docker","exec",runtime.name,"env","LD_LIBRARY_PATH=/opt/python-libs","/opt/owner-alpha/venv/bin/python","-c",
            "from domain.services.zhanaozen_typed_manifest import WORKSPACE_ID;print(WORKSPACE_ID)"]).stdout.decode().strip()
        assert from_source in workspace
        context=f"/api/foundation/analysis/v1/projects/{project}/workspaces/{from_source}/context/"
        geo=f"/api/foundation/geography/v1/projects/{project}/"
        profiles={p["profile"]:p for p in runtime.invoke("access")["profiles"]}
        expected={
            "STUDIO_EDITOR": {"studio-project:"+project},
            "STUDIO_PUBLISHER": {"studio-project:"+project,"analysis-reader:"+project,"analysis-location-editor:"+project},
            "PLAYER_ASSESSOR": {"studio-project:"+project,"analysis-reader:"+project},
        }
        for role,profile in profiles.items():
            names=set(runtime.sql("SELECT g.name FROM auth_group g JOIN auth_user_groups u ON u.group_id=g.id WHERE u.user_id="+str(profile["user_pk"])+";").decode().splitlines())
            assert names==expected[role]
        assert int(runtime.sql("SELECT count(*) FROM auth_group_permissions;"))==0
        script=r"""
import http.cookies,json,sys,urllib.request,urllib.error
data=json.load(sys.stdin)
origin="http://127.0.0.1:8765"
headers={"Cookie":data["cookie"]["name"]+"="+data["cookie"]["value"]}
if data.get("csrf"):
    headers["Cookie"]+="; csrftoken="+data["csrf"]
    headers["X-CSRFToken"]=data["csrf"]
headers.update(data.get("headers",{}))
raw=json.dumps(data["body"]).encode() if "body" in data else None
if raw is not None: headers.update({"Content-Type":"application/json","Origin":origin})
req=urllib.request.Request(origin+data["path"],data=raw,headers=headers)
try:r=urllib.request.urlopen(req,timeout=20)
except urllib.error.HTTPError as error:r=error
payload=r.read()
cookie=http.cookies.SimpleCookie();cookie.load(r.headers.get("Set-Cookie",""))
print(json.dumps({"status":r.status,"etag":r.headers.get("ETag"),
 "csrf":cookie["csrftoken"].value if "csrftoken" in cookie else None,
 "body":json.loads(payload) if "application/json" in r.headers.get("Content-Type","") else None}))
"""
        def http(role,path,**extra):
            material={"cookie":profiles[role],"path":path,**extra}
            return json.loads(command(["docker","exec","-i",runtime.name,"env","LD_LIBRARY_PATH=/opt/python-libs","/opt/owner-alpha/venv/bin/python","-c",script],
                input=json.dumps(material).encode()).stdout)
        for role in profiles:
            route="/player/" if role=="PLAYER_ASSESSOR" else "/studio/drafts/"
            assert http(role,route)["status"]==200
        for role in ("STUDIO_PUBLISHER","PLAYER_ASSESSOR"):
            assert http(role,"/analysis/")["status"]==200
            assert http(role,context)["status"]==200
            result=http(role,geo+"location/")
            assert result["status"]==200
            assert result["body"]["can_edit"] is (role=="STUDIO_PUBLISHER")
        # The authenticated shell itself is public in exact C; protected Analysis data is denied.
        assert http("STUDIO_EDITOR",context)["status"]==404
        assert http("STUDIO_EDITOR",geo+"location/")["status"]==404
        reader=http("PLAYER_ASSESSOR",geo+"location/")
        assert http("PLAYER_ASSESSOR",geo+"location-revisions/",body={},csrf=reader["csrf"])["status"]==403
        assert http("STUDIO_EDITOR",geo+"location-revisions/",body={})["status"]==404
        current=http("STUDIO_PUBLISHER",geo+"location/")
        # Use the exact accepted service constants; no copied authorization/model code.
        source = command(["docker","exec",runtime.name,"env","LD_LIBRARY_PATH=/opt/python-libs","/opt/owner-alpha/venv/bin/python","-c",
            "import ast,json;from pathlib import Path;t=ast.parse(Path('/opt/owner-alpha/venv/lib/python3.12/site-packages/domain/services/geography.py').read_text());print(json.dumps({x.targets[0].id:ast.literal_eval(x.value) for x in t.body if isinstance(x,ast.Assign) and isinstance(x.targets[0],ast.Name) and x.targets[0].id in ['DATASET','VERSION','POLICY']}))"]).stdout
        constants=json.loads(source)
        body={"latitude":"43.337","longitude":"52.8619","location_kind":"POINT","uncertainty_radius_m":0,
              "area_id":None,"label":"Жанаозен","source_kind":"MANUAL_COORDINATES","source_reference":"MVP7 package contract",
              "rationale":"Синтетическая проверка установки","supersedes_id":None,
              "boundary_dataset_code":constants["DATASET"],"boundary_dataset_version":constants["VERSION"],
              "boundary_policy_version":constants["POLICY"]}
        created=http("STUDIO_PUBLISHER",geo+"location-revisions/",body=body,csrf=current["csrf"],
                     headers={"If-Match":current["etag"],"X-Operation-ID":str(uuid.uuid4())})
        assert created["status"]==201
        revision=created["body"]["head"]
        assert revision["latitude"]=="43.337" and revision["longitude"]=="52.8619"
        runtime.invoke("stop");runtime.invoke("start")
        profiles={p["profile"]:p for p in runtime.invoke("access")["profiles"]}
        assert http("STUDIO_PUBLISHER",geo+"location/")["body"]["head"]==revision
        assert len(http("STUDIO_PUBLISHER",geo+"location-history/")["body"]["revisions"])==1
        check_migrations=r"""
import os
from pathlib import Path
os.environ.update(DJANGO_SETTINGS_MODULE="conflict_analysis.settings",USE_SQLITE="false",
 DJANGO_SECRET_KEY=Path("/var/lib/owner-alpha/django-secret").read_text(),
 POSTGRES_HOST="/run/owner-alpha-pg",POSTGRES_USER="owneralpha",POSTGRES_DB="conflict_analysis",POSTGRES_PASSWORD="")
import django;django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
executor=MigrationExecutor(connection)
assert executor.loader.graph.leaf_nodes("domain")==[("domain","0019_analysis_geography")]
assert executor.migration_plan(executor.loader.graph.leaf_nodes())==[]
print("MIGRATION_0019_EMPTY_PLAN=PASS")
"""
        command(["docker","exec",runtime.name,"env","LD_LIBRARY_PATH=/opt/python-libs","/opt/owner-alpha/venv/bin/python","-c",check_migrations])
        # A recognized prefix with the wrong profile combination is also refused.
        editor=profiles["STUDIO_EDITOR"]["user_pk"]
        group=runtime.sql("SELECT id FROM auth_group WHERE name='analysis-reader:"+project+"';").decode().strip()
        runtime.sql(f"INSERT INTO auth_user_groups(user_id,group_id) VALUES ({editor},{group});")
        denied=runtime.raw("access",success=False)
        assert denied.returncode!=0 and b"BLOCKED_G10_ACCESS_PROVISIONING_GAP" in denied.stderr
        runtime.sql(f"DELETE FROM auth_user_groups WHERE user_id={editor} AND group_id={group};")
        assert runtime.invoke("stop")["phase"]=="STOPPED"
    finally: runtime.close()
