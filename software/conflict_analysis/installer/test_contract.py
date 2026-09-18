"""Packaging-only checks; none are Windows 11 E2E."""
from pathlib import Path
import ast,copy,hashlib,json,os,re,stat,subprocess,sys,zipfile
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parent
APP=ROOT.parent
sys.path.insert(0,str(APP/'scripts'))
import verify_owner_alpha_package as v
import build_owner_alpha_package as b

def test_external_inputs_have_exact_urls_sizes_hashes():
    lock=json.loads((ROOT/'external-inputs.lock.json').read_text())
    pins=lock['wheels']+lock['debs']+lock['windows_wheels']+[lock['nsis']]
    pins += [pin for image in lock['oci'].values() for pin in image['inputs']]
    for pin in pins:
        assert pin['url'].startswith('https://') and type(pin['bytes']) is int and pin['bytes']>0
        assert v.SHA256.fullmatch(pin['sha256'])
    assert lock['wheels']==b.PINS['wheels'] and lock['debs']==b.PINS['debs']
    assert {k:x['image'] for k,x in lock['oci'].items()}==b.PINS['oci']
    assert lock['nsis']['version']=='3.12'
    assert b.validate_closure()

def test_product_source_and_allowlist_are_bounded(monkeypatch):
    assert v.LOCK['source']['head']=='85a253126bf270664c4786d159994e7359b5d2c5'
    assert v.LOCK['source']['tree']=='5567183dbe16fc6c7c8caac051b7694f37b92457'
    assert v.CONTROL['migration']=='domain/migrations/0019_analysis_geography.py'
    for p in ['domain/models.py','production_studio/browser_tests/audited_authoring.mjs','production_studio/browser_tests/cdp_client.mjs','analysis_dashboard/views.py','domain/migrations/0019_analysis_geography.py']:
        assert not v.allowed_installer_path('software/conflict_analysis/'+p)
    assert v.allowed_installer_path('software/conflict_analysis/installer/build_setup.py')
    base='c8263b81adb8fcb90ec92b65342f9620884c929b'
    first='21c4812a8eaf8d503454699c191d99abaf538036'
    assert v.LOCK['installer_parent']==base and v.LOCK['installer_commit_a']==first
    assert v.LOCK['installer_message']=='build(installer): add MVP7 R1 Windows setup candidate'
    assert v.LOCK['correction_message']=='fix(installer): repair private runtime service paths'
    assert len(v.CORRECTIVE_PATHS)==7 and all(v.allowed_installer_path(p) for p in v.CORRECTIVE_PATHS)
    second='7011f31c8b4a8a21986b85da18d5337e64c7aa28'
    assert v.LOCK['installer_commit_b']==second
    assert v.LOCK['readiness_correction_message']=='fix(installer): harden private daemon readiness'
    assert v.READINESS_PATHS==v.CORRECTIVE_PATHS-{'software/conflict_analysis/owner_alpha_package/linux/nginx.conf'}
    assert len(v.READINESS_PATHS)==6
    third='ce522813cfbfd26c3a06fd53fbde54939559e4d9'
    assert v.LOCK['installer_commit_c']==third
    assert v.LOCK['restore_correction_message']=='fix(installer): canonicalize restore graph verification'
    assert v.RESTORE_PATHS==v.READINESS_PATHS
    fourth='1e109ad2f37d3de4d0d0fa3a9b9ad1dbace182d4'
    assert v.LOCK['installer_commit_d']==fourth
    assert v.LOCK['transaction_correction_message']=='fix(installer): make Windows installation transactional'
    assert len(v.TRANSACTION_PATHS)==11
    fifth='43a37838b94695e3516ca086c0e409719328f8e4'
    assert v.LOCK['installer_commit_e']==fifth
    assert v.LOCK['uninstall_correction_message']=='fix(installer): canonicalize uninstall target path'
    assert len(v.UNINSTALL_PATHS)==5
    sixth='33742b06d2c38fad567d52f5a07d2bc34fce5eaa'
    assert v.LOCK['installer_commit_e2']==sixth
    assert v.LOCK['harness_correction_message']=='test(installer): stabilize interrupted rollback contract'
    assert v.HARNESS_PATHS=={'software/conflict_analysis/owner_alpha_package/tests/OwnerAlpha.Windows.Contract.Tests.ps1','software/conflict_analysis/installer/test_contract.py','software/conflict_analysis/installer/source.lock.json','software/conflict_analysis/scripts/verify_owner_alpha_package.py'}
    head='d'*40;tree='e'*40
    answers={
        ('rev-parse','HEAD'):head, ('rev-parse','HEAD^{tree}'):tree,
        ('branch','--show-current'):v.LOCK['installer_branch'],
        ('show','-s','--format=%P',first):base,
        ('show','-s','--format=%B',first):v.LOCK['installer_message'],
        ('status','--porcelain=v1','--untracked-files=all'):'',
        ('show','-s','--format=%P',second):first,
        ('show','-s','--format=%B',second):v.LOCK['correction_message'],
        ('diff','--name-status','--no-renames',first,second):'\n'.join('M\t'+p for p in sorted(v.CORRECTIVE_PATHS)),
        ('show','-s','--format=%P',third):second,
        ('show','-s','--format=%B',third):v.LOCK['readiness_correction_message'],
        ('diff','--name-status','--no-renames',second,third):'\n'.join('M\t'+p for p in sorted(v.READINESS_PATHS)),
        ('show','-s','--format=%P',fourth):third,
        ('show','-s','--format=%B',fourth):v.LOCK['restore_correction_message'],
        ('diff','--name-status','--no-renames',third,fourth):'\n'.join('M\t'+p for p in sorted(v.RESTORE_PATHS)),
        ('rev-list','--count',base+'..'+fourth):'4',
        ('show','-s','--format=%P',fifth):fourth,
        ('show','-s','--format=%B',fifth):v.LOCK['transaction_correction_message'],
        ('diff','--name-status','--no-renames',fourth,fifth):'\n'.join('M\t'+p for p in sorted(v.TRANSACTION_PATHS)),
        ('rev-list','--count',base+'..'+fifth):'5',
        ('show','-s','--format=%P',sixth):fifth,
        ('rev-list','--count',base+'..'+sixth):'6',
        ('show','-s','--format=%B',sixth):v.LOCK['uninstall_correction_message'],
        ('diff','--name-status','--no-renames',fifth,sixth):'\n'.join('M\t'+p for p in sorted(v.UNINSTALL_PATHS)),
        ('show','-s','--format=%P',head):sixth,
        ('rev-list','--count',base+'..'+head):'7',
        ('show','-s','--format=%B',head):v.LOCK['harness_correction_message'],
        ('diff','--name-status','--no-renames',sixth,head):'\n'.join('M\t'+p for p in sorted(v.HARNESS_PATHS)),
        ('diff','--name-only',base,head):'\n'.join(sorted(v.CORRECTIVE_PATHS)),
    }
    monkeypatch.setattr(v,'git',lambda repo,*args:answers[args])
    assert v.delivery_identity(APP)=={'head':head,'tree':tree,'parent':sixth}
    invalid=[
        (('show','-s','--format=%P',first),'0'*40),
        (('show','-s','--format=%P',second),base),
        (('show','-s','--format=%P',third),first),
        (('show','-s','--format=%P',head),base),
        (('show','-s','--format=%P',head),second),
        (('show','-s','--format=%P',head),third+' '+base),
        (('show','-s','--format=%P',sixth),fourth),
        (('show','-s','--format=%B',first),'changed A'),
        (('show','-s','--format=%B',second),'changed B'),
        (('show','-s','--format=%B',third),'changed C'),
        (('show','-s','--format=%B',fourth),'changed D'),
        (('show','-s','--format=%P',fourth),base),
        (('show','-s','--format=%P',fifth),third),
        (('show','-s','--format=%B',fifth),'changed E'),
        (('show','-s','--format=%B',sixth),'changed E2'),
        (('show','-s','--format=%B',head),'changed E3'),
        (('status','--porcelain=v1','--untracked-files=all'),' M extra'),
        (('diff','--name-only',base,head),'software/conflict_analysis/domain/models.py'),
    ]
    invalid += [(('rev-list','--count',base+'..'+head),str(n)) for n in (0,1,2,3,4,5,6,8)]
    invalid += [(('rev-list','--count',base+'..'+sixth),str(n)) for n in (0,1,2,3,4,5,7)]
    invalid += [(('rev-list','--count',base+'..'+fifth),str(n)) for n in (0,1,2,3,4,6)]
    invalid += [(('rev-list','--count',base+'..'+fourth),str(n)) for n in (0,1,2,3,5)]
    for parent,child in ((first,second),(second,third),(third,fourth),(fourth,fifth),(fifth,sixth),(sixth,head)):
        key=('diff','--name-status','--no-renames',parent,child)
        invalid.extend([(key,'M\tsoftware/conflict_analysis/domain/models.py'),
                        (key,answers[key].replace('M\t','A\t',1)),
                        (key,'\n'.join(answers[key].splitlines()[:-1]))])
    for key,bad in invalid:
        original=answers[key];answers[key]=bad
        with pytest.raises(v.GateError):v.delivery_identity(APP)
        answers[key]=original

