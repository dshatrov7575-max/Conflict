"""NSIS build/embedded payload proof only; never Windows 11 E2E."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,struct,subprocess,sys,urllib.request,zipfile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'scripts'))
from verify_owner_alpha_package import verify_zip,identity,canonical,safe_member
LOCK=json.loads((ROOT/'external-inputs.lock.json').read_text())
def checked(args,**kw): return subprocess.run([str(a) for a in args],check=True,**kw)
def pe_fields(path):
    raw=path.read_bytes();offset=struct.unpack_from('<I',raw,0x3c)[0]
    assert raw[offset:offset+4]==b'PE\0\0'
    return {'coff_timestamp':struct.unpack_from('<I',raw,offset+8)[0],
            'optional_checksum':struct.unpack_from('<I',raw,offset+24+64)[0]}
def main():
    p=argparse.ArgumentParser();p.add_argument('--inner',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    assert os.name=='nt','Windows build environment required'
    result=verify_zip(args.inner);inner=identity(args.inner)
    args.output.mkdir(parents=True,exist_ok=False)
    pin=LOCK['nsis'];archive=args.output/pin['filename']
    with urllib.request.urlopen(pin['url'],timeout=180) as r,archive.open('xb') as out:shutil.copyfileobj(r,out)
    assert identity(archive)=={k:pin[k] for k in ['filename','bytes','sha256']}
    tools=args.output/'compiler'
    with zipfile.ZipFile(archive) as z:
        assert all(safe_member(n.rstrip('/')) for n in z.namelist())
        z.extractall(tools)
    compiler=tools/pin['compiler_path']
    assert compiler.stat().st_size==pin['compiler_bytes'] and identity(compiler)['sha256']==pin['compiler_sha256']
    env={**os.environ,'NSISDIR':str(tools/'nsis-3.12')}
    version=subprocess.check_output([str(compiler),'/VERSION'],env=env,text=True).strip()
    assert version=='v3.12',version
    build=args.output/'script';build.mkdir()
    for name in ['Mvp7Setup.nsi','Mvp7.Setup.psm1','Install-Mvp7.ps1','Launch-Mvp7.ps1','Uninstall-Mvp7.ps1']:shutil.copyfile(ROOT/name,build/name)
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
        checked([target,'/S','/VERIFYONLY','/PAYLOADOUT='+str(extracted.resolve())],timeout=600)
        embedded=extracted/'inner.zip'
        assert embedded.stat().st_size==inner['bytes'] and identity(embedded)['sha256']==inner['sha256']
        verify_zip(embedded,expected_sha256=inner['sha256'],expected_bytes=inner['bytes'])
        binaries.append(target)
    same=binaries[0].read_bytes()==binaries[1].read_bytes()
    report={'SETUP_BUILD':'PASS','INNER_ZIP_VERIFY':'PASS','WINDOWS11_WSL2_E2E':'BLOCKED_NO_RUNNER',
            'CLEAN_PC_SMOKE':'NOT_EXECUTED','PARTNER_RELEASE_READY':False,
            'setup':identity(binaries[0]),'inner':inner,'source':result['manifest']['source'],
            'compiler':{**pin,'observed_version':version},
            'delivery':result['manifest']['delivery'],
            'disk_capacity_policy':{'program_reserve_bytes':512*1024**2,'state_reserve_bytes':1024**3,
                'program_formula':'actual ZIP bytes + expanded archive bytes + controller bytes + bootstrap bytes + reserve',
                'state_formula':'2 * manifest rootfs bytes + reserve','same_volume':'sum program and state requirements',
                'zero_mutations_before_preflight':True},
            'transaction_contract':'MVP7_INSTALL_TRANSACTION_V1',
            'superseded_internal_candidate_sha256':'491f7bdf9946fe8f470b19ddcdfafd877cdb4cc06ce2a616b32d520061e29e92',
            'script_sources':{p.name:identity(p) for p in sorted(build.iterdir())},
            'repeat':identity(binaries[1]),'byte_identical_exe':same,
            'pe_fields':[pe_fields(p) for p in binaries],
            'embedded_payload_identity_proven':True}
    if not same:
        a,b=(p.read_bytes() for p in binaries)
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
