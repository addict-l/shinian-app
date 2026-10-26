"""Temporarily recreate only our candidate with an internal upstream fault relay.

Always restore its original env/image/mounts. Production is never touched.
"""
from pathlib import Path
from urllib.parse import urlsplit
import json,subprocess,os,shutil,time,urllib.request
os.umask(0o077)
HERE=Path(__file__).resolve().parent
R=Path('/opt/shinian-releases/story-listening-20261027')
NAME='shinian-story-listening-20261027'
PROXY='shinian-listening-fault-proxy'
def call(*args,**kw):return subprocess.run(list(args),check=True,**kw)
def inspect():return json.loads(subprocess.check_output(['docker','inspect',NAME]))[0]
def ready():
    for i in range(90):
        try:
            data=json.load(urllib.request.urlopen('http://127.0.0.1:18133/health',timeout=2))
            if data.get('database')=='ok':return
        except Exception:pass
        time.sleep(.5)
    raise RuntimeError('candidate not healthy')
def start(env_file,image):
    call('docker','run','-d','--name',NAME,'--memory=384m','--memory-swap=512m','--network','backend_default',
        '--env-file',str(env_file),'-p','127.0.0.1:18133:8000','-v',str(R/'candidate-media')+':/data/media',image,stdout=subprocess.DEVNULL)
    ready()
before=inspect();original=dict(x.split('=',1) for x in before['Config']['Env'])
assert original['INTERVIEW_PIPELINE']=='v3j_v5f'
assert urlsplit(original['DATABASE_URL']).path=='/shinian_story_listening_20261027'
assert before['HostConfig']['PortBindings']['8000/tcp']==[{'HostIp':'127.0.0.1','HostPort':'18133'}]
(R/'fault-original-inspect.json').write_text(json.dumps(before))
F=R/'fault-injection';F.mkdir(exist_ok=True);(F/'records').mkdir(exist_ok=True)
if (F/'records/proxy.jsonl').exists():
    assert not (F/'records/proxy-initial-failed.jsonl').exists()
    (F/'records/proxy.jsonl').rename(F/'records/proxy-initial-failed.jsonl')
shutil.copy2(HERE/'fault_proxy.py',F/'proxy.py')
proxy_env={'UPSTREAM_BASE_URL':original['LLM_BASE_URL']}
(F/'proxy.env').write_text(''.join(k+'='+v+'\n' for k,v in proxy_env.items()))
fault_env=dict(original);fault_env['LLM_BASE_URL']='http://'+PROXY+':18095'+urlsplit(original['LLM_BASE_URL']).path.rstrip('/')
(F/'candidate.env').write_text(''.join(k+'='+v+'\n' for k,v in fault_env.items()))
result={'production_touched':False,'upstream_fault_simulated':True,'judge_and_speaker_real':True}
replaced=False
try:
    call('docker','run','-d','--name',PROXY,'--network','backend_default','--memory=64m','--memory-swap=96m',
        '--env-file',str(F/'proxy.env'),'-v',str(F/'proxy.py')+':/proxy.py:ro',
        '-v',str(R/'source/cloud-deployment/backend/app/ai/interview_runtime_v3j_v5f_listening')+':/prompts:ro',
        '-v',str(F/'records')+':/records','--entrypoint','python',before['Image'],'/proxy.py',stdout=subprocess.DEVNULL)
    for attempt in range(40):
        probe=subprocess.run(['docker','exec',PROXY,'python','-c',
            'import urllib.request;urllib.request.urlopen("http://127.0.0.1:18095/health",timeout=2).read()'],capture_output=True)
        if probe.returncode==0:break
        time.sleep(.5)
    else:raise RuntimeError('fault relay not ready')
    call('docker','stop',NAME,stdout=subprocess.DEVNULL);call('docker','rm',NAME,stdout=subprocess.DEVNULL);replaced=True
    start(F/'candidate.env',before['Image'])
    r=subprocess.run(['python3',str(HERE/'verify_story_https.py'),'--private-dir',str(R/'test-private'),
        '--output-dir',str(R/'real-candidate'),'--forward-port','18453','--cases','FM01:provider_fail_v2'],
        env={**os.environ,'SHINIAN_CLOUD_CANDIDATE':'1'})
    result['harness_exit']=r.returncode
    rows=[json.loads(line) for line in (F/'records/proxy.jsonl').read_text().splitlines()]
    result.update(rows=rows,deepen_requests=sum(x['stage']=='deepen' for x in rows))
    assert r.returncode==0 and result['deepen_requests']==1
finally:
    with (F/'proxy-container.log').open('wb') as log:
        subprocess.run(['docker','logs',PROXY],stdout=log,stderr=subprocess.STDOUT)
    if replaced:
        call('docker','rm','-f',NAME,stdout=subprocess.DEVNULL)
        start(R/'candidate.env',before['Image'])
        after=inspect();result['original_candidate_env_restored']=set(after['Config']['Env'])==set(before['Config']['Env'])
        result['original_image_restored']=after['Image']==before['Image']
        result['mounts_restored']=after['Mounts']==before['Mounts']
    call('docker','rm','-f',PROXY,stdout=subprocess.DEVNULL)
    (R/'fault-validation-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
