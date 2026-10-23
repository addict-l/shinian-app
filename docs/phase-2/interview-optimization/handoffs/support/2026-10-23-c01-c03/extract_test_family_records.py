"""Read only the synthetic family created by verify_candidate_https.py.

Never exports whole production tables, auth state, configuration or real families.
"""
from pathlib import Path
from uuid import UUID
import argparse,json,subprocess,shlex
p=argparse.ArgumentParser();p.add_argument('--private-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--container',required=True);p.add_argument('--ssh-host',default='admin@47.82.83.74');p.add_argument('--ssh-key',default='/Users/student03/.ssh/id_ed25519_shinian');a=p.parse_args()
auth=json.loads((a.private_dir/'auth.json').read_text());assert auth['purpose']=='independent_C01_C03_validation'
family=auth['auth']['family_id'];UUID(family)
expected={json.loads(file.read_text())['response']['id'] for file in (a.private_dir/'operations').glob('*/person.json')}
assert expected and a.container in ('backend-api-1','shinian-c01-c03-ed38ab2-20261023')
code='''import json
from sqlalchemy import text
from app.db.database import engine
with engine.connect() as c:
 rows=c.execute(text('SELECT id,life_interview FROM family_members WHERE family_id=:fid'),{'fid':%r})
 out={row[0]:json.loads(row[1]) if isinstance(row[1],(str,bytes)) else row[1] for row in rows}
 assert set(out)==%r
 print(json.dumps(out,ensure_ascii=False))
'''%(family,expected)
cmd='sudo -n docker exec -i '+shlex.quote(a.container)+' python -'
r=subprocess.run(['ssh','-i',a.ssh_key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',a.ssh_host,cmd],input=code,text=True,capture_output=True,check=True)
values=json.loads(r.stdout);assert set(values)==expected
file=a.output_dir/'server-skeleton-records.json';file.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'family_scoped_records':len(values),'only_test_person_ids':True,'output':str(file)}))
