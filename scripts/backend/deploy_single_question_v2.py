"""Protected on-host release operations. No credentials or business rows printed.

Upload reviewed patch to /tmp/shinian-single-question-v2.tar.gz and this script,
then run with sudo python3 SCRIPT prepare|activate. Production activation is
separate from candidate verification. Never restores SQL or deletes volumes.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tarfile, time, urllib.request

os.umask(0o077)
RELEASE=Path('/opt/shinian-releases/interview-single-question-v2-20261018')
CURRENT=Path('/opt/shinian-releases/interview-no-thinking-20261018/production-override.json')
BACKEND=Path('/opt/ai-memories/backend')
PIN='d3bbba726e826e5bc84a038e55457077b9c706682e52f588264d1f0f7bc8a503'
TAG='shinian-api:interview-single-question-v2-20261018'
def run(args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def inspect():return json.loads(subprocess.check_output(['docker','inspect','backend-api-1']))[0]
def health():
    for _ in range(40):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2) as r:d=json.load(r)
            if d.get('database')=='ok':return d
        except Exception:pass
        time.sleep(.5)
    raise RuntimeError('health failed')
def compose(config):return ['docker','compose','--project-name','backend','--env-file','.env.production','-f','docker-compose.demo.yml','-f',str(config),'up','-d','--no-deps','--no-build','api']
def fingerprint():
    code='''import json,hashlib
from sqlalchemy import text
from app.db.database import engine
out={}
with engine.connect() as c:
 for table in ['families','family_members','chat_sessions','chat_messages','memories','media_assets']:
  rows=[dict(r._mapping) for r in c.execute(text('SELECT * FROM '+table))]
  values=sorted(json.dumps(row,sort_keys=True,default=str,ensure_ascii=False) for row in rows)
  out[table]={'count':len(rows),'sha256':hashlib.sha256('\\n'.join(values).encode()).hexdigest()}
print(json.dumps(out))
'''
    return json.loads(subprocess.check_output(['docker','exec','-i','backend-api-1','python','-'],input=code.encode()))
if sys.argv[1]=='prepare':
    assert not RELEASE.exists(),'release already exists; inspect it before resuming'
    RELEASE.mkdir(mode=0o700)
    before=inspect();(RELEASE/'before-image').write_text(before['Image'])
    shutil.copy2(CURRENT,RELEASE/'rollback-override.json')
    shutil.copy2(BACKEND/'.env.production',RELEASE/'env.production.backup')
    # Consistent DB export and recoverable media/source snapshots. Protected
    # files stay on server, never in repository or user-visible command output.
    with (RELEASE/'database.sql').open('wb') as f:
        run(['docker','exec','backend-db-1','sh','-c','exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --no-tablespaces ai_memories'],stdout=f,stderr=subprocess.DEVNULL)
    with (RELEASE/'media.tar.gz').open('wb') as f:
        run(['docker','exec','backend-api-1','tar','-C','/data/media','-czf','-','.'],stdout=f)
    with tarfile.open(RELEASE/'source-before.tar.gz','w:gz') as t:
        for p in sorted((BACKEND/'app').rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:t.add(p,arcname=str(p.relative_to(BACKEND)))
    assert (RELEASE/'database.sql').stat().st_size>0
    with tarfile.open(RELEASE/'media.tar.gz') as t:t.getmembers()
    before_data=fingerprint();(RELEASE/'data-before.json').write_text(json.dumps(before_data))
    patch=RELEASE/'patch';patch.mkdir()
    with tarfile.open('/tmp/shinian-single-question-v2.tar.gz') as t:
        assert all(not m.issym() and not m.islnk() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in t.getmembers())
        t.extractall(patch)
    assert hashlib.sha256((patch/'app/ai/interview_runtime/manifest.json').read_bytes()).hexdigest()==PIN
    run(['docker','tag',before['Image'],'shinian-api:single-question-v2-parent'])
    (patch/'Dockerfile').write_text('FROM shinian-api:single-question-v2-parent\nCOPY app /app/app\nCOPY tests /app/tests\nLABEL shinian.runtime_manifest="'+PIN+'"\n')
    with (RELEASE/'build.log').open('w') as f:run(['docker','build','-t',TAG,str(patch)],stdout=f,stderr=subprocess.STDOUT)
    config=json.loads(CURRENT.read_text());config['services']['api']['image']=TAG
    config['services']['api']['environment']['INTERVIEW_RUNTIME_MANIFEST_SHA256']=PIN
    (RELEASE/'production-override.json').write_text(json.dumps(config))
    env=dict(x.split('=',1) for x in before['Config']['Env']);env['INTERVIEW_RUNTIME_MANIFEST_SHA256']=PIN
    (RELEASE/'runtime.env').write_text(''.join(k+'='+v+'\n' for k,v in env.items()))
    with (RELEASE/'candidate-tests.log').open('w') as f:
        run(['docker','run','--rm','--network','backend_default','--env-file',str(RELEASE/'runtime.env'),'-e','ALLOWED_HOSTS=testserver','--entrypoint','python',TAG,'-m','unittest','discover','-s','tests','-p','test_contract_interview_*.py','-q'],stdout=f,stderr=subprocess.STDOUT)
    smoke='''import json
from app.services.contract_interview_state import runtime,questions
from app.ai.contract_interview import ContractInterviewPipeline
from app.ai.llm_client import LLMClient
r=runtime();assert len(r.questions)==83 and len(questions('skeleton'))==11
assert len(runtime('full-interview-v1.29.1').questions)==62
assert r.settings['thinking']=='disabled' and 'reasoning_effort' not in r.settings
out=ContractInterviewPipeline(r,LLMClient()).run('SK01',[{'id':'smoke-only','question_id':'SK01','speaker':'narrator','question':r.questions['SK01']['main_question'],'text':'我是1984年出生的。'}])
assert out['result']['decision']=='ready',out['result']['errors']
print(json.dumps({'passed':True,'runtime':r.version,'questions':len(r.questions),'skeleton':len(questions('skeleton')),'settings':r.settings,'decision':out['result']['decision'],'persisted_business_data':False}))
'''
    with (RELEASE/'smoke.json').open('w') as f:
        run(['docker','run','--rm','-i','--network','backend_default','--env-file',str(RELEASE/'runtime.env'),'--entrypoint','python',TAG,'-'],input=smoke,text=True,stdout=f,stderr=subprocess.STDOUT)
    print(json.dumps({'prepared':True,'release':str(RELEASE),'smoke':json.loads((RELEASE/'smoke.json').read_text()),'backup_complete':True}),flush=True)
elif sys.argv[1]=='activate':
    assert json.loads((RELEASE/'smoke.json').read_text())['passed']
    before=inspect()
    try:
        run(compose(RELEASE/'production-override.json'),cwd=BACKEND,stdout=subprocess.DEVNULL)
        h=health();after=inspect()
        a=dict(x.split('=',1) for x in after['Config']['Env']);b=dict(x.split('=',1) for x in before['Config']['Env'])
        assert {k:v for k,v in a.items() if k!='INTERVIEW_RUNTIME_MANIFEST_SHA256'}=={k:v for k,v in b.items() if k!='INTERVIEW_RUNTIME_MANIFEST_SHA256'}
        assert a['INTERVIEW_RUNTIME_MANIFEST_SHA256']==PIN
        assert after['Mounts']==before['Mounts'] and after['HostConfig']['PortBindings']==before['HostConfig']['PortBindings']
        after_data=fingerprint();assert after_data==json.loads((RELEASE/'data-before.json').read_text()),'business data changed during release; inspect before proceeding'
        for p in (RELEASE/'patch/app').rglob('*'):
            if p.is_file():
                dest=BACKEND/p.relative_to(RELEASE/'patch');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        result={'passed':True,'release':str(RELEASE),'health':h,'runtime_version':'full-interview-v2.0.0','manifest_sha256':PIN,'image':after['Image'],'ports_volumes_other_environment_preserved':True,'original_business_data_unchanged':True,'business_counts':{k:v['count'] for k,v in after_data.items()},'formal_quality_acceptance':False}
        (RELEASE/'deployment.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    except Exception:
        run(compose(RELEASE/'rollback-override.json'),cwd=BACKEND,stdout=subprocess.DEVNULL);health();raise
else:raise ValueError('prepare or activate required')
