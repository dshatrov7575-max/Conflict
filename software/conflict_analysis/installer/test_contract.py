"""Packaging-only checks; none are Windows 11 E2E."""
from pathlib import Path
import ast,copy,hashlib,json,subprocess,sys,zipfile
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

def test_product_source_and_allowlist_are_bounded():
    assert v.LOCK['source']['head']=='85a253126bf270664c4786d159994e7359b5d2c5'
    assert v.LOCK['source']['tree']=='5567183dbe16fc6c7c8caac051b7694f37b92457'
    assert v.CONTROL['migration']=='domain/migrations/0019_analysis_geography.py'
    for p in ['domain/models.py','production_studio/browser_tests/audited_authoring.mjs','production_studio/browser_tests/cdp_client.mjs','analysis_dashboard/views.py','domain/migrations/0019_analysis_geography.py']:
        assert not v.allowed_installer_path('software/conflict_analysis/'+p)
    assert v.allowed_installer_path('software/conflict_analysis/installer/build_setup.py')

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
