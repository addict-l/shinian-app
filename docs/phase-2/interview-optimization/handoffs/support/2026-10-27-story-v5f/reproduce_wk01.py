"""Reproduce S01 with a saved real reply and the real Node engine, offline.

Exit 0 means the reported BUG was reproduced, not that acceptance passed.
Point --backend at the fixed 20013ab/9915707 candidate checkout.
"""
from pathlib import Path
import argparse,json,hashlib,os,sys
p=argparse.ArgumentParser();p.add_argument('--backend',required=True);args=p.parse_args()
b=Path(args.backend).resolve();sys.path.insert(0,str(b))
for tag,name in [('V3J','v4d'),('V5F','v5f')]:
    d=b/('app/ai/interview_runtime_v3j_'+name)
    os.environ['INTERVIEW_'+tag+'_RUNTIME_DIR']=str(d)
    os.environ['INTERVIEW_'+tag+'_RUNTIME_MANIFEST_SHA256']=hashlib.sha256((d/'manifest.json').read_bytes()).hexdigest()
from app.services.contract_interview_state import v3j_runtime,v5f_runtime
from app.ai.contract_interview_v3j import V3jPipeline
x=json.loads(Path(__file__).with_name('wk01-cause-real-response.json').read_text())
for rt in (v3j_runtime(),v5f_runtime()):
    pipe=V3jPipeline(rt,None)
    def saved(system,user,params,timeout):
        assert system==rt.judge_prompt,'unexpected provider stage'
        return x['judge_response']
    pipe._call=saved
    result=pipe.run('WK01',x['sources'],{'previous_fields':{},'ask_counts':{}})
    errors=[e for a in result['trace']['attempts'] for e in a['errors']]
    print(json.dumps({'pipeline':rt.pipeline,'decision':result['result']['decision'],
        'effective':result['result']['effective'],'engine_errors':errors},ensure_ascii=False))
    assert result['result']['effective']['WK01-E2']=='missing'
    assert 'WK01-E2:repetition_is_not_explanation' in errors