@pytest.mark.parametrize('name',['../escape','C:/escape','a\\b','a/../b','a//b','A.','a /b','cafe\u0301'])
def test_archive_paths_reject_unsafe_names(name):
    assert not v.safe_member(name)

@pytest.mark.parametrize('names',[['a','A'],['../escape'],['unexpected.txt']])
def test_real_zip_verifier_rejects_collision_traversal_extra(tmp_path,names):
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(p,'w') as z:
        for name in names:z.writestr(name,b'x')
    with pytest.raises(v.GateError):v.verify_zip(p)

def test_nsis_payload_only_mode_cannot_install_or_bypass_gate():
    text=(ROOT/'Mvp7Setup.nsi').read_text()
    assert 'RequestExecutionLevel user' in text and 'MUI_LANGUAGE "Russian"' in text
    assert 'WriteRegStr HKLM' not in text and 'RequestExecutionLevel admin' not in text
    assert text.index('verified:')<text.index('install:')
    assert 'Quit' in text[text.index('verified:'):text.index('install:')]
    code=(ROOT/'Install-Mvp7.ps1').read_text()
    assert code.index('Assert-Mvp7Archive')<code.index('if ($VerifyOnly)')<code.index('Assert-Mvp7Host')<code.index('Invoke-Mvp7Installation')
    module=(ROOT/'Mvp7.Setup.psm1').read_text()
    flow=module.split('function Invoke-Mvp7Installation',1)[1].split('function Remove-Mvp7Program',1)[0]
    assert flow.index('Assert-Mvp7DiskCapacity')<flow.index('New-Mvp7PrivateProgram')<flow.index('Expand-Mvp7Archive')
    assert flow.index('Invoke-Mvp7InnerInstall')<flow.index('Complete-OwnerInstallTransaction')<flow.index('Publish-Mvp7Installation')
    assert 'Undo-Mvp7Installation' in flow

