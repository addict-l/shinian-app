from pathlib import Path
from types import SimpleNamespace
import importlib.util,json,subprocess,hashlib
A=Path('/Users/student03/Desktop/shinian-validation/artifacts/session-list-sort-20261023')
P=Path('/Users/student03/Desktop/shinian-validation/private/session-list-sort-20261023/candidate')
s=importlib.util.spec_from_file_location('api','/Users/student03/Desktop/shinian-validation/artifacts/interview-c01-c03-20261023/verify_candidate_https.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
api=m.API(SimpleNamespace(private_dir=str(P),output_dir=str(A),forward_port=28446,legacy_forward_port=None));api.authenticate()
auth=json.loads((P/'auth.json').read_text());auth['purpose']='independent_session_sort_validation';m.save(P/'auth.json',auth)
person=api.operation('history-person','/api/v1/family-members/',{'family_id':api.family,'name':'排序审计隔离人物','relationship':'测试'})
fresh=api.operation('fresh-person','/api/v1/family-members/',{'family_id':api.family,'name':'入口隔离人物','relationship':'测试'})
code=r'''import json,hashlib
from datetime import datetime,timezone,timedelta
from uuid import UUID,uuid5,NAMESPACE_URL
from sqlalchemy import select,text
from sqlalchemy.exc import OperationalError
from app.db.database import SessionLocal,engine
from app.models.chat_session import ChatSessionModel
from app.schemas.story_information import StoryInformation
from app.schemas.guided_interview import GuidedInterviewState
from app.repositories.chat_session_repository import ChatSessionRepository
family=FAMILY;person=PERSON
ids=[str(uuid5(NAMESPACE_URL,f'sort-probe:{family}:{i}')) for i in range(8)]
now=datetime(2026,10,24,tzinfo=timezone.utc)
with SessionLocal.begin() as db:
 for index,identity in enumerate(ids):
  if db.get(ChatSessionModel,identity):continue
  info=StoryInformation(guided_interview=GuidedInterviewState()).model_dump(mode='json')
  info['guided_interview']['contract_state']={'audit':['x'*1048576]}
  db.add(ChatSessionModel(id=identity,family_id=family,primary_person_id=person,title='隔离大段审计',llm_model='test-only',information=info,created_at=now,updated_at=now+timedelta(days=index)))
with SessionLocal() as db:
 size=db.scalar(text('SELECT @@session.sort_buffer_size'))
 try:
  db.scalars(select(ChatSessionModel).where(ChatSessionModel.family_id==family).order_by(ChatSessionModel.updated_at.desc())).all()
  legacy_error=None
 except OperationalError as exc:legacy_error=exc.orig.args[0]
assert legacy_error==1038,('legacy_repro',legacy_error)
rows=ChatSessionRepository().list(UUID(family));seen=[str(r.id) for r in rows]
assert seen[:8]==list(reversed(ids))
assert len(rows)==10
assert all(r.information.guided_interview.contract_state['audit']==['x'*1048576] for r in rows[:8])
assert ChatSessionRepository().list(UUID('00000000-0000-0000-0000-000000000001'))==[]
print(json.dumps({'mysql_sort_buffer_size':size,'legacy_query_error':legacy_error,'new_query_passed':True,'synthetic_large_histories':8,'each_audit_bytes':1048576,'family_sessions':len(rows),'order_content_and_family_filter_passed':True}))
'''.replace('FAMILY',repr(api.family)).replace('PERSON',repr(person['id']))
r=subprocess.run(['ssh','-i','/Users/student03/.ssh/id_ed25519_shinian','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','admin@47.82.83.74','sudo -n docker exec -i shinian-sort-a1ecee6-20261023 python -'],input=code,text=True,capture_output=True,check=True)
proof=json.loads(r.stdout)
rows=api.send('/api/v1/chat/sessions');assert len(rows)==10
assert all(row['family_id']==api.family for row in rows)
state=api.operation('open-conversation','/api/v1/chat/members/'+fresh['id']+'/conversation?family_id='+api.family,method='POST')
assert state['life_overview']['question_id']=='SK01'
assert state['life_overview']['status']=='collecting'
proof.update(https_session_list_passed=True,https_person_conversation_passed=True,api_session_count=len(rows),passed=True,production_data_writes=False,provider_calls=0)
(A/'candidate-sort-verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
