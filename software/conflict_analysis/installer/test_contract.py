"""Packaging-only checks; none are Windows 11 E2E."""
from pathlib import Path
import ast,copy,hashlib,json,re,subprocess,sys,zipfile
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
    head='b'*40;tree='c'*40
    answers={
        ('rev-parse','HEAD'):head, ('rev-parse','HEAD^{tree}'):tree,
        ('branch','--show-current'):v.LOCK['installer_branch'],
        ('show','-s','--format=%P',first):base,
        ('show','-s','--format=%B',first):v.LOCK['installer_message'],
        ('status','--porcelain=v1','--untracked-files=all'):'',
        ('show','-s','--format=%P',head):first,
        ('rev-list','--count',base+'..'+head):'2',
        ('show','-s','--format=%B',head):v.LOCK['correction_message'],
        ('diff','--name-status','--no-renames',first,head):'\n'.join('M\t'+p for p in sorted(v.CORRECTIVE_PATHS)),
        ('diff','--name-only',base,head):'\n'.join(sorted(v.CORRECTIVE_PATHS)),
    }
    monkeypatch.setattr(v,'git',lambda repo,*args:answers[args])
    assert v.delivery_identity(APP)=={'head':head,'tree':tree,'parent':first}
    for key,bad in [
        (('show','-s','--format=%P',first),'0'*40),
        (('show','-s','--format=%P',head),base),
        (('show','-s','--format=%P',head),first+' '+base),
        (('show','-s','--format=%B',first),'changed A'),
        (('show','-s','--format=%B',head),'changed B'),
        (('rev-list','--count',base+'..'+head),'1'),
        (('rev-list','--count',base+'..'+head),'3'),
        (('status','--porcelain=v1','--untracked-files=all'),' M extra'),
        (('diff','--name-status','--no-renames',first,head),'M\tsoftware/conflict_analysis/domain/models.py'),
        (('diff','--name-status','--no-renames',first,head),answers[('diff','--name-status','--no-renames',first,head)].replace('M\t','A\t',1)),
        (('diff','--name-only',base,head),'software/conflict_analysis/domain/models.py'),
    ]:
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
    assert code.index('Assert-Mvp7Archive')<code.index('if ($VerifyOnly)')<code.index('Assert-Mvp7Host')<code.index('Expand-Mvp7Archive')
    assert code.index('Install-OwnerAlpha.ps1')<code.index("'mvp7-installation.json.pending'")

def test_runtime_and_installer_have_no_external_download_or_policy_mutation():
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
    assert '(RUN/"gunicorn.sock").is_socket()' in start
    assert 'network_check()["tcp_listeners"]==[["127.0.0.1",s["port"]]]' in start

def test_first_install_marker_follows_success_and_uninstall_preserves_state():
    common=(APP/'owner_alpha_package/windows/OwnerAlpha.Common.psm1').read_text()
    install=common[common.index('function New-OwnerInstall'):common.index('function Assert-OwnerInstalled')]
    assert install.index('New-OwnerPrivateDirectory')<install.index('installation.pending.json')<install.index("'--import'")
    assert install.index('$result=Invoke-OwnerWsl')<install.index('Write-OwnerJson $Context.stateFile')
    uninstall=(APP/'owner_alpha_package/windows/Uninstall-OwnerAlpha.ps1').read_text()
    assert '--unregister' not in uninstall and 'Remove-Item' not in uninstall
    assert 'Stop-OwnerState' in uninstall

def test_nonclaims_are_literal_and_schema_requires_provenance():
    schema=json.loads((APP/'owner_alpha_package/manifest.schema.json').read_text())
    assert {'source','delivery','acceptance','migration','payload'}<=set(schema['required'])
    assert schema['properties']['source']['properties']['ordinary_commits']['maxItems']==3
    assert schema['properties']['migration']['properties']['path']['const'].endswith('0019_analysis_geography.py')