def test_runtime_and_installer_have_no_external_download_or_policy_mutation(tmp_path):
    texts=[p.read_text() for p in (APP/'owner_alpha_package/windows').glob('*') if p.suffix in {'.ps1','.psm1'}]
    texts += [p.read_text() for p in ROOT.glob('*.ps*')]
    runtime='\n'.join(texts)
    for token in ['Set-ExecutionPolicy','-ExecutionPolicy Bypass','Unblock-File','Import-Certificate','New-NetFirewallRule','Enable-WindowsOptionalFeature','wsl --install','wsl --update','Invoke-WebRequest','Invoke-RestMethod','Start-BitsTransfer']:
        assert token.casefold() not in runtime.casefold()
    linux=(APP/'owner_alpha_package/linux/owner-alpha-supervisor.sh').read_text()
    for token in ['apt-get','pip install','curl ','wget ']:assert token not in linux
    assert '127.0.0.1' in linux and 'USE_SQLITE="false"' in linux
    config=(APP/'owner_alpha_package/linux/nginx.conf').read_text()
    directives=re.findall(r'^\s*(\w+_temp_path)\s+([^;]+);',config,re.M)
    assert len(directives)==5 and dict(directives)=={
        'client_body_temp_path':'/run/owner-alpha/client','proxy_temp_path':'/run/owner-alpha/proxy',
        'fastcgi_temp_path':'/run/owner-alpha/fastcgi','uwsgi_temp_path':'/run/owner-alpha/uwsgi',
        'scgi_temp_path':'/run/owner-alpha/scgi'}
    code=linux.split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
    module=ast.parse(code)
    functions={node.name:node for node in module.body if isinstance(node,ast.FunctionDef)}
    pg=ast.get_source_segment(code,functions['start_pg'])
    assert pg.index('PGSOCK.mkdir')<pg.index('os.chmod(PGSOCK,0o710)')<pg.index('os.chown(PGSOCK,999,18001)')<pg.index('pgcommand(')
    assert '(999,18001,0o710)' in pg
    start=ast.get_source_segment(code,functions['start_services'])
    assert start.index('directory.mkdir')<start.index('os.chmod(directory,0o700)')<start.index('os.chown(directory,18001,18001)')<start.index('["nginx","-t"')<start.index('["nginx","-c"')
    assert 'user="owneralpha"' in start and '/var/lib/nginx' not in linux
    assert start.index('execute([PACKAGE/"venv/bin/gunicorn"')<start.index('wait_daemon("gunicorn")')
    assert start.index('execute(["nginx","-c"')<start.index('wait_daemon("nginx")')
    _assert_private_daemon_helpers(module,tmp_path)
    harness=ast.parse((APP/'owner_alpha_package/tests/test_linux_contract.py').read_text())
    probes=0
    for node in ast.walk(harness):
        if isinstance(node,ast.List):
            for i,item in enumerate(node.elts):
                if isinstance(item,ast.Constant) and item.value=='/opt/owner-alpha/venv/bin/python':
                    assert [ast.literal_eval(x) for x in node.elts[i-2:i]]==['env','LD_LIBRARY_PATH=/opt/python-libs']
                    probes+=1
    assert probes==8

    assert 'network_check()["tcp_listeners"]==[["127.0.0.1",s["port"]]]' in start

