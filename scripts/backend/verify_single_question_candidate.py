"""Resume verification after a test-only host configuration failure."""
from pathlib import Path
import json,os,subprocess,shutil,sys
os.umask(0o077)
r=Path('/opt/shinian-releases/interview-single-question-v2-20261018')
tag='shinian-api:interview-single-question-v2-20261018'
args=['docker','run','--rm','--network','backend_default','--env-file',str(r/'runtime.env')]
if '--updated-skip-boundary' in sys.argv:
 shutil.copy2('/tmp/contract_guided_interview.py',r/'patch/app/services/contract_guided_interview.py')
 shutil.copy2('/tmp/test_contract_interview_workflow.py',r/'patch/tests/test_contract_interview_workflow.py')
 with (r/'build-revision2.log').open('w') as f:subprocess.run(['docker','build','-t',tag,str(r/'patch')],stdout=f,stderr=subprocess.STDOUT,check=True)
with (r/'candidate-tests-corrected-host.log').open('w') as f:
 subprocess.run(args+['-e','ALLOWED_HOSTS=testserver','--entrypoint','python',tag,'-m','unittest','discover','-s','tests','-p','test_contract_interview_*.py','-q'],stdout=f,stderr=subprocess.STDOUT,check=True)
smoke='''import json
from app.services.contract_interview_state import runtime,questions
from app.ai.contract_interview import ContractInterviewPipeline
from app.ai.llm_client import LLMClient
r=runtime();assert len(r.questions)==83 and len(questions('skeleton'))==11
assert len(runtime('full-interview-v1.29.1').questions)==62
assert r.settings['thinking']=='disabled' and 'reasoning_effort' not in r.settings
out=ContractInterviewPipeline(r,LLMClient()).run('SK01',[{'id':'smoke-only','question_id':'SK01','speaker':'narrator','question':r.questions['SK01']['main_question'],'text':'我是1984年出生的。'}])
assert out['result']['decision']=='ready',out['result']['errors']
print(json.dumps({'passed':True,'runtime':r.version,'questions':len(r.questions),'skeleton':len(questions('skeleton')),'settings':r.settings,'decision':out['result']['decision'],'persisted_business_data':False}))
'''
with (r/'smoke.json').open('w') as f:
 subprocess.run(args+['-i','--entrypoint','python',tag,'-'],input=smoke,text=True,stdout=f,stderr=subprocess.STDOUT,check=True)
print(json.dumps({'prepared':True,'smoke':json.loads((r/'smoke.json').read_text()),'production_host_protection_unchanged':True}))
