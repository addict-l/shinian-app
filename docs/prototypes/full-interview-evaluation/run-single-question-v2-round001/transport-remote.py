
import base64,concurrent.futures,json,os,sys,time,threading,urllib.request
job=json.load(sys.stdin)
encoded=os.environ.get('LLM_API_KEY_B64')
key=base64.b64decode(encoded).decode() if encoded else os.environ.get('LLM_API_KEY','')
base=os.environ.get('LLM_BASE_URL','').rstrip('/')
configured_model=os.environ.get('LLM_TURN_MODEL') or os.environ.get('LLM_MODEL')
model='deepseek-v4-pro'
emit_lock=threading.Lock()
def emit(x):
    with emit_lock: print(json.dumps(x,ensure_ascii=False),flush=True)
if not key or base!='https://api.deepseek.com' or configured_model!='deepseek-flash':
    emit({'kind':'configuration_error','model':model,'key_configured':bool(key)});sys.exit(2)
emit({'kind':'run_start','provider_settings':{'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'max_tokens': 16384},'model':model,'jobs':len(job['jobs']),'synthetic_only':job.get('source_kind','synthetic')=='synthetic','source_kind':job.get('source_kind','synthetic'),'database_used':False})
def call(item):
    start=time.monotonic()
    body={'model':model,'messages':[{'role':'system','content':job['prompt']},{'role':'user','content':json.dumps(item['payload'],ensure_ascii=False)}],
          'response_format':{'type':'json_object'},'thinking':{'type':'disabled'},'max_tokens':16384}
    req=urllib.request.Request(base+'/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=90) as response: raw=json.load(response)
        content=raw['choices'][0]['message']['content']
        try: output=json.loads(content);parse_error=False
        except Exception: output=None;parse_error=True
        emit({'kind':'model_call','id':item['id'],'input':item['payload'],'output':output,'raw_content':content,'parse_error':parse_error,
              'seconds':round(time.monotonic()-start,3),'usage':raw.get('usage'),'finish_reason':raw['choices'][0].get('finish_reason'),'response_model':raw.get('model'),'provider_settings':{'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'max_tokens': 16384}})
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
