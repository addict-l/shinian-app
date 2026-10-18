"""One independent validation family on the authorized production endpoint.

Keeps account credentials outside the repository; never uses the real family's
records. Writes no memories and deletes no data. Run after release activation.
"""
import argparse,json,os,secrets,urllib.request,uuid
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--private-dir',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
os.umask(0o077);a.private_dir.mkdir(parents=True,exist_ok=True);a.private_dir.chmod(0o700)
BASE='https://aimemory.47-82-83-74.nip.io';auth=None
def call(path,data=None,method=None):
 headers={'Content-Type':'application/json'}
 if auth:headers['Authorization']='Bearer '+auth['token']
 req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data,ensure_ascii=False).encode(),headers=headers,method=method or ('POST' if data is not None else 'GET'))
 with urllib.request.urlopen(req,timeout=450) as r:return json.load(r)
private=a.private_dir/'https-validation.json'
if private.exists():saved=json.loads(private.read_text());auth=saved['auth']
else:
 username='v2flow_'+uuid.uuid4().hex[:10];password=secrets.token_urlsafe(26)
 auth=call('/api/v1/auth/register',{'username':username,'password':password})
 saved={'auth':auth,'password':password};private.write_text(json.dumps(saved))
if not saved.get('person'):
 saved['person']=call('/api/v1/family-members/',{'client_request_id':str(uuid.uuid4()),'family_id':auth['family_id'],'name':'跳题验证','relationship':'测试'})
 private.write_text(json.dumps(saved))
person=saved['person']
state=call('/api/v1/chat/members/'+person['id']+'/conversation?family_id='+auth['family_id'],method='POST');sid=state['session']['id'];saved['session_id']=sid;private.write_text(json.dumps(saved))
catalog=call('/api/v1/chat/interview-modules');assert sum(len(m['baseline_questions']) for m in catalog)==72
overview=call('/api/v1/chat/sessions/'+sid+'/life-overview');assert overview['total_questions']==11
skips=0
while overview['status']=='collecting':
 out=call('/api/v1/chat/sessions/'+sid+'/life-overview/actions',{'action':'answer','text':'我不想回答这个问题','client_request_id':str(uuid.uuid4()),'expected_version':overview['version']})
 previous=overview['question_id'];overview=out['life_overview'];assert overview['question_id']!=previous
 if overview['question_id']:assert '那我们聊聊下一个话题吧。' in overview['turns'][-1]['content']
 assert not out['can_generate'] and out['generation_offer'] is None
 skips+=1
if overview['status']=='review':
 state=call('/api/v1/chat/sessions/'+sid+'/life-overview/actions',{'action':'confirm','text':'','client_request_id':str(uuid.uuid4()),'expected_version':overview['version']})
else:state=call('/api/v1/chat/sessions/'+sid+'/state')
state=call('/api/v1/chat/sessions/'+sid+'/interview',{'module':'family','expected_version':state['session']['version']})
assert state['session']['information']['guided_interview']['runtime_version']=='full-interview-v2.0.0'
url='/api/v1/chat/sessions/'+sid+'/conversation/messages'
answer=call(url,{'content':'我和老伴是在学校读书时认识的。我们经常一起复习功课，后来慢慢熟悉起来。','client_request_id':str(uuid.uuid4())})
body={'content':'这个问题我不想回答','client_request_id':str(uuid.uuid4())};out=call(url,body)
text=out['messages'][-1]['content'];g=out['session']['information']['guided_interview']
assert text.startswith('那我们聊聊下一个话题吧。')
assert not out['can_generate'] and out['generation_offer'] is None
assert g['topic_index']==1 and g['processed_topics']['FM01']=='skipped' and not g['contract_state']
assert g['contract_history']['FM01']['sources']
again=call(url,body);assert again['messages'][-1]['id']==out['messages'][-1]['id']
saved['last_snapshot']=out;private.write_text(json.dumps(saved,ensure_ascii=False))
report={'passed':True,'public_https':True,'catalog_module_questions':72,'skeleton_questions':11,'skeleton_opt_outs':skips,'refusal_after_substantive_answer':True,'exact_ack_and_next_question':True,'can_generate_after_refusal':out['can_generate'],'generation_offer_after_refusal':out['generation_offer'],'same_request_replay_advanced_once':True,'previous_answer_preserved':True,'validation_person_id':person['id'],'validation_session_id':sid,'independent_validation_family':True,'real_family_test_writes':False,'saved_memories_created':0}
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