def test_first_install_marker_follows_success_and_uninstall_preserves_state():
    common=(APP/'owner_alpha_package/windows/OwnerAlpha.Common.psm1').read_text()
    install=common[common.index('function New-OwnerInstall'):common.index('function Assert-OwnerInstalled')]
    assert install.index('Assert-OwnerInstallDisk')<install.index('New-OwnerPrivateDirectory')<install.index("'--import'")
    assert install.index('Write-OwnerJson $pending')<install.index("'--import'")
    assert 'Undo-OwnerInstallTransaction' in install
    assert install.index('$result=Invoke-OwnerWsl')<install.index('Write-OwnerJson $Context.stateFile')
    uninstall=(APP/'owner_alpha_package/windows/Uninstall-OwnerAlpha.ps1').read_text()
    assert '--unregister' not in uninstall and 'Remove-Item' not in uninstall
    assert 'Stop-OwnerState' in uninstall

def test_nonclaims_are_literal_and_schema_requires_provenance():
    schema=json.loads((APP/'owner_alpha_package/manifest.schema.json').read_text())
    assert {'source','delivery','acceptance','migration','payload'}<=set(schema['required'])
    assert schema['properties']['source']['properties']['ordinary_commits']['maxItems']==3
    assert schema['properties']['migration']['properties']['path']['const'].endswith('0019_analysis_geography.py')


def _assert_private_daemon_helpers(module,tmp_path):
    """Run the actual embedded helpers; mock kill(0), never signal a Windows process."""
    selected={'Halt','need','read_pid','pid_alive','proc_alive','wait_daemon'}
    nodes=[n for n in module.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in selected]
    kills=[]
    def probe(pid,signal):
        kills.append((pid,signal))
        assert signal==0
        if pid!=42:raise ProcessLookupError()
    safe_os=SimpleNamespace(**{name:getattr(os,name) for name in dir(os)})
    safe_os.kill=probe
    scope={'Path':Path,'os':safe_os,'stat':stat,'re':re}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'exact-supervisor-helpers','exec'),scope)
    path=tmp_path/'daemon.pid'
    assert scope['proc_alive'](path) is False
    for raw in (b'',b'42',b'not-a-pid\n',b'-42\n',b'0\n',b'1\n',b'42x\n',b'42 \n',b'99999999999999999999\n',b'2147483648\n',b'\xff\n'):
        path.write_bytes(raw)
        assert scope['proc_alive'](path) is False
    assert kills==[]
    path.write_bytes(b'43\n');assert scope['proc_alive'](path) is False
    path.write_bytes(b'42\n');assert scope['proc_alive'](path) is True
    path.write_bytes(b'42\n/pg/data\n');assert scope['proc_alive'](path) is True
    assert scope['proc_alive'](tmp_path) is False
    # Partial -> ready and permanently false both use a monotonic bounded deadline.
    class Clock:
        now=0
        def monotonic(self):return self.now
        def sleep(self,value):
            assert 0<value<=.1
            self.now+=value
    clock=Clock();scope['time']=clock
    scope['daemon_ready']=lambda name:clock.now>=.3
    scope['wait_daemon']('gunicorn');assert .3<=clock.now<.5
    clock.now=0;scope['daemon_ready']=lambda name:False
    with pytest.raises(scope['Halt']) as caught:scope['wait_daemon']('nginx')
    assert caught.value.code=='BLOCKED_G10_RUNTIME_OPERATION_FAILED' and clock.now==15
    for timeout in (0,-1,16,60):
        with pytest.raises(scope['Halt']):scope['wait_daemon']('nginx',timeout)
