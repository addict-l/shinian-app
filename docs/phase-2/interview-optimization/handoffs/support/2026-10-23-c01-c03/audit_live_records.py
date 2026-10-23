"""Independent audit of actual API and family-scoped skeleton provider records."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import argparse
import hashlib
import json

parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--runtime-dir',type=Path,default=Path('/tmp/shinian-question-review-20261023/cloud-deployment/backend/app/ai/interview_runtime_v3j_v4d'));args=parser.parse_args()
directory=Path(args.directory)
runtime=args.runtime_dir
PIN='8897f3c50690d70571e8b8bf2acf2176c80caf17c860ddf6f207c2470a3ba99f'
settings=json.loads((runtime/'provider-settings.json').read_text())
speaker=json.loads((runtime/'speaker-config.json').read_text())
params={'judge':settings['judge'],'verify':settings['verify'],'speaker':speaker['model']}
prompts={stage:(runtime/(stage+'-prompt.txt')).read_text() for stage in params}
failures=[];checks=0;identities={};failed_calls={};seen_wrappers=set();pins=0

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def check(name,ok,where):
 global checks
 checks+=1
 if not ok:failures.append({'check':name,'where':where})

def walk(value,path='',stage=None):
 global pins
 if isinstance(value,dict):
  if value.get('pipeline')=='v3j' and 'runtime_manifest_sha256' in value:
   pins+=1;check('runtime_pin',value['runtime_manifest_sha256']==PIN,path)
  if {'request_sha256','payload','response'}.issubset(value) and isinstance(value['response'],dict):
   row=value['response'];digest=value['request_sha256']
   if row.get('kind')=='model_call' and stage in params:
    actual=row.get('params',params[stage])
    expected=hashlib.sha256(canonical({'runtime':PIN,'stage':stage,'params':actual,'system':prompts[stage],'user':value['payload']}).encode()).hexdigest()
    check('request_digest',digest==expected,path)
    if row.get('ok'):
     identity=row.get('response_id');check('provider_response_id',isinstance(identity,str) and bool(identity),path)
     check('exact_pinned_parameters',actual==params[stage],path)
     check('thinking_disabled_and_no_reasoning_effort',actual.get('thinking')=='disabled' and 'reasoning_effort' not in actual,path)
     check('actual_response_model',row.get('response_model')=='deepseek-v4-pro',path)
     signature=hashlib.sha256(canonical({'stage':stage,'digest':digest,'row':row}).encode()).hexdigest()
     details=(row.get('usage') or {}).get('completion_tokens_details') or {}
     if identity in identities:check('response_id_consistency',identities[identity]['signature']==signature,path)
     else:
      identities[identity]={'stage':stage,'response_id':identity,'request_sha256':digest,'params':actual,'response_model':row.get('response_model'),'reasoning_tokens':details.get('reasoning_tokens'),'signature':signature}
     if details.get('reasoning_tokens') is not None:
      check('reported_reasoning_tokens_zero',details['reasoning_tokens']==0,path)
    else:failed_calls[stage+':'+digest]={'stage':stage,'request_sha256':digest,'error':row.get('error')}
    seen_wrappers.add((stage,digest,row.get('response_id')))
  for key,item in value.items():walk(item,path+'/'+key,key if key in params else stage)
 elif isinstance(value,list):
  for index,item in enumerate(value):walk(item,path+'/'+str(index),stage)

check('local_manifest_pin',hashlib.sha256((runtime/'manifest.json').read_bytes()).hexdigest()==PIN,'runtime')
for path in sorted(directory.glob('*.json')):
 if path.name in ('summary.json','independent-audit.json'):continue
 walk(json.loads(path.read_text()),path.name)
check('live_judge_evidence',any(r['stage']=='judge' for r in identities.values()),'provider_set')
check('live_speaker_evidence',any(r['stage']=='speaker' for r in identities.values()),'provider_set')
report={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'failed_checks':failures,'passed':not failures,
 'unique_successful_provider_responses':len(identities),'stages':dict(Counter(r['stage'] for r in identities.values())),
 'failed_provider_calls':list(failed_calls.values()),'all_provider_calls_successful':not failed_calls,
 'unique_request_response_bindings':len(seen_wrappers),'runtime_pin_occurrences':pins,
 'provider_responses':list(identities.values()),'method':'Recompute request digests from pinned system prompt, persisted user payload and actual parameters; compare response IDs and content across API snapshots and family-scoped MySQL skeleton records',
 'cache_or_holdout_used':False}
(directory/'independent-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='provider_responses'},ensure_ascii=False,indent=2))
raise SystemExit(0 if report['passed'] else 1)
