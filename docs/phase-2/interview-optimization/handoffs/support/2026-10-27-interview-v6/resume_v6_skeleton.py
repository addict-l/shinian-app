"""Retry the same failed, idempotent API opening; preserve the original capture."""
from pathlib import Path
import json,shutil
import verify_v6_production as p
from http_base import API,save
from types import SimpleNamespace
R=p.R;out=R/'production-records';initial=R/'initial-attempts';initial.mkdir(exist_ok=True)
case='v5f_V6_PROD_full_skeleton'
for source in [out/(case+'.json'),R/'production-verification.json',R/'production-test-private/operations'/case/'conversation.json']:
    target=initial/source.name
    assert not target.exists(),'initial record already preserved; inspect before another retry'
    shutil.copy2(source,target)
args=SimpleNamespace(private_dir=str(R/'production-test-private'),output_dir=str(out),forward_port=443,legacy_forward_port=0)
api=API(args);api.authenticate()
result=p.v.run_skeleton(api,case)
summary=json.loads((R/'production-verification.json').read_text())
summary['results']=[x for x in summary['results'] if x['case']!=case]+[{'case':case,'passed':result['passed'],'error':result['error'],'checks':len(result['checks'])}]
summary.update(passed=all(x['passed'] for x in summary['results']),passed_cases=sum(x['passed'] for x in summary['results']))
summary['checks']=sum(x['checks'] for x in summary['results'])
summary['failed_checks']=sum(not c['passed'] for c in result['checks'])
summary.update(initial_failed_attempts_retained=1,total_case_captures_including_initial=15,
    recovery='same person and same API operation retried after MySQL deadlock; no source/runtime/config changes',
    concurrency_issue_fixed=False)
save(R/'production-verification.json',summary)
print(json.dumps(summary,ensure_ascii=False),flush=True)
assert summary['passed']
