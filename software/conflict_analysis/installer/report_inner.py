from pathlib import Path
import argparse,json,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'scripts'))
import build_owner_alpha_package as b
import verify_owner_alpha_package as v
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
z=args.output/b.ZIP_NAME;result=v.verify_zip(z);cases=ET.parse(args.output/'linux-contract.xml')
assert not cases.findall('.//failure') and not cases.findall('.//error') and not cases.findall('.//skipped')
assert len(cases.findall('.//testcase'))==28
report={'LINUX_BUILD':'PASS','INNER_ZIP_VERIFY':'PASS','PORTABLE_CONTRACT_COUNT':28,
        'source':result['manifest']['source'],'delivery':result['manifest']['delivery'],
        'inner':v.identity(z),'repeat_inner':v.identity(args.output/('repeat-'+b.ZIP_NAME)),
        'wheel':result['manifest']['wheel'],'WINDOWS11_WSL2_E2E':'BLOCKED_NO_RUNNER',
        'CLEAN_PC_SMOKE':'NOT_EXECUTED','PARTNER_RELEASE_READY':False}
assert report['inner']['sha256']==report['repeat_inner']['sha256']
(args.output/'inner-build-report.json').write_bytes(v.canonical(report))
print(json.dumps(report,indent=2))
