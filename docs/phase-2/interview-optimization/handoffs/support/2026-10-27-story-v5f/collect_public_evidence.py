"""Whitelist only synthetic test records and non-secret verification metadata."""
from pathlib import Path
import json,sys,tarfile,subprocess
from datetime import datetime,timezone
R=Path('/opt/shinian-releases/story-v5f-20013ab-20261026')
original=json.loads((R/'before-inspect.json').read_text())
actual=json.loads(subprocess.check_output(['docker','inspect','backend-api-1']))[0]
e=dict(x.split('=',1) for x in actual['Config']['Env'])
state={'checked_at':datetime.now(timezone.utc).isoformat(),'production_switched':False,'image':actual['Image'],
    'revision':actual['Config']['Labels'].get('org.opencontainers.image.revision'),'pipeline':e['INTERVIEW_PIPELINE'],
    'v4d_pin':e['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'],
    'image_unchanged':actual['Image']==original['Image'],
    'environment_unchanged':set(actual['Config']['Env'])==set(original['Config']['Env']),
    'mounts_unchanged':actual['Mounts']==original['Mounts'],'v5f_config_enabled':e['INTERVIEW_PIPELINE']=='v3j_v5f'}
assert state['image_unchanged'] and state['environment_unchanged'] and state['mounts_unchanged'] and not state['v5f_config_enabled']
(R/'production-unchanged.json').write_text(json.dumps(state,indent=2))
pending_code='''import json
from sqlalchemy import text
from app.db.database import engine
out={'life_pending':0,'guided_pending':0,'speaker_saved':0,'deepen_saved':0}
def count(p,k):
 if p:
  out[k]+=1
  for stage in ('speaker','deepen'):
   if (p.get('calls') or {}).get(stage):out[stage+'_saved']+=1
with engine.connect() as c:
 for raw, in c.execute(text('SELECT life_interview FROM family_members WHERE life_interview IS NOT NULL')):
  x=(json.loads(raw) if isinstance(raw,str) else raw) or {};count(x.get('pending'),'life_pending')
 for raw, in c.execute(text('SELECT information FROM chat_sessions WHERE information IS NOT NULL')):
  x=(json.loads(raw) if isinstance(raw,str) else raw) or {}
  g=x.get('guided_interview') or {};count((g.get('contract_state') or {}).get('pending'),'guided_pending')
print(json.dumps(out))'''
pending=json.loads(subprocess.check_output(['docker','exec','backend-api-1','python','-c',pending_code]))
(R/'production-readonly-pending.json').write_text(json.dumps(pending,indent=2))
failed=R/'test-private/operations/v5f_FM01_provider_fail/answer-0.json'
if failed.exists():
    x=json.loads(failed.read_text())
    safe={k:x[k] for k in ('path','method','request','last_error','errors') if k in x}
    (R/'real-candidate/fault-initial-failed-operation.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2))
fixed=['candidate-unittest.log','candidate-unittest-complete.log','candidate-unittest-overlay-mount-failed.log',
 'unittest-result.json','unittest-complete-result.json','validation-overlay-manifest.json',
 'prepared.json','source-manifest.json','production-unchanged.json','production-readonly-pending.json',
 'fault-validation-startup-failed.json','fault-validation-result.json']
files=[R/x for x in fixed]+list((R/'real-candidate').glob('*.json'))
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
    for p in files:
        assert p.is_file() and not p.is_symlink()
        archive.add(p,arcname=str(p.relative_to(R)),recursive=False)
