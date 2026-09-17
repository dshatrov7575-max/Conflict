#!/bin/bash
# The only privileged controller lives inside this package-owned WSL distro.
# Windows never elevates. Secrets pass via a private inherited stream only.
set -euo pipefail
export LD_LIBRARY_PATH=/opt/python-libs
export PATH=/opt/owner-alpha/venv/bin:/usr/lib/postgresql/18/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
exec /opt/owner-alpha/venv/bin/python - "$@" 3<&0 <<'PY'
from __future__ import annotations
import contextlib
import datetime
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import tarfile
import time
import uuid

PACKAGE=Path("/opt/owner-alpha")
STATE=Path("/var/lib/owner-alpha")
RUN=Path("/run/owner-alpha")
PG=STATE/"postgres"
PGSOCK=Path("/run/owner-alpha-pg")
PROFILES=("STUDIO_EDITOR","STUDIO_PUBLISHER","PLAYER_ASSESSOR")
EDITOR=frozenset("domain."+p for p in (
 "studio_read_definition","studio_create_definition_draft",
 "studio_clone_definition_draft","studio_save_definition_draft"))
PUBLISHER=frozenset("domain."+p for p in (
 "studio_read_definition","studio_validate_definition","studio_publish_definition"))
os.umask(0o077)

class Halt(Exception):
    def __init__(self, code): self.code=code
def need(value, code="BLOCKED_G10_BACKUP_RESTORE_GAP"):
    if not value: raise Halt(code)
def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode()
def read(path): return json.loads(path.read_bytes())
def digest(path):
    with path.open("rb") as stream: return hashlib.file_digest(stream,"sha256").hexdigest()
def write(path,value):
    tmp=path.with_suffix(path.suffix+".pending")
    with tmp.open("xb") as stream:
        stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(tmp,path)
def execute(args, *, user=None, input=None, binary=False):
    cmd=(["runuser","-u",user,"--"] if user else [])+[str(a) for a in args]
    result=subprocess.run(cmd,input=input,capture_output=True,text=not binary,check=False)
    # Do not include argv, SQL, stdout, stderr or exception text in public failures.
    need(result.returncode==0,"BLOCKED_G10_RUNTIME_OPERATION_FAILED")
    return result.stdout
def pgcommand(args,**kwargs):
    return execute(args,user="postgres",**kwargs)
def identity():
    return {"source":read(PACKAGE/"source.json"),"wheel":read(PACKAGE/"wheel.json"),
            "pins":read(PACKAGE/"pins.json")}
def runtime_id():
    return hashlib.sha256(canonical(identity())).hexdigest()
