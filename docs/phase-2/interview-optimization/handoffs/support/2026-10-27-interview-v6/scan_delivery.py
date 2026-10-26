"""Scan this synthetic evidence bundle, including nested source tar, against actual secrets."""
from pathlib import Path
from urllib.parse import quote
import argparse, hashlib, io, json, re, subprocess, tarfile, zipfile
p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--sha256',required=True);a=p.parse_args()
r=Path('/opt/shinian-releases/story-listening-20261027');z=Path(a.archive)
assert hashlib.sha256(z.read_bytes()).hexdigest()==a.sha256
values=set()
def collect(x):
    if isinstance(x,dict):
        for k,v in x.items():
            if re.search('key|secret|token|password',k,re.I) and isinstance(v,str) and len(v)>=8:
                values.add(v);values.add(quote(v,safe=''))
            collect(v)
    elif isinstance(x,list):
        for v in x:collect(v)
for name in ['backend-api-1','backend-db-1','shinian-story-listening-20261027']:
    x=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
    collect(dict(v.split('=',1) for v in x['Config']['Env']))
    for m in x['Mounts']:
        if 'oss' not in m['Destination']:continue
        source=Path(m['Source'])
        for f in ([source] if source.is_file() else source.glob('*.json')):
            try:collect(json.loads(f.read_text()))
            except (ValueError,OSError):pass
for d in ['test-private','actor-private','supplement-private']:
    f=r/d/'auth.json'
    if f.exists():collect(json.loads(f.read_text()))
leaks=[];scanned=0
def scan(data,name):
    global scanned
    scanned+=1
    if any(v.encode() in data for v in values):leaks.append(name)
    if name.endswith('.tar.gz'):
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
            for member in archive.getmembers():
                assert member.isfile() and member.size<25_000_000
                scan(archive.extractfile(member).read(),name+'!'+member.name)
with zipfile.ZipFile(z) as archive:
    assert archive.testzip() is None
    for item in archive.infolist():scan(archive.read(item),item.filename)
result={'archive_sha256':a.sha256,'zip_integrity':True,'files_scanned_including_nested_source':scanned,
        'actual_secret_values_checked':len(values),'files_containing_actual_secret':leaks,'passed':not leaks}
(r/'delivery-security-scan.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
assert not leaks
