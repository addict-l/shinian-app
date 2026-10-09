"""Restart only task-owned services and verify durable data plus concurrent local reads."""
import json,subprocess,time,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import httpx
ROOT=Path(__file__).resolve().parents[1]
previous=json.loads((ROOT/'.runtime/logs/real-integration.json').read_text())
client=httpx.Client(base_url='http://127.0.0.1:8000',timeout=10,trust_env=False,follow_redirects=True)
checks=[]
def ready():
    for _ in range(100):
        try:
            r=client.get('/health')
            if r.status_code==200 and r.json()['database']=='ok':return
        except httpx.HTTPError:pass
        time.sleep(.25)
    raise AssertionError('Service did not recover')
def verify(name):
    memory=client.get('/api/v1/memories/'+previous['memory_id'])
    assert memory.status_code==200 and memory.json()['source_session_id']==previous['session_id']
    assert client.get(previous['media_url']).status_code==200
    checks.append(name);print('PASS: '+name,flush=True)
for service in ['api','mysql']:
    subprocess.run([sys.executable,str(ROOT/'scripts/manage_local.py'),'restart',service],check=True)
    ready();verify(service+' restart retains memory and photo')
def read(index):
    path='/health' if index%2==0 else '/api/v1/memories/'+previous['memory_id']
    started=time.monotonic();response=client.get(path)
    assert response.status_code==200
    return time.monotonic()-started
with ThreadPoolExecutor(max_workers=8) as pool:timings=list(pool.map(read,range(120)))
checks.append('120 reads with 8 concurrent workers, zero failures')
print('PASS: '+checks[-1],flush=True)
result={'checks':checks,'requests':len(timings),'failures':0,'max_latency_ms':round(max(timings)*1000,2),'mean_latency_ms':round(sum(timings)/len(timings)*1000,2)}
(ROOT/'.runtime/logs/restart-stability.json').write_text(json.dumps(result,indent=2))
