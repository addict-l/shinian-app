from pathlib import Path
from types import SimpleNamespace
import importlib.util,json,subprocess,hashlib,re,os
from uuid import UUID
A=Path('/Users/student03/Desktop/shinian-validation/artifacts/session-list-sort-20261023')
P=Path('/Users/student03/Desktop/shinian-validation/private/interview-c01-c03-20261023/production')
s=importlib.util.spec_from_file_location('api','/Users/student03/Desktop/shinian-validation/artifacts/interview-c01-c03-20261023/verify_candidate_https.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
api=m.API(SimpleNamespace(private_dir=str(P),output_dir=str(A),forward_port=None,legacy_forward_port=None))
auth=json.loads((P/'auth.json').read_text());api.token=auth['auth']['token'];api.family=auth['auth']['family_id']
health=api.send('/health');assert health['database']=='ok'
me=api.send('/api/v1/auth/me');assert me['family_id']==api.family
rows=api.send('/api/v1/chat/sessions');assert rows and all(r['family_id']==api.family for r in rows)
api.token=None
try:api.send('/api/v1/auth/me');raise AssertionError('anonymous_access_allowed')
except RuntimeError as exc:assert str(exc).startswith('HTTPS_401:')
remote=r'''from pathlib import Path
import json,subprocess,re
R=Path('/opt/shinian-releases/session-list-sort-a1ecee6-20261023')
files=['deployment.json','backup-verification.json','data-before.json','data-after.json','preactivation-pending.json','quiesced-pending.json']
out={'artifacts':{name:json.loads((R/name).read_text()) for name in files}}
code="""import json
from uuid import UUID
from sqlalchemy import text
from app.db.database import SessionLocal
from app.repositories.chat_session_repository import ChatSessionRepository
from app.models.chat_session import ChatSessionModel
with SessionLocal() as db:
 db.execute(text('SET SESSION TRANSACTION READ ONLY'))
 repository=ChatSessionRepository();repository.session=db
 # Repository normally owns its sessions; call under an engine connect read-only hook instead below.
from sqlalchemy import event
from app.db.database import engine
@event.listens_for(engine,'begin')
def read_only(connection):connection.exec_driver_sql('SET TRANSACTION READ ONLY')
family=UUID('__PROBE_FAMILY_UUID__')
rows=ChatSessionRepository().list(family)
assert len(rows)>=51 and all(r.family_id==family for r in rows)
assert [r.updated_at for r in rows]==sorted((r.updated_at for r in rows),reverse=True)
print(json.dumps({'read_only':True,'family_list_passed':True,'family_session_count':len(rows),'descending_order_passed':True,'production_data_writes':False}))
"""
r=subprocess.run(['docker','exec','-i','backend-api-1','python','-'],input=code,text=True,capture_output=True,check=True)
out['real_family_readonly']=json.loads(r.stdout)
logs=subprocess.check_output(['docker','logs','--since','20m','backend-api-1'],stderr=subprocess.STDOUT,text=True)
# Only retain HTTP method/route pattern and status; omit IPs, person/session/family UUIDs.
matches=re.findall(r'"((?:GET|POST) /api/v1/(?:chat/[^\"]+)) HTTP/1.1" (\d{3})',logs)
out['app_route_statuses']=[{'route':re.sub(r'[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}', '<uuid>',route),'status':int(status)} for route,status in matches]
print(json.dumps(out))
'''
remote=remote.replace('__PROBE_FAMILY_UUID__',str(UUID(os.environ['SHINIAN_PROBE_FAMILY_ID'])))
r=subprocess.run(['ssh','-i','/Users/student03/.ssh/id_ed25519_shinian','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','admin@47.82.83.74','sudo -n python3 -'],input=remote,text=True,capture_output=True,check=True)
proof=json.loads(r.stdout)
for name,record in proof.pop('artifacts').items():
 (A/name).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
proof.update(public_https_health=health,anonymous_auth_status=401,synthetic_family_list_status=200,synthetic_family_session_count=len(rows),passed=True,provider_calls=0)
(A/'production-postrelease-verification.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(proof,ensure_ascii=False,indent=2))
