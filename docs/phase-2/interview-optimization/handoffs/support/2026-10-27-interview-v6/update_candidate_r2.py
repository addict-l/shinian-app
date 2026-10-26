"""Apply the supplemental-ending fix to this isolated candidate after tests; never production."""
from pathlib import Path
import json, hashlib, subprocess, tarfile, os, time, urllib.request
os.umask(0o077)
R=Path('/opt/shinian-releases/story-listening-20261027');U=R/'update-r2';NAME='shinian-story-listening-20261027'
def run(a,**k):return subprocess.run(a,check=True,**k)
def out(a):return subprocess.check_output(a)
def inspect(n):return json.loads(out(['docker','inspect',n]))[0]
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def stage(s,**k):print(json.dumps({'stage':s,**k}),flush=True)
assert not U.exists();U.mkdir(mode=0o700)
before=inspect(NAME);prod=inspect('backend-api-1')
write(U/'before-candidate-inspect.json',before)
with tarfile.open('/home/admin/shinian-story-listening-20261027-r2.tar.gz') as f:
 assert all(not m.issym() and not m.islnk() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in f.getmembers());f.extractall(U,filter='data')
m=json.loads((U/'source-manifest.json').read_text());source=U/'source'
assert {str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}==set(m['source_sha256'])
for n,h in m['source_sha256'].items():assert hashlib.sha256((source/n).read_bytes()).hexdigest()==h,n
e=dict(x.split('=',1) for x in before['Config']['Env'])
assert e['INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256']==m['v5f_listening_pin'],'prompt/pin changes require separate state migration'
assert e['DATABASE_URL'].split('?')[0].endswith('/shinian_story_listening_20261027')
assert before['HostConfig']['PortBindings']['8000/tcp']==[{'HostIp':'127.0.0.1','HostPort':'18133'}]
manifest_sha=hashlib.sha256((U/'source-manifest.json').read_bytes()).hexdigest()
parent='shinian-api:story-listening-r2-parent'
run(['docker','tag',before['Image'],parent])
(U/'Dockerfile').write_text('FROM '+parent+'\nCOPY source/cloud-deployment/backend/ /app/\nLABEL io.shinian.backend-tree="'+m['backend_content_sha256']+'"\nLABEL io.shinian.source-manifest-sha256="'+manifest_sha+'"\n')
(U/'.dockerignore').write_text('*\n!Dockerfile\n!source\n!source/**\n')
tag='shinian-api:story-listening-20261027-r2'
with (U/'build.log').open('w') as f:run(['docker','build','-t',tag,str(U)],stdout=f,stderr=subprocess.STDOUT)
stage('r2_built')
with (U/'unittest.log').open('w') as f:
 result=subprocess.run(['docker','run','--rm','--network','none','--memory=384m','--memory-swap=512m','--env-file',str(R/'unittest.env'),'-v',str(source)+':/validation:ro','-v',str(R/'replay/interview-eval')+':/evaluation:ro','-w','/validation/cloud-deployment/backend','--entrypoint','python',tag,'-m','unittest','discover','-s','tests','-p','test_*.py','-v'],stdout=f,stderr=subprocess.STDOUT)
write(U/'unittest-result.json',{'exit_code':result.returncode,'network':'none','source_manifest_sha256':manifest_sha});assert result.returncode==0
stage('r2_unittest_passed')
# All test request processes must have finished before invocation. Check own pending state too.
check='''from sqlalchemy import text
from app.db.database import engine
import json
n=0
with engine.connect() as c:
 for raw, in c.execute(text('SELECT information FROM chat_sessions WHERE information IS NOT NULL')):
  x=(json.loads(raw) if isinstance(raw,str) else raw) or {};n+=bool(((x.get('guided_interview') or {}).get('contract_state') or {}).get('pending'))
 for raw, in c.execute(text('SELECT life_interview FROM family_members WHERE life_interview IS NOT NULL')):
  x=(json.loads(raw) if isinstance(raw,str) else raw) or {};n+=bool(x.get('pending'))
assert n==0,n
print(n)'''
assert out(['docker','exec',NAME,'python','-c',check]).strip()==b'0'
run(['docker','stop',NAME],stdout=subprocess.DEVNULL);run(['docker','rm',NAME],stdout=subprocess.DEVNULL)
run(['docker','run','-d','--name',NAME,'--memory=384m','--memory-swap=512m','--network','backend_default','--env-file',str(R/'candidate.env'),'-p','127.0.0.1:18133:8000','-v',str(R/'candidate-media')+':/data/media',tag],stdout=subprocess.DEVNULL)
for _ in range(90):
 try:
  h=json.load(urllib.request.urlopen('http://127.0.0.1:18133/health',timeout=2))
  if h.get('database')=='ok':break
 except Exception:pass
 time.sleep(.5)
else:raise RuntimeError('candidate r2 health failed')
after=inspect(NAME);pa=inspect('backend-api-1')
assert set(before['Config']['Env'])==set(after['Config']['Env']) and before['Mounts']==after['Mounts']
assert prod['Image']==pa['Image'] and prod['Config']['Env']==pa['Config']['Env'] and prod['Mounts']==pa['Mounts']
for name in ('production-override.json','fallback-v4d-override.json'):
 p=R/name;x=json.loads(p.read_text());x['services']['api']['image']=tag;write(p,x)
proof={'candidate_image':after['Image'],'previous_candidate_image':before['Image'],'runtime_pin_unchanged':m['v5f_listening_pin'],'source_manifest_sha256':manifest_sha,'backend_content_sha256':m['backend_content_sha256'],'production_unchanged':True,'candidate_env_mounts_unchanged':True,'unittest_exit_code':0,'change':'C03 negative intent scope only; no prompts/params/schema changes'}
write(U/'updated.json',proof);stage('r2_candidate_ready',**proof)
