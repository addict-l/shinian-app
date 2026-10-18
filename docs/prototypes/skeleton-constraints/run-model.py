#!/usr/bin/env python3
"""THROWAWAY actual-model transport; credentials remain in existing isolated container."""
import argparse,base64,json,shlex,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REMOTE=r'''
import base64,concurrent.futures,json,os,sys,time,threading,urllib.request
job=json.load(sys.stdin)
encoded=os.environ.get('LLM_API_KEY_B64')
key=base64.b64decode(encoded).decode() if encoded else os.environ.get('LLM_API_KEY','')
base=os.environ.get('LLM_BASE_URL','').rstrip('/')
model=os.environ.get('LLM_TURN_MODEL') or os.environ.get('LLM_MODEL')
emit_lock=threading.Lock()
def emit(x):
    with emit_lock: print(json.dumps(x,ensure_ascii=False),flush=True)
if not key or base!='https://api.deepseek.com' or model!='deepseek-flash':
    emit({'kind':'configuration_error','model':model,'key_configured':bool(key)});sys.exit(2)
emit({'kind':'run_start','model':model,'jobs':len(job['jobs']),'synthetic_only':job.get('source_kind','synthetic')=='synthetic','source_kind':job.get('source_kind','synthetic'),'database_used':False})
def call(item):
    start=time.monotonic()
    body={'model':model,'messages':[{'role':'system','content':job['prompt']},{'role':'user','content':json.dumps(item['payload'],ensure_ascii=False)}],
          'response_format':{'type':'json_object'},'thinking':{'type':'disabled'},'max_tokens':2400,'temperature':0.2}
    req=urllib.request.Request(base+'/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=45) as response: raw=json.load(response)
        content=raw['choices'][0]['message']['content']
        try: output=json.loads(content);parse_error=False
        except Exception: output=None;parse_error=True
        emit({'kind':'model_call','id':item['id'],'input':item['payload'],'output':output,'raw_content':content,'parse_error':parse_error,
              'seconds':round(time.monotonic()-start,3),'usage':raw.get('usage'),'finish_reason':raw['choices'][0].get('finish_reason')})
    except Exception as e:
        detail=None
        if getattr(e,'code',None)==400:
            try:
                err=json.loads(e.read().decode()).get('error',{})
                detail={k:str(err.get(k,''))[:400].replace(key,'[REDACTED]') for k in ('type','code','message')}
            except Exception: detail={'message':'unparsed_http_400'}
        emit({'kind':'call_error','id':item['id'],'exception':type(e).__name__,'http_status':getattr(e,'code',None),'error_detail':detail,'seconds':round(time.monotonic()-start,3)})
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(call,job['jobs']))
emit({'kind':'run_end'})
'''
def main():
    p=argparse.ArgumentParser();p.add_argument('jobs');p.add_argument('output');p.add_argument('--prompt',default='extractor-prompt-v1.txt');p.add_argument('--source-kind',choices=['synthetic','published_transcript'],default='synthetic');a=p.parse_args()
    job={'prompt':(ROOT/a.prompt).read_text(),'jobs':json.loads(Path(a.jobs).read_text()),'source_kind':a.source_kind}
    encoded=base64.b64encode(REMOTE.encode()).decode()
    inner="exec(__import__('base64').b64decode("+repr(encoded)+"))"
    command='sudo -n docker exec -i shinian-b03-isolated python -c '+shlex.quote(inner)
    cmd=['ssh','-i','/Users/student03/.ssh/id_ed25519_shinian','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','admin@47.82.83.74',command]
    with Path(a.output).open('w') as log:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        proc.stdin.write(json.dumps(job,ensure_ascii=False));proc.stdin.close()
        for line in proc.stdout:
            log.write(line);log.flush()
            try:
                row=json.loads(line)
                if row['kind']=='model_call': print(json.dumps({'id':row['id'],'seconds':row['seconds'],'parse_error':row['parse_error']},ensure_ascii=False),flush=True)
                else: print(json.dumps(row,ensure_ascii=False),flush=True)
            except Exception: print('non_json_transport_output_retained',flush=True)
        code=proc.wait()
        # Never print remote environment or raw error bodies.
        if code: print(json.dumps({'transport_exit':code,'stderr_present':bool(proc.stderr.read())}),flush=True)
    raise SystemExit(code)
if __name__=='__main__': main()
