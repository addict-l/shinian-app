"""Check a whitelisted delivery ZIP against actual on-host secret values.

Only boolean/count/file-name results leave the host. Never prints secret values.
"""
from pathlib import Path
from urllib.parse import quote
import argparse,hashlib,json,re,subprocess,zipfile
p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--sha256',required=True)
p.add_argument('--release',default='/opt/shinian-releases/story-v5f-20013ab-20261026');args=p.parse_args()
r=Path(args.release);z=Path(args.archive)
assert hashlib.sha256(z.read_bytes()).hexdigest()==args.sha256
values=set()
def collect(x):
    if isinstance(x,dict):
        for k,v in x.items():
            if re.search('key|secret|token|password',k,re.I) and isinstance(v,str) and len(v)>=8:
                values.add(v);values.add(quote(v,safe=''))
            collect(v)
    elif isinstance(x,list):
        for v in x:collect(v)
for name in ['backend-api-1','backend-db-1']:
    x=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
    collect(dict(v.split('=',1) for v in x['Config']['Env']))
    for m in x['Mounts']:
        if 'oss' not in m['Destination']:continue
        source=Path(m['Source'])
        for f in ([source] if source.is_file() else source.glob('*.json')):
            try:collect(json.loads(f.read_text()))
            except (ValueError,OSError):pass
collect(json.loads((r/'test-private/auth.json').read_text()))
leaks=[]
with zipfile.ZipFile(z) as a:
    assert a.testzip() is None
    for item in a.infolist():
        data=a.read(item)
        if any(v.encode() in data for v in values):leaks.append(item.filename)
    result={'archive_sha256':args.sha256,'zip_integrity':True,'files':len(a.infolist()),
        'actual_secret_values_checked':len(values),'files_containing_actual_secret':leaks,'passed':not leaks}
assert not leaks
(r/'delivery-security-scan.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
