"""NSIS build/embedded payload proof only; never Windows 11 E2E."""
from pathlib import Path, PurePosixPath
import argparse,hashlib,json,os,shutil,struct,subprocess,sys,urllib.request,zipfile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'scripts'))
from verify_owner_alpha_package import verify_zip,identity,canonical,safe_member
LOCK=json.loads((ROOT/'external-inputs.lock.json').read_text())
def checked(args,**kw): return subprocess.run([str(a) for a in args],check=True,**kw)

def run_direct_verify(pwsh, script, inner, expected_sha256, expected_bytes, runtime_root, runtime_manifest):
    result=subprocess.run([str(pwsh),'-NoLogo','-NoProfile','-NonInteractive','-File',str(script),
                           '-Zip',str(inner),'-Sha256',expected_sha256,'-Bytes',str(expected_bytes),
                           '-RuntimeRoot',str(runtime_root),'-RuntimeManifest',str(runtime_manifest),'-VerifyOnly'],
                          capture_output=True,text=True,timeout=600)
    proof={'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    if result.returncode:
        print(json.dumps({'direct_private_runtime_verify':proof},ensure_ascii=False,indent=2),file=sys.stderr)
        raise RuntimeError('Bundled private runtime VerifyOnly failed')
    return proof

def run_setup_verify(target, extracted):
    result=subprocess.run([str(target),'/S','/VERIFYONLY','/PAYLOADOUT='+str(extracted.resolve())],
                          capture_output=True,text=True,timeout=600)
    error_file=extracted/'verify-error.txt'
    proof={'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
           'verify_error_present':error_file.exists(),
           'verify_error':error_file.read_text(encoding='utf-8',errors='replace') if error_file.exists() else ''}
    if result.returncode:
        print(json.dumps({'nsis_verifyonly':proof},ensure_ascii=False,indent=2),file=sys.stderr)
        raise RuntimeError('NSIS VerifyOnly failed')
    assert not error_file.exists(), 'verify-error.txt must not exist after successful VerifyOnly'
    return proof
def pe_fields(path):
    raw=path.read_bytes();offset=struct.unpack_from('<I',raw,0x3c)[0]
    assert raw[offset:offset+4]==b'PE\0\0'
    return {'coff_timestamp':struct.unpack_from('<I',raw,offset+8)[0],
            'optional_checksum':struct.unpack_from('<I',raw,offset+24+64)[0]}
def fetch_pin(pin, target):
    with urllib.request.urlopen(pin['url'],timeout=240) as r,target.open('xb') as out:
        shutil.copyfileobj(r,out)
    observed=identity(target)
    assert observed=={k:pin[k] for k in ['filename','bytes','sha256']},observed
    return observed
def safe_zip_name(name):
    clean=name.rstrip('/')
    return bool(clean) and safe_member(clean)
def safe_extract_zip(archive_path, destination):
    destination.mkdir(parents=True,exist_ok=False)
    seen=set()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            name=info.filename.rstrip('/')
            assert safe_zip_name(info.filename),info.filename
            key=name.casefold()
            assert key not in seen,name
            seen.add(key)
            mode=(info.external_attr>>16)&0o170000
            assert not (info.flag_bits & 1) and mode not in (0o120000,0o160000,0o140000),name
            target=(destination/PurePosixPath(name)).resolve()
            assert target.is_relative_to(destination.resolve()),name
            if info.is_dir():
                target.mkdir(parents=True,exist_ok=True)
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(info) as source,target.open('xb') as out:
                shutil.copyfileobj(source,out)
    return destination
def runtime_manifest(runtime_root, archive_identity, observed):
    entries=[];expanded=0
    for path in sorted(p for p in runtime_root.rglob('*') if p.is_file()):
        rel=path.relative_to(runtime_root).as_posix()
        assert safe_member(rel),rel
        meta={'relative_path':rel,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        entries.append(meta);expanded+=meta['bytes']
    names=[x['relative_path'].casefold() for x in entries]
    assert len(names)==len(set(names))
    entrypoint=next(x for x in entries if x['relative_path']=='pwsh.exe')
    lower={x['relative_path'].casefold() for x in entries}
    assert any('license' in x for x in lower) and any('third' in x and 'notice' in x for x in lower)
    return {'schema':'MVP7_POWERSHELL_RUNTIME_MANIFEST_V1','archive':archive_identity,
            'file_count':len(entries),'expanded_bytes':expanded,'entrypoint':entrypoint,
            'observed_version':observed,'files':entries}
def prepare_powershell_runtime(output):
    pin=LOCK['powershell'];archive=output/pin['filename']
    archive_identity=fetch_pin(pin,archive)
    archive_record={**archive_identity,'version':pin['version']}
    runtime=safe_extract_zip(archive,output/'powershell-runtime')
    pwsh=runtime/'pwsh.exe'
    assert pwsh.is_file()
    command="[pscustomobject]@{PSEdition=$PSVersionTable.PSEdition;PSVersion=$PSVersionTable.PSVersion.ToString();Architecture=[Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()} | ConvertTo-Json -Compress"
    observed=json.loads(subprocess.check_output([str(pwsh),'-NoLogo','-NoProfile','-NonInteractive','-Command',command],text=True))
    assert observed=={'PSEdition':'Core','PSVersion':pin['version'],'Architecture':'X64'},observed
    manifest=runtime_manifest(runtime,archive_record,observed)
    assert manifest['entrypoint']['bytes']==pwsh.stat().st_size
    assert manifest['entrypoint']['sha256']==hashlib.sha256(pwsh.read_bytes()).hexdigest()
    (output/'runtime-manifest.json').write_bytes(canonical(manifest))
    return runtime,manifest

def main():
    p=argparse.ArgumentParser();p.add_argument('--inner',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    assert os.name=='nt','Windows build environment required'
    result=verify_zip(args.inner);inner=identity(args.inner)
    args.output.mkdir(parents=True,exist_ok=False)
    pin=LOCK['nsis'];archive=args.output/pin['filename']
    nsis_archive=fetch_pin(pin,archive)
    tools=args.output/'compiler'
    safe_extract_zip(archive,tools)
    compiler=tools/pin['compiler_path']
    assert compiler.stat().st_size==pin['compiler_bytes'] and identity(compiler)['sha256']==pin['compiler_sha256']
    env={**os.environ,'NSISDIR':str(tools/'nsis-3.12')}
    version=subprocess.check_output([str(compiler),'/VERSION'],env=env,text=True).strip()
    assert version=='v3.12',version
    runtime_root,runtime=prepare_powershell_runtime(args.output)
    build=args.output/'script';build.mkdir()
    for name in ['Mvp7Setup.nsi','Mvp7.Setup.psm1','Install-Mvp7.ps1','Launch-Mvp7.ps1','Uninstall-Mvp7.ps1']:
        shutil.copyfile(ROOT/name,build/name)
    shutil.copyfile(args.output/'runtime-manifest.json',build/'runtime-manifest.json')
    shutil.copytree(runtime_root,build/'pwsh')
    direct_verify=run_direct_verify(build/'pwsh/pwsh.exe',build/'Install-Mvp7.ps1',args.inner,inner['sha256'],inner['bytes'],build/'pwsh',build/'runtime-manifest.json')
    def nsi(value):
        text=str(value);assert not any(c in text for c in ['"','$','\n','\r']),text
        return text
    include=f'!define INNER_ZIP "{nsi(args.inner.resolve())}"\n!define INNER_SHA256 "{inner["sha256"]}"\n!define INNER_BYTES "{inner["bytes"]}"\n'
    (build/'payload.nsh').write_text(include,encoding='utf8')
    binaries=[]
    for name in ['ConflictPartnerDemo_MVP7_Setup.exe','repeat-ConflictPartnerDemo_MVP7_Setup.exe']:
        target=args.output/name
        checked([compiler,'/V2','/NOCONFIG','/INPUTCHARSET','UTF8','/DOUTPUT_EXE='+str(target.resolve()),str(build/'Mvp7Setup.nsi')],cwd=build,env=env)
        assert target.is_file()
        extracted=args.output/('embedded-'+str(len(binaries)));extracted.mkdir()
        # This mode only verifies/extracts embedded ZIP into the requested folder.
        # It never installs, imports WSL, registers shortcuts or bypasses host gates.
        verify_proof=run_setup_verify(target,extracted)
        embedded=extracted/'inner.zip'
        assert embedded.stat().st_size==inner['bytes'] and identity(embedded)['sha256']==inner['sha256']
        verify_zip(embedded,expected_sha256=inner['sha256'],expected_bytes=inner['bytes'])
        binaries.append({'path':target,'verify':verify_proof})
    binary_paths=[x['path'] for x in binaries]
    same=binary_paths[0].read_bytes()==binary_paths[1].read_bytes()
    report={'SETUP_BUILD':'PASS','INNER_ZIP_VERIFY':'PASS','WINDOWS11_WSL2_E2E':'NOT_EXECUTED',
            'CLEAN_PC_SMOKE':'NOT_EXECUTED','PARTNER_RELEASE_READY':False,
            'host_powershell_required':False,'powershell_system_install':False,
            'powershell_path_mutation':False,'powershell_network_install':False,
            'private_runtime_shortcuts':True,'private_runtime_uninstall_bootstrap':True,
            'setup':identity(binary_paths[0]),'inner':inner,'source':result['manifest']['source'],
            'compiler':{**pin,'archive':nsis_archive,'observed_version':version},
            'direct_private_runtime_verify':direct_verify,
            'nsis_verifyonly':[x['verify'] for x in binaries],
            'bundled_runtime':{'version':LOCK['powershell']['version'],'archive':runtime['archive'],
                'expanded_bytes':runtime['expanded_bytes'],'file_count':runtime['file_count'],
                'entrypoint':runtime['entrypoint'],'observed_version':runtime['observed_version']},
            'delivery':result['manifest']['delivery'],
            'disk_capacity_policy':{'program_reserve_bytes':512*1024**2,'state_reserve_bytes':1024**3,
                'program_formula':'actual ZIP bytes + expanded archive bytes + private PowerShell runtime bytes + controller bytes + bootstrap bytes + reserve',
                'state_formula':'2 * manifest rootfs bytes + reserve','same_volume':'sum program and state requirements',
                'zero_mutations_before_preflight':True},
            'transaction_contract':'MVP7_INSTALL_TRANSACTION_V1',
            'superseded_setup_sha256':'1b2893a727887bb3e0a76e4e4ad16810e8d6ba81e4c556cf07662f28af9bfa1a',
            'script_sources':{p.name:identity(p) for p in sorted(build.iterdir()) if p.is_file()},
            'repeat':identity(binary_paths[1]),'byte_identical_exe':same,
            'pe_fields':[pe_fields(p) for p in binary_paths],
            'embedded_payload_identity_proven':True}
    if not same:
        a,b=(p.read_bytes() for p in binary_paths)
        ranges=[];start=None
        for i in range(max(len(a),len(b))):
            unequal=a[i:i+1]!=b[i:i+1]
            if unequal and start is None:start=i
            if not unequal and start is not None:ranges.append([start,i]);start=None
        if start is not None:ranges.append([start,max(len(a),len(b))])
        report['differing_byte_ranges']=ranges
    (args.output/'setup-build-report.json').write_bytes(canonical(report))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
