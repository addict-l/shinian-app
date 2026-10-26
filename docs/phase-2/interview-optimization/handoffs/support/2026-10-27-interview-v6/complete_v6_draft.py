"""Continue the same completed Q&A through actual draft generation and confirmation."""
import json,shutil
from types import SimpleNamespace
import verify_v6_production as p
from http_base import API,guide,save
R=p.R;name='v5f_V6_PROD_work_retry';path=R/'production-records'/(name+'.json')
old=json.loads(path.read_text());assert old['passed']
initial=R/'initial-attempts';initial.mkdir(exist_ok=True)
snapshot=initial/(name+'-before-draft.json');assert not snapshot.exists();shutil.copy2(path,snapshot)
api=API(SimpleNamespace(private_dir=str(R/'production-test-private'),output_dir=str(R/'production-records'),forward_port=443,legacy_forward_port=0));api.authenticate()
c=p.ProductionCase(api,name,'work');c.session=old['responses'][0]['session']['id'];c.prefix='/api/v1/chat/sessions/'+c.session
c.qid='WK01';c.events=old['events'];c.responses=old['responses'];c.checks=old['checks'];c.operations=sum(x['role']=='respondent' for x in c.events)
c.setup_method=old['setup'];c.state=api.send(c.prefix+'/state');c.life=c.state['life_overview']
assert guide(c.state)['phase']=='supplement'
expected=[s['text'] for s in guide(c.state)['contract_state']['sources']]+[s['text'] for s in c.depth().get('sources',[])]
p.v.save_draft(c,expected)
result=c.finish();assert result['passed']
summary=json.loads((R/'production-verification.json').read_text())
for x in summary['results']:
 if x['case']==name:x.update(passed=result['passed'],error=result['error'],checks=len(result['checks']))
summary.update(checks=sum(x['checks'] for x in summary['results']),draft_generated_and_confirmed_via_production_API=True,draft_confirmation_idempotent=True)
save(R/'production-verification.json',summary)
print(json.dumps({'case':name,'passed':True,'checks':len(result['checks']),'draft_generated_and_confirmed':True}),flush=True)
