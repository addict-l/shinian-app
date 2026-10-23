"""Actual TLS/API/DeepSeek scenarios for C01-C03, plus stateful regressions.

All inputs are fixed acceptance utterances or verbatim prior synthetic dialogue.
No gold/holdout or response cache is consulted, and no memory is generated/saved.
Secrets stay in private_dir; public records omit registration/login credentials.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from copy import deepcopy
from uuid import uuid4
import argparse
import hashlib
import http.client
import json
import secrets
import socket
import ssl
import threading
import time

HOST='aimemory.47-82-83-74.nip.io'
REVIEW='好，先核对这段草稿，您确认后再保存。'
DRAFT='这段可以先整理成草稿了。您还有什么想补充的吗？'
MORE='您还有别的想补充的吗？'
PIN='8897f3c50690d70571e8b8bf2acf2176c80caf17c860ddf6f207c2470a3ba99f'
ORDER=['SK01','SK01b','SK01c','SK02','SK03','SK03b','SK03c','SK03d','SK04','SK05','SK06']
LOCK=threading.Lock()

def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 temp=path.with_suffix(path.suffix+'.tmp')
 temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)

def log(**value):print(json.dumps(value,ensure_ascii=False),flush=True)

class Connection(http.client.HTTPSConnection):
 def __init__(self,port):
  super().__init__(HOST,443,timeout=660,context=ssl.create_default_context())
  self.forward_port=port
 def connect(self):
  raw=socket.create_connection(('127.0.0.1',self.forward_port),timeout=30) if self.forward_port else socket.create_connection((HOST,443),timeout=30)
  self.sock=self._context.wrap_socket(raw,server_hostname=HOST)
  self.sock.settimeout(self.timeout)

class API:
 def __init__(self,args):
  self.args=args;self.private=Path(args.private_dir);self.output=Path(args.output_dir);self.token=None
  self.private.mkdir(parents=True,exist_ok=True,mode=0o700);self.output.mkdir(parents=True,exist_ok=True,mode=0o700)
 def send(self,path,body=None,method=None,legacy=False,read_timeout=None):
  connection=Connection(self.args.legacy_forward_port if legacy else self.args.forward_port)
  headers={'Accept':'application/json','Content-Type':'application/json','Host':HOST}
  if self.token:headers['Authorization']='Bearer '+self.token
  raw=None if body is None else json.dumps(body,ensure_ascii=False).encode()
  connection.request(method or ('POST' if body is not None else 'GET'),path,body=raw,headers=headers)
  if read_timeout is not None:connection.sock.settimeout(read_timeout)
  try:
   response=connection.getresponse();payload=response.read();value=json.loads(payload) if payload else None
   if response.status>=400:raise RuntimeError('HTTPS_'+str(response.status)+':'+json.dumps(value,ensure_ascii=False))
   return value
  finally:connection.close()
 def operation(self,key,path,body=None,method=None,legacy=False,read_timeout=None):
  location=self.private/'operations'/(key+'.json')
  if location.exists():
   record=json.loads(location.read_text());assert record['path']==path
   if 'response' in record:return record['response']
   body=record['request']
  else:
   record={'path':path,'method':method or ('POST' if body is not None else 'GET'),'request':body,'legacy_setup':legacy}
   save(location,record)
  start=time.monotonic()
  try:
   result=self.send(path,body,method,legacy,read_timeout)
   record.update(response=result,seconds=round(time.monotonic()-start,3))
   save(location,record)
   return result
  except Exception as exc:
   record['last_error']={'type':type(exc).__name__,'message':str(exc),'seconds':round(time.monotonic()-start,3)}
   record.setdefault('errors',[]).append(deepcopy(record['last_error']))
   save(location,record);raise
 def authenticate(self):
  path=self.private/'auth.json'
  if path.exists():record=json.loads(path.read_text())
  else:
   record={'purpose':'independent_C01_C03_validation','credentials':{'username':'c01_'+uuid4().hex[:14],'password':secrets.token_urlsafe(30)}};save(path,record)
  if not record.get('auth'):
   try:record['auth']=self.send('/api/v1/auth/register',record['credentials'])
   except Exception:
    record['auth']=self.send('/api/v1/auth/login',record['credentials'])
   save(path,record)
  self.token=record['auth']['token'];self.family=record['auth']['family_id']
  me=self.send('/api/v1/auth/me');assert me['family_id']==self.family
  return self.send('/health')

def calls(state):
 found={}
 def walk(value,stage=None):
  if isinstance(value,dict):
   if value.get('kind')=='model_call':
    identity=value.get('id') or value.get('response_id')
    if identity:found[identity]={**value,'_stage':stage}
   for key,item in value.items():walk(item,key if key in ('judge','verify','speaker') else stage)
  elif isinstance(value,list):
   for item in value:walk(item,stage)
 walk(state);return found

def guide(state):return state['session']['information']['guided_interview']
def last_reply(state):return next(m['content'] for m in reversed(state['messages']) if m['role']=='assistant' and m.get('type')!='notice')

class Case:
 def __init__(self,api,name,module=None):
  self.api=api;self.name=name;self.module=module;self.checks=[];self.events=[];self.responses=[];self.operations=0
 def op(self,label,path,body=None,method=None,legacy=False,timeout=None):
  result=self.api.operation(self.name+'/'+label,path,body,method,legacy,timeout)
  record=json.loads((self.api.private/'operations'/self.name/(label+'.json')).read_text())
  self.last_request_body=record['request']
  return result
 def check(self,name,condition,details=None):
  self.checks.append({'check':name,'passed':bool(condition),'details':details})
 def setup(self):
  api=self.api;person=self.op('person','/api/v1/family-members/',{'family_id':api.family,'name':self.name,'relationship':'独立验收测试','client_request_id':str(uuid4())})
  state=self.op('conversation','/api/v1/chat/members/'+person['id']+'/conversation?family_id='+api.family,method='POST')
  self.session=state['session']['id'];self.prefix='/api/v1/chat/sessions/'+self.session
  life=self.op('initial-life',self.prefix+'/life-overview')
  if self.module:
   legacy=bool(api.args.legacy_forward_port)
   for index in range(11):
    if life['status']!='collecting':break
    state=self.op('setup-skip-'+str(index),self.prefix+'/life-overview/actions',{'action':'answer','text':'跳过','client_request_id':str(uuid4()),'expected_version':life['version']},legacy=legacy)
    life=state['life_overview']
   assert life['status']=='review'
   state=self.op('setup-confirm',self.prefix+'/life-overview/actions',{'action':'confirm','text':'','client_request_id':str(uuid4()),'expected_version':life['version']},legacy=legacy)
   state=self.op('select-module',self.prefix+'/interview',{'module':self.module,'expected_version':state['session']['version']})
   self.check('module_selected',guide(state)['module']==self.module)
   self.check('overview_setup_done_by_API',state['life_overview']['status']=='confirmed')
   self.setup_method='explicit API skips using same isolated image with v2, then module selects v3j_v4d' if legacy else 'explicit API skips through v3j_v4d'
   self.state=state;self.events.append({'role':'interviewer','text':last_reply(state),'kind':'opening'})
  else:
   self.life=life;self.events.append({'role':'interviewer','text':life['turns'][-1]['content'],'kind':'opening'})
   self.setup_method='fresh skeleton over v3j_v4d HTTPS'
  log(case=self.name,stage='setup_complete')
 def answer(self,text,timeout_retry=False):
  index=self.operations;self.operations+=1
  body={'content':text,'client_request_id':str(uuid4())}
  path=self.prefix+'/conversation/messages'
  if timeout_retry:
   saved=self.api.private/'operations'/self.name/('answer-timeout-'+str(index)+'.json')
   prior=json.loads(saved.read_text()) if saved.exists() else None
   if prior and prior.get('last_error',{}).get('type') in ('TimeoutError','timeout'):
    body=prior['request'];self.check('transport_timeout_exercised',True,'retained original timeout journal')
   else:
    try:
     self.op('answer-timeout-'+str(index),path,body,timeout=.05)
     self.check('transport_timeout_exercised',False,'response arrived before forced read timeout')
    except (TimeoutError,socket.timeout):
     body=json.loads(saved.read_text())['request'];self.check('transport_timeout_exercised',True)
   state=self.op('answer-'+str(index),path,body)
  else:state=self.op('answer-'+str(index),path,body)
  self.state=state;self.responses.append(state)
  self.events.extend([{'role':'respondent','text':text},{'role':'interviewer','text':last_reply(state),'phase':guide(state)['phase'],'generation_offer':state.get('generation_offer') is not None}])
  self.last_body=self.last_request_body
  return state
 def life_answer(self,text,label=None):
  body={'action':'answer','text':text,'client_request_id':str(uuid4()),'expected_version':self.life['version']}
  state=self.op(label or 'life-answer-'+str(self.operations),self.prefix+'/life-overview/actions',body);self.operations+=1
  self.life=state['life_overview'];self.responses.append(state)
  self.events.extend([{'role':'respondent','text':text},{'role':'interviewer','text':self.life['turns'][-1]['content'],'question_id':self.life['question_id'],'paused':self.life['paused']}])
  self.last_body=self.last_request_body;return state
 def finish(self,error=None):
  record={'case':self.name,'module':self.module,'input_method':'fixed acceptance utterances or verbatim prior public-material AI respondent answers; not a live human interview','setup':getattr(self,'setup_method',None),'checks':self.checks,'events':self.events,'responses':self.responses,'error':error,'passed':not error and all(c['passed'] for c in self.checks),'memory_generation_or_save_called':False}
  save(self.api.output/(self.name+'.json'),record);log(case=self.name,passed=record['passed'],checks=len(self.checks),error=error)
  return record

C03={
 'childhood':['小时候听大伯说先祖是‘谋士’，我当成磨刀的石头了，这件事印象很深。','后来我妈把‘谋士’写给我看，我才明白不是磨刀的石头。','这件事我记得的就是这些，没有别的补充了。'],
 'work':['我最初是在糖厂实验室当临时工，后来才看到报纸招考女青年工作大队。','家里弟妹多，初中毕业就没法再读书，得自己谋生活。我看到报纸招考，就和两个同学去高雄报考了。','当时薪水好像每月九十块，另有两百块的工作勤务加勤。那两百块寄回家，九十块留作自己的零用钱。','父母当时很反对，觉得女孩子不该离乡到部队工作。不过有两个同学一起，我们三个人还是北上报到了，做的是文教工作。','没有了，关于最初工作这些事情，我能补充的就是这些。'],
 'family':['我没有成家，从来没考虑过这回事，所以也没有伴侣认识的经历。','也没什么特别原因，我就是好玩，从来不为成家这事伤脑筋。','没有了，关于成家这件事，我能说的就是这些。']}
C01=['那时候下工累了就歇一会儿。','不是累了，我还想接着聊。','她不想说，后来我就没有再问。','我有点累了，想先歇一会儿。']

def execute(case):
 try:
  if case.name in ('C03_childhood','C03_work','C03_family'):
   answers=C03[case.module]
   for index,text in enumerate(answers):
    previous=case.state;phase=guide(previous)['phase'];before=set(calls(previous))
    state=case.answer(text,timeout_retry=case.name=='C03_childhood' and index==0)
    if index==0:case.check('new_module_uses_v3j_v4d',guide(state)['contract_state']['pipeline']=='v3j_v4d')
    if index==len(answers)-1:
     case.check('nothing_more_after_supplement',phase in ('supplement','review'),phase)
     case.check('nothing_more_goes_directly_to_review',guide(state)['phase']=='review',guide(state)['phase'])
     case.check('nothing_more_exact_review_text',last_reply(state)==REVIEW,last_reply(state))
     case.check('nothing_more_no_provider_call',set(calls(state))==before)
     case.check('review_keeps_draft_entry',state.get('generation_offer') is not None)
    elif phase in ('supplement','review'):
     reply=last_reply(state)
     case.check('addition_uses_short_supplement_question_'+str(index),reply.endswith(MORE) and DRAFT not in reply,reply)
     case.check('addition_recorded_with_new_provider_response_'+str(index),bool(set(calls(state))-before))
  elif case.name.startswith('C01_'):
   index=int(case.name.rsplit('_',1)[1]);text=C01[index]
   if case.module:
    state=case.answer(text);g=guide(state);rule=g['contract_state']['audit'][-1].get('speaker') or {}
    case.check('own_current_rest_pauses' if index==3 else 'historical_negated_other_does_not_pause',g['phase']=='paused' if index==3 else g['phase']!='paused',g['phase'])
    if index!=3:case.check('does_not_refuse_or_skip',g['topic_index']==0 and rule.get('reason') not in ('declined','deferred'),rule)
    else:
     state=case.answer('继续');case.check('pause_resumes',guide(state)['phase']!='paused')
   else:
    case.life_answer(text)
    case.check('own_current_rest_pauses' if index==3 else 'historical_negated_other_does_not_pause',case.life['paused'] if index==3 else not case.life['paused'])
    if index!=3:
     field=next(f for f in case.life['fields'] if f['topic_id']=='SK01');case.check('does_not_refuse_or_skip',field['status'] not in ('declined','skipped'),field['status'])
  elif case.name=='C02_partial':
   state=case.answer('我们是在工厂认识的。后来天天一起上下班，慢慢就熟了。这段我不想多讲。')
   g=guide(state);spoken=g['contract_state']['audit'][-1].get('speaker') or {}
   case.check('partial_decline_keeps_draft',state.get('generation_offer') is not None)
   case.check('partial_decline_stops_target_followups',g['phase']=='supplement' and g['pending_question'] is None)
   case.check('partial_decline_classified',spoken.get('reason')=='declined_partial',spoken)
   case.answer('没有了，就这些。');case.check('partial_decline_then_review',guide(case.state)['phase']=='review')
  elif case.name=='C02_empty':
   state=case.answer('这段我不想多讲。');g=guide(state)
   case.check('empty_refusal_skips_question',g['topic_index']==1,g['topic_index'])
   case.check('empty_refusal_has_no_draft',state.get('generation_offer') is None)
  elif case.name=='C03_content_and_end':
   case.answer(C03['childhood'][0]);before=set(calls(case.state))
   state=case.answer('后来我妈把‘谋士’写给我看，我才明白不是磨刀的石头，就这些了。')
   case.check('addition_and_end_goes_review',guide(state)['phase']=='review')
   new={k:v for k,v in calls(state).items() if k not in before}
   case.check('addition_and_end_judged',bool(new))
   case.check('addition_and_end_not_spoken',all(v.get('_stage')!='speaker' for v in new.values()))
  elif case.name=='full_skeleton':
   texts=['我是1956年出生的。','我出生在江苏邳州的城子河后老庄。','我小时候的家乡在江苏邳州乡下，靠近车站，交通方便，家里开着一家小饭店。','我的名字叫秋生，因为我出生在秋天；家里人对这个名字有什么期望，我不想多讲了。']+['跳过']*7
   seen=[]
   for index,text in enumerate(texts):
    seen.append(case.life['question_id']);state=case.life_answer(text)
    if index==0:
     previous=deepcopy(case.life);again=case.op('repeat-first',case.prefix+'/life-overview/actions',case.last_body)
     case.check('skeleton_repeat_idempotent',again['life_overview']==previous)
     for action in ('pause','resume'):
      result=case.op('skeleton-'+action,case.prefix+'/life-overview/actions',{'action':action,'text':'','client_request_id':str(uuid4()),'expected_version':case.life['version']})
      case.life=result['life_overview'];case.check('skeleton_'+action,case.life['paused']==(action=='pause') and case.life['question_id']=='SK01b')
    if case.life['question_id']:
     case.check('spoken_next_matches_'+str(index),case.life['turns'][-1]['content'].endswith(case.life['question']),case.life['turns'][-1]['content'])
    if index==3:
     field=next(f for f in case.life['fields'] if f['topic_id']=='SK02')
     case.check('partial_answer_skeleton_known_with_original_evidence',field['status']=='known' and bool(field['evidence']),field)
   case.check('full_eleven_order',seen==ORDER,seen);case.check('full_skeleton_review',case.life['status']=='review')
   corrected=case.op('correct-year',case.prefix+'/life-overview/actions',{'action':'correct','topic_id':'SK01','text':'我是1957年出生的。','client_request_id':str(uuid4()),'expected_version':case.life['version']})
   case.life=corrected['life_overview'];case.responses.append(corrected)
   case.check('correction_returns_to_review',case.life['status']=='review')
   result=case.op('confirm-review',case.prefix+'/life-overview/actions',{'action':'confirm','text':'','client_request_id':str(uuid4()),'expected_version':case.life['version']})
   case.check('review_confirm',result['life_overview']['status']=='confirmed');case.responses.append(result)
  return case.finish()
 except Exception as exc:return case.finish({'type':type(exc).__name__,'message':str(exc)})

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--private-dir',required=True);parser.add_argument('--output-dir',required=True)
 parser.add_argument('--forward-port',type=int);parser.add_argument('--legacy-forward-port',type=int);parser.add_argument('--postrelease',action='store_true');args=parser.parse_args()
 api=API(args);health=api.authenticate();log(stage='authenticated',health=health)
 cases=[Case(api,'C03_'+module,module) for module in C03]+[Case(api,'C02_partial','family'),Case(api,'C02_empty','family')]
 cases += [Case(api,'C01_module_'+str(i),'family') for i in range(4)]
 if not args.postrelease:cases += [Case(api,'C01_skeleton_'+str(i)) for i in range(4)]+[Case(api,'full_skeleton'),Case(api,'C03_content_and_end','childhood')]
 for case in cases:case.setup()
 results=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  for future in as_completed([pool.submit(execute,case) for case in cases]):results.append(future.result())
 provider={};audit_failures=[]
 for result in results:
  for record in calls(result).values():
   identity=record.get('id') or record.get('response_id');params=record.get('params') or {}
   if params.get('model')!='deepseek-v4-pro' or params.get('thinking')!='disabled' or 'reasoning_effort' in params:audit_failures.append('model_parameter_mismatch')
   provider[identity]={'response_id':identity,'stage':record.get('_stage'),'response_model':record.get('response_model'),'request_sha256':record.get('request_sha256'),'params':params}
 if not provider:audit_failures.append('no_provider_response_evidence')
 summary={'checked_at':datetime.now(timezone.utc).isoformat(),'production':args.postrelease,'candidate_https':not args.postrelease,
  'transport':'public HTTPS' if args.postrelease else 'verified TLS identity over SSH forwarding; separate loopback Nginx',
  'scenarios':len(results),'passed_scenarios':sum(r['passed'] for r in results),'failed_scenarios':[r['case'] for r in results if not r['passed']],
  'checks':sum(len(r['checks']) for r in results),'failed_checks':[{'case':r['case'],**c} for r in results for c in r['checks'] if not c['passed']],
  'errors':[{'case':r['case'],'error':r['error']} for r in results if r['error']],
  'unique_model_responses':len(provider),'model_audit_failures':audit_failures,'all_passed':all(r['passed'] for r in results) and not audit_failures,
  'provider_responses':list(provider.values()),'memory_generation_or_save_called':False,'holdout_used_for_tuning':False}
 save(api.output/'summary.json',summary);log(stage='finished',**{k:v for k,v in summary.items() if k!='provider_responses'})

if __name__=='__main__':main()
