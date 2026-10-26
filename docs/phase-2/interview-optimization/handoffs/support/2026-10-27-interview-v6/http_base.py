"""TLS/API capture helpers reused from the C01-C03 validation harness.

Scenario-specific behavior, including draft generation/save, is in StoryCase in
verify_story_https.py. It overrides the legacy setup and capture metadata below.
All elder inputs are synthetic acceptance text; no gold/holdout is consulted.
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

HOST='api.xn--zbs33ddmy9oeqa.club'
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
   record={'purpose':'independent_story_v5f_validation','credentials':{'username':'v5f_'+uuid4().hex[:14],'password':secrets.token_urlsafe(30)}};save(path,record)
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
   for key,item in value.items():walk(item,key if key in ('judge','verify','speaker','deepen') else stage)
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
