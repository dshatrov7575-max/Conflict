"""Fetch and verify frozen build inputs; no runtime/installer download path."""
from pathlib import Path
import argparse,hashlib,json,os,urllib.request
ROOT=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--windows-only',action='store_true');args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    lock=json.loads((ROOT/'external-inputs.lock.json').read_text())
    def fetch(pin,name,token=None):
        target=args.output/name
        if not target.exists():
            headers={'Authorization':'Bearer '+token} if token else {}
            if '/manifests/' in pin['url']:
                headers['Accept']='application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'
            request=urllib.request.Request(pin['url'],headers=headers)
            with urllib.request.urlopen(request,timeout=180) as r,target.open('xb') as out:
                while block:=r.read(1024*1024):out.write(block)
        with target.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        assert target.stat().st_size==pin['bytes'] and actual==pin['sha256'],name
    wheels=lock['windows_wheels'] if args.windows_only else lock['wheels']
    for pin in wheels+([] if args.windows_only else lock['debs']):fetch(pin,pin['filename'])
    (args.output/'ci.lock').write_text(''.join(x['name']+'=='+x['version']+' --hash=sha256:'+x['sha256']+'\n' for x in wheels),encoding='utf8')
    if args.windows_only:
        print('FROZEN_WINDOWS_VERIFIER_INPUTS=PASS');return
    for item in lock['oci'].values():
        url='https://auth.docker.io/token?service=registry.docker.io&scope=repository:'+item['repository']+':pull'
        token=json.load(urllib.request.urlopen(url,timeout=60))['token']
        for pin in item['inputs']:fetch(pin,'oci-'+pin['sha256'],token)
    print('ALL_FROZEN_EXTERNAL_LINUX_INPUTS=PASS')
if __name__=='__main__':main()