def state():
    s=read(STATE/"state.json")
    need(s["runtime_id"]==runtime_id(),"BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    need(type(s["port"]) is int and 1024<=s["port"]<=65535,"BLOCKED_G10_NETWORK_EXPOSURE")
    return s
def proc_alive(path):
    if not path.exists(): return False
    pid=int(path.read_text().splitlines()[0])
    try: os.kill(pid,0); return True
    except ProcessLookupError: return False
def configure_env():
    s=state()
    os.environ.update(DJANGO_SETTINGS_MODULE="conflict_analysis.settings",
        DJANGO_SECRET_KEY=(STATE/"django-secret").read_text(),
        DJANGO_DEBUG="false",DJANGO_ALLOWED_HOSTS="127.0.0.1",
        USE_SQLITE="false",POSTGRES_HOST=str(PGSOCK),POSTGRES_USER="owneralpha",
        POSTGRES_DB="conflict_analysis",POSTGRES_PASSWORD="",POSTGRES_CONN_MAX_AGE="0")
    import django
    django.setup()
    from django.conf import settings
    need(not settings.DEBUG and settings.DATABASES["default"]["ENGINE"]=="django.db.backends.postgresql",
         "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    return s
def start_pg():
    PGSOCK.mkdir(exist_ok=True,mode=0o710)
    need(not PGSOCK.is_symlink(),"BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    # mkdir's requested mode is masked by the controller's umask(0077).
    os.chmod(PGSOCK,0o710)
    os.chown(PGSOCK,999,18001)
    st=PGSOCK.stat()
    need((st.st_uid,st.st_gid,st.st_mode & 0o7777)==(999,18001,0o710),
         "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    if not proc_alive(PG/"postmaster.pid"):
        pgcommand(["pg_ctl","-D",PG,"-l","/dev/null","-w","-t","30","start"])
    return True
def sql(query, *, database="conflict_analysis"):
    return pgcommand(["psql","-X","-A","-t","-v","ON_ERROR_STOP=1","-h",PGSOCK,"-d",database],
                     input=query)
def provision_empty(port):
    need(not (STATE/"state.json").exists(),"BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    need(not any(STATE.iterdir()),"BLOCKED_G10_BACKUP_RESTORE_GAP")
    need(type(port) is int and 1024<=port<=65535,"BLOCKED_G10_NETWORK_EXPOSURE")
    # No database or app secret exists in the distributed rootfs.
    os.chmod(STATE,0o710); os.chown(STATE,0,18001)
    PG.mkdir(mode=0o700); os.chown(PG,999,18001)
    pgcommand(["initdb","-D",PG,"--encoding=UTF8","--locale=C.UTF-8","--auth-local=peer",
               "--auth-host=reject","--no-instructions"])
    with (PG/"postgresql.conf").open("a") as out:
        out.write("\nlisten_addresses = ''\nunix_socket_directories = '/run/owner-alpha-pg'\n"
                  "unix_socket_permissions = 0770\nunix_socket_group = 'owneralpha'\n"
                  "logging_collector = off\nlog_statement = 'none'\n"
                  "log_min_error_statement = 'panic'\nlog_min_messages = 'panic'\n"
                  "log_connections = off\nlog_disconnections = off\n")
    (PG/"pg_hba.conf").write_text("local all postgres peer\n"
        "local conflict_analysis owneralpha peer map=g10\nlocal all all reject\n")
    (PG/"pg_ident.conf").write_text("g10 root owneralpha\ng10 owneralpha owneralpha\n")
    (STATE/"django-secret").write_text(secrets.token_urlsafe(64))
    write(STATE/"state.json",{"runtime_id":runtime_id(),"port":port,"phase":"EMPTY",
                             "instance":str(uuid.uuid4())})
    start_pg()
    sql("CREATE ROLE owneralpha LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;\n"
        "CREATE DATABASE conflict_analysis OWNER owneralpha;\n",database="postgres")
def profile_groups(profile, project_id):
    names={"studio-project:"+str(project_id)}
    if profile in ("STUDIO_PUBLISHER","PLAYER_ASSESSOR"):
        names.add("analysis-reader:"+str(project_id))
    if profile=="STUDIO_PUBLISHER":
        names.add("analysis-location-editor:"+str(project_id))
    return names
def users(create=False, validate_scope=True):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    from django.db import transaction
    from domain.policies import studio_principal_from_user
    from domain.services.player_experiments import G8_REQUIRED_PERMISSIONS, assessment_principal
    User=get_user_model()
    mapping_path=STATE/"principals.json"
    permissions={"STUDIO_EDITOR":EDITOR,"STUDIO_PUBLISHER":PUBLISHER,
                 "PLAYER_ASSESSOR":G8_REQUIRED_PERMISSIONS}
    if create:
        need(not mapping_path.exists(),"BLOCKED_G10_ACCESS_PROVISIONING_GAP")
        mapping={}
        with transaction.atomic():
            for profile in PROFILES:
                username="owner-alpha:"+profile
                need(not User.objects.filter(username=username).exists(),
                     "BLOCKED_G10_ACCESS_PROVISIONING_GAP")
                user=User(username=username,is_staff=False,is_superuser=False,is_active=True)
                user.set_unusable_password(); user.save()
                rows=list(Permission.objects.filter(content_type__app_label="domain",
                          codename__in=[p.split(".",1)[1] for p in permissions[profile]]))
                need(len(rows)==len(permissions[profile]),"BLOCKED_G10_ACCESS_PROVISIONING_GAP")
                user.user_permissions.set(rows)
                mapping[profile]=user.pk
        write(mapping_path,mapping)
    mapping=read(mapping_path)
    need(set(mapping)==set(PROFILES) and len(set(mapping.values()))==3,
         "BLOCKED_G10_PROFILE_ISOLATION_GAP")
    verified={}
    for profile in PROFILES:
        user=User.objects.get(pk=mapping[profile])
        need(user.username=="owner-alpha:"+profile and user.is_active and not user.is_staff
             and not user.is_superuser and not user.has_usable_password(),
             "BLOCKED_G10_ACCESS_PROVISIONING_GAP")
        need(frozenset(user.get_all_permissions())==permissions[profile],
             "BLOCKED_G10_ACCESS_PROVISIONING_GAP")
        groups=list(user.groups.all())
        for group in groups:
            need(re.fullmatch(r"(?:studio-project|analysis-reader|analysis-location-editor):[0-9a-f-]{36}",group.name)
                 and not group.permissions.exists(),"BLOCKED_G10_ACCESS_PROVISIONING_GAP")
        if validate_scope and not create:
            from domain.models import Project
            from domain.demo_data import PROJECT_CODE, stable_demo_uuid
            actual={g.name for g in groups}
            scoped={uuid.UUID(name.split(":",1)[1]) for name in actual if name.startswith("studio-project:")}
            need(stable_demo_uuid("project",PROJECT_CODE) in scoped,
                 "BLOCKED_G10_ACCESS_PROVISIONING_GAP")
            need(Project.objects.filter(pk__in=scoped).count()==len(scoped),
                 "BLOCKED_G10_ACCESS_PROVISIONING_GAP")
            expected=set().union(*(profile_groups(profile,p) for p in scoped))
            need(actual==expected,"BLOCKED_G10_ACCESS_PROVISIONING_GAP")
        if profile=="PLAYER_ASSESSOR": assessment_principal(user)
        else: need(studio_principal_from_user(user).role.value==profile,
                   "BLOCKED_G10_ACCESS_PROVISIONING_GAP")
        verified[profile]=user
    return verified
def seed_demo():
    from django.contrib.auth.models import Group
    from domain.services.seed import seed_zhanaozen_demo
    from domain.services.geography import install_pinned_geographic_areas
    from domain.services.project_definitions import project_access_group_name
    from domain.services.analysis_admission import analysis_reader_group_name, analysis_location_editor_group_name
    project=seed_zhanaozen_demo()
    install_pinned_geographic_areas()
    verified=users(validate_scope=False)
    for profile,user in verified.items():
        for name in profile_groups(profile,project.pk):
            group,_=Group.objects.get_or_create(name=name)
            need(not group.permissions.exists(),"BLOCKED_G10_ACCESS_PROVISIONING_GAP")
            user.groups.add(group)
    users()


def migrate_clean():
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.core.checks import run_checks, ERROR
    executor=MigrationExecutor(connection)
    leaves=executor.loader.graph.leaf_nodes("domain")
    need(leaves==[("domain","0019_analysis_geography")],
         "BLOCKED_G10_UNAUTHORIZED_MIGRATION")
    call_command("migrate",interactive=False,verbosity=0)
    executor=MigrationExecutor(connection)
    need(executor.loader.graph.leaf_nodes("domain")==[("domain","0019_analysis_geography")]
         and not executor.migration_plan(executor.loader.graph.leaf_nodes()),
         "BLOCKED_G10_UNAUTHORIZED_MIGRATION")
    call_command("makemigrations",check=True,dry_run=True,verbosity=0)
    need(not [e for e in run_checks(include_deployment_checks=True) if e.level>=ERROR],
         "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    call_command("provision_studio_help",str(PACKAGE/"studio_help_ru_v1.json"),verbosity=0,
                 stdout=io.StringIO(),stderr=io.StringIO())
    call_command("provision_player_help",verbosity=0,stdout=io.StringIO(),stderr=io.StringIO())
def session_revoke():
    from django.contrib.sessions.models import Session
    # This DB belongs exclusively to this package instance. No old browser
    # session, including an expired or restored one, may survive a rotation.
    Session.objects.all().delete()
def prepare_sessions():
    from django.contrib.auth import SESSION_KEY,BACKEND_SESSION_KEY,HASH_SESSION_KEY
    from django.contrib.sessions.backends.db import SessionStore
    from django.conf import settings
    verified=users()
    session_revoke()
    cookies=[]
    for profile,user in verified.items():
        session=SessionStore()
        session[SESSION_KEY]=str(user.pk)
        session[BACKEND_SESSION_KEY]="django.contrib.auth.backends.ModelBackend"
        session[HASH_SESSION_KEY]=user.get_session_auth_hash()
        session.set_expiry(3600); session.create()
        cookies.append({"profile":profile,"user_pk":user.pk,"name":settings.SESSION_COOKIE_NAME,
                        "value":session.session_key,"expires":int(time.time())+3500,
                        "httpOnly":True,"sameSite":"Lax","secure":False,"path":"/"})
    return {"profiles":cookies,"origin":"http://127.0.0.1:"+str(state()["port"]),
            "runtime_id":runtime_id()}
def grant(project_id):
    from django.contrib.auth.models import Group
    from django.db import transaction
    from domain.models import Project
    from domain.services.project_definitions import project_access_group_name
    verified=users()
    project_id=uuid.UUID(project_id)
    need(Project.objects.filter(pk=project_id).exists(),"BLOCKED_G10_ACCESS_PROVISIONING_GAP")
    group=Group.objects.get(name=project_access_group_name(project_id))
    need(not group.permissions.exists(),"BLOCKED_G10_ACCESS_PROVISIONING_GAP")
    with transaction.atomic():
        for profile in ("STUDIO_PUBLISHER","PLAYER_ASSESSOR"):
            for name in profile_groups(profile,project_id):
                scoped,_=Group.objects.get_or_create(name=name)
                need(not scoped.permissions.exists(),"BLOCKED_G10_ACCESS_PROVISIONING_GAP")
                verified[profile].groups.add(scoped)
    users()
    return {"project_id":str(project_id),"granted":["STUDIO_PUBLISHER","PLAYER_ASSESSOR"]}
def start_services():
    s=state()
    need(s["phase"] in ("READY","STOPPED","RESTORED"),"BLOCKED_G10_BACKUP_RESTORE_GAP")
    start_pg(); configure_env(); users()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    executor=MigrationExecutor(connection)
    need(executor.loader.graph.leaf_nodes("domain")==[("domain","0019_analysis_geography")]
         and not executor.migration_plan(executor.loader.graph.leaf_nodes()),
         "BLOCKED_G10_UNAUTHORIZED_MIGRATION")
    temp_paths={"client_body_temp_path":"client","proxy_temp_path":"proxy",
                "fastcgi_temp_path":"fastcgi","uwsgi_temp_path":"uwsgi","scgi_temp_path":"scgi"}
    config=(PACKAGE/"nginx.conf").read_text().replace("__PORT__",str(s["port"]))
    directives=re.findall(r"^\s*(\w+_temp_path)\s+([^;]+);",config,re.M)
    need(len(directives)==5 and dict(directives)=={k:str(RUN/v) for k,v in temp_paths.items()},
         "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    for directory in (RUN,*(RUN/name for name in temp_paths.values())):
        directory.mkdir(mode=0o700,exist_ok=True)
        need(not directory.is_symlink(),"BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
        os.chmod(directory,0o700); os.chown(directory,18001,18001)
        st=directory.stat()
        need((st.st_uid,st.st_gid,st.st_mode & 0o7777)==(18001,18001,0o700),
             "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    (RUN/"nginx.conf").write_text(config)
    os.chmod(RUN/"nginx.conf",0o600); os.chown(RUN/"nginx.conf",18001,18001)
    execute(["nginx","-t","-c",RUN/"nginx.conf"],user="owneralpha")
    if not proc_alive(RUN/"gunicorn.pid"):
        execute([PACKAGE/"venv/bin/gunicorn","--config",PACKAGE/"gunicorn.conf.py",
                 "conflict_analysis.wsgi:application"],user="owneralpha")
    if not proc_alive(RUN/"nginx.pid"):
        execute(["nginx","-c",RUN/"nginx.conf"],user="owneralpha")
    need(proc_alive(RUN/"nginx.pid") and proc_alive(RUN/"gunicorn.pid")
         and (RUN/"gunicorn.sock").is_socket(),"BLOCKED_G10_RUNTIME_OPERATION_FAILED")
    need(network_check()["tcp_listeners"]==[["127.0.0.1",s["port"]]],
         "BLOCKED_G10_NETWORK_EXPOSURE")
    s["phase"]="READY"; write(STATE/"state.json",s)
    return health()
def network_check():
    import ipaddress
    # Inspect kernel sockets, including unknown daemons; don't infer absent
    # or unreadable state as zero. PG and Gunicorn must have no TCP listeners.
    listeners=[]
    for file in (Path("/proc/net/tcp"),Path("/proc/net/tcp6")):
        need(file.exists(),"BLOCKED_G10_NETWORK_EXPOSURE")
        for line in file.read_text().splitlines()[1:]:
            columns=line.split()
            if columns[3]!="0A": continue
            address,port=columns[1].split(":")
            listeners.append((address,int(port,16)))
    allowed={("0100007F",state()["port"])}
    need(set(listeners)<=allowed,"BLOCKED_G10_NETWORK_EXPOSURE")
    return {"tcp_listeners":[["127.0.0.1",p] for _,p in listeners]}
def health():
    s=state()
    if s["phase"]!="READY":
        return {"phase":s["phase"],"instance":s["instance"],"runtime_id":runtime_id()}
    configure_env(); users()
    need(proc_alive(PG/"postmaster.pid") and proc_alive(RUN/"gunicorn.pid")
         and proc_alive(RUN/"nginx.pid"),"BLOCKED_G10_RUNTIME_OPERATION_FAILED")
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT version(), current_database(), inet_server_addr()")
        row=cursor.fetchone()
    need(row[0].startswith("PostgreSQL 18.4 ") and row[1]=="conflict_analysis" and row[2] is None,
         "BLOCKED_G10_NETWORK_EXPOSURE")
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:"+str(s["port"])+"/player/",timeout=15) as response:
            need(response.status==200,"BLOCKED_G10_RUNTIME_OPERATION_FAILED")
    except urllib.error.HTTPError as error:
        need(error.code in (401,403),"BLOCKED_G10_RUNTIME_OPERATION_FAILED")
    return {"phase":"READY","instance":s["instance"],"runtime_id":runtime_id(),
            "user_pks":read(STATE/"principals.json"),**network_check()}
def stop_web():
    # Graceful drain only. Unknown/PID-reused/unresponsive processes fail closed;
    # no force-kill followed by a false consistency claim.
    for name,expected in (("nginx","nginx"),("gunicorn","gunicorn")):
        pidfile=RUN/(name+".pid")
        if not proc_alive(pidfile): continue
        pid=int(pidfile.read_text().strip())
        command=Path("/proc/"+str(pid)+"/cmdline").read_bytes()
        need(expected.encode() in command,"BLOCKED_G10_OPERATION_UNKNOWN")
        os.kill(pid,signal.SIGQUIT if name=="nginx" else signal.SIGTERM)
        deadline=time.monotonic()+140
        while proc_alive(pidfile) and time.monotonic()<deadline: time.sleep(.2)
        need(not proc_alive(pidfile),"BLOCKED_G10_OPERATION_BUSY")
def quiesce():
    stop_web()
    from django.db import connections
    connections.close_all()
    result=sql("""
SELECT json_build_object(
 'sessions',(SELECT count(*) FROM pg_stat_activity
    WHERE datname='conflict_analysis' AND pid<>pg_backend_pid()
      AND backend_type='client backend'),
 'transactions',(SELECT count(*) FROM pg_stat_activity
    WHERE datname='conflict_analysis' AND pid<>pg_backend_pid() AND xact_start IS NOT NULL),
 'locks',(SELECT count(*) FROM pg_locks
    WHERE database=(SELECT oid FROM pg_database WHERE datname='conflict_analysis')
      AND pid<>pg_backend_pid()));
""")
    counts=json.loads(result)
    need(set(counts)=={"sessions","transactions","locks"} and
         all(type(x) is int and x==0 for x in counts.values()),"BLOCKED_G10_OPERATION_BUSY")
    return counts
def graph(include_sessions=True):
    import psycopg
    from psycopg import sql as q
    data={}
    with psycopg.connect(host=str(PGSOCK),dbname="conflict_analysis",user="owneralpha") as conn:
        tables=conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
        for (table,) in tables:
            if not include_sessions and table=="django_session": continue
            rows=conn.execute(q.SQL("SELECT to_jsonb(t) FROM {} AS t").format(q.Identifier(table)))
            values=sorted(canonical(row[0]) for row in rows)
            data[table]={"rows":len(values),"sha256":hashlib.sha256(b"".join(values)).hexdigest()}
        data["$sequences"]=[list(row) for row in conn.execute(
          "SELECT sequencename,sequenceowner,data_type::text,start_value,min_value,max_value,increment_by,cycle,cache_size,last_value "
          "FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename")]
        data["$permissions"]=[list(row) for row in conn.execute(
          "SELECT grantor,grantee,table_schema,table_name,privilege_type,is_grantable,with_hierarchy "
          "FROM information_schema.table_privileges WHERE table_schema='public' ORDER BY 1,2,3,4,5")]
        data["$constraints"]=[list(row) for row in conn.execute(
          "SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) FROM pg_constraint "
          "WHERE connamespace='public'::regnamespace ORDER BY 1,2")]
        data["$triggers"]=[list(row) for row in conn.execute(
          "SELECT tgrelid::regclass::text,tgname,pg_get_triggerdef(oid),tgenabled FROM pg_trigger "
          "WHERE tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace) ORDER BY 1,2")]
        data["$extensions"]=[list(row) for row in conn.execute(
          "SELECT extname,extversion FROM pg_extension ORDER BY extname")]
        data["$roles"]=[list(row) for row in conn.execute(
          "SELECT rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,"
          "rolconnlimit,rolvaliduntil::text,rolbypassrls,rolconfig FROM pg_roles ORDER BY rolname")]
    return data
def backup():
    quiescence=quiesce()
    folder=STATE/"backups"/str(uuid.uuid4())
    folder.mkdir(parents=True,mode=0o700)
    sql("SELECT 1;")
    pgcommand(["pg_dump","-h",PGSOCK,"-d","conflict_analysis","--format=custom",
               "--file",folder/"database.dump"])
    # postgres must be able to write only its temporary dump directory.
    return folder
def backup_stream():
    import shutil
    quiescence=quiesce()
    base=STATE/"backups"; base.mkdir(exist_ok=True,mode=0o700)
    folder=base/str(uuid.uuid4()); folder.mkdir(mode=0o700)
    # Capture stdout into a root-owned private file; never print a dump in logs.
    dump=pgcommand(["pg_dump","-h",PGSOCK,"-d","conflict_analysis","--format=custom"],binary=True)
    (folder/"database.dump").write_bytes(dump)
    globals_bytes=pgcommand(["pg_dumpall","-h",PGSOCK,"--globals-only"],binary=True)
    (folder/"globals.sql").write_bytes(globals_bytes)
    for filename in ("principals.json","django-secret"):
        shutil.copyfile(STATE/filename,folder/filename)
    before=graph()
    need(before==graph(),"BLOCKED_G10_OPERATION_UNKNOWN")
    write(folder/"logical.json",before)
    write(folder/"logical-without-sessions.json",graph(False))
    # Complete bytea DocumentContent originals are part of every-row DB graph.
    objects={p.name:{"bytes":p.stat().st_size,"sha256":digest(p)} for p in folder.iterdir()}
    manifest={"schema":"G10_PRIVATE_BACKUP_V1","runtime_id":runtime_id(),
              "identity":identity(),"source_instance":state()["instance"],
              "quiescence":quiescence,"objects":objects,"full_database":True,
              "originals_storage":"PostgreSQL DocumentContent.original_bytes",
              "no_redownload":True}
    write(folder/"private-manifest.json",manifest)
    archive=folder.with_suffix(".tar")
    with tarfile.open(archive,"x") as out:
        for p in sorted(folder.iterdir()): out.add(p,arcname=p.name,recursive=False)
    quiesce()
    s=state(); s["phase"]="STOPPED"; write(STATE/"state.json",s)
    with archive.open("rb") as stream: shutil.copyfileobj(stream,sys.stdout.buffer)
    return None
def restore_stream():
    import shutil
    need(state()["phase"]=="EMPTY","BLOCKED_G10_BACKUP_RESTORE_GAP")
    candidate=STATE/"restore-candidate"; candidate.mkdir(mode=0o700)
    archive=candidate/"input.tar"
    with os.fdopen(3,"rb",closefd=False) as incoming, archive.open("xb") as output:
        shutil.copyfileobj(incoming,output)
    allowed={"database.dump","globals.sql","principals.json","django-secret",
             "logical.json","logical-without-sessions.json","private-manifest.json"}
    with tarfile.open(archive) as tar:
        members=tar.getmembers()
        need(len(members)==len(allowed) and {m.name for m in members}==allowed)
        for member in members:
            need(member.isfile() and not member.issym() and not member.islnk())
            with tar.extractfile(member) as src,(candidate/member.name).open("xb") as dst:
                shutil.copyfileobj(src,dst)
    manifest=read(candidate/"private-manifest.json")
    need(manifest["schema"]=="G10_PRIVATE_BACKUP_V1")
    need(manifest["runtime_id"]==runtime_id() and manifest["identity"]==identity(),
         "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    need(set(manifest["objects"])==allowed-{"private-manifest.json"})
    for name,meta in manifest["objects"].items():
        p=candidate/name
        need(meta=={"bytes":p.stat().st_size,"sha256":digest(p)})
    # Only an exact, already known private backup receipt can reach this path
    # from Windows. Hash equality is never treated as origin authentication.
    globals_sql=(candidate/"globals.sql").read_text()
    roles=sql("SELECT rolname FROM pg_roles WHERE rolname NOT LIKE 'pg_%' ORDER BY rolname;",database="postgres").splitlines()
    need(roles==["owneralpha","postgres"])
    # Reconcile the two exact existing roles; reject arbitrary role expansion.
    created=re.findall(r"^CREATE ROLE (.+);$",globals_sql,re.M)
    need(set(created)=={"owneralpha","postgres"})
    globals_sql=re.sub(r"^CREATE ROLE (?:owneralpha|postgres);\n","",globals_sql,flags=re.M)
    sql(globals_sql,database="postgres")
    pgcommand(["pg_restore","-h",PGSOCK,"-d","conflict_analysis","--exit-on-error",
               "--single-transaction"],input=(candidate/"database.dump").read_bytes(),binary=True)
    need(graph()==read(candidate/"logical.json"),"BLOCKED_G10_BACKUP_RESTORE_GAP")
    shutil.copyfile(candidate/"principals.json",STATE/"principals.json")
    shutil.copyfile(candidate/"django-secret",STATE/"django-secret")
    configure_env(); users()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    executor=MigrationExecutor(connection)
    need(executor.loader.graph.leaf_nodes("domain")==[("domain","0019_analysis_geography")]
         and not executor.migration_plan(executor.loader.graph.leaf_nodes()),
         "BLOCKED_G10_UNAUTHORIZED_MIGRATION")
    session_revoke()
    need(graph(False)==read(candidate/"logical-without-sessions.json"))
    s=state(); s["phase"]="RESTORED"; s["restored_from"]=manifest["source_instance"]
    write(STATE/"state.json",s)
    return {"phase":"RESTORED","full_graph_verified":True,"old_sessions":0,
            "source_instance":manifest["source_instance"],"candidate_instance":s["instance"]}
def stop():
    configure_env(); users(); quiesce()
    session_revoke(); quiesce()
    pgcommand(["pg_ctl","-D",PG,"-w","-t","30","stop","-m","fast"])
    s=state(); s["phase"]="STOPPED"; write(STATE/"state.json",s)
    return {"phase":"STOPPED","runtime_id":runtime_id(),"sessions_revoked":True}
def main():
    need(os.geteuid()==0,"BLOCKED_G10_RUNTIME_IDENTITY_DRIFT")
    command=sys.argv[1] if len(sys.argv)>1 else "identity"
    if command=="identity": return identity()
    # Package operation lock is never inferred from an application enum.
    lock=Path("/run/owner-alpha-operation.lock").open("a")
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: raise Halt("BLOCKED_G10_OPERATION_BUSY")
    if command in ("initialize","restore-empty"):
        provision_empty(int(sys.argv[2]))
        if command=="restore-empty": return {"phase":"EMPTY"}
        configure_env(); migrate_clean(); users(create=True); seed_demo()
        s=state(); s["phase"]="STOPPED"; write(STATE/"state.json",s)
        return {"phase":"STOPPED","user_pks":read(STATE/"principals.json")}
    if command=="health":
        if (STATE/"state.json").exists(): return health()
        return {"phase":"UNINITIALIZED","runtime_id":runtime_id()}
    if command=="start": return start_services()
    if command=="restore": return restore_stream()
    if command=="stop":
        if state()["phase"]=="STOPPED" and not proc_alive(PG/"postmaster.pid"):
            return {"phase":"STOPPED","sessions_revoked":True,"runtime_id":runtime_id()}
        return stop()
    start_pg(); configure_env()
    if command=="access": return prepare_sessions()
    if command=="grant": return grant(sys.argv[2])
    if command=="backup": return backup_stream()
    if command=="graph": quiesce(); return graph(False)
    if command=="revoke": session_revoke(); return {"sessions_revoked":True}
    raise Halt("BLOCKED_G10_RUNTIME_OPERATION_FAILED")
try:
    answer=main()
    if answer is not None: sys.stdout.buffer.write(canonical(answer))
except Exception as exc:
    # Public diagnostics deliberately exclude private data, traceback and SQL.
    print(json.dumps({"result":getattr(exc,"code","BLOCKED_G10_RUNTIME_OPERATION_FAILED")}),file=sys.stderr)
    sys.exit(1)
PY
