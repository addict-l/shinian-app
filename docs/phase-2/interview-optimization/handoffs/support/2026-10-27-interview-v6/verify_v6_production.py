"""Official HTTPS validation in a newly registered synthetic family; no DB test seeding."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from types import SimpleNamespace
import json,subprocess,sys
import verify_story_https as v
from http_base import API,Case,guide,last_reply,calls,save,log,REVIEW

R=Path('/opt/shinian-releases/interview-v6-8799b52-20261027')
PIN='1062b6c2158fa8132c0a6ea9541a4dcdbec80f6dd32d21cfda0d816cd2a76487'
READONLY='''import json,sys
from app.db.database import SessionLocal,engine
from app.models.chat_session import ChatSessionModel
from app.models.family_member import FamilyMemberModel
r=json.load(sys.stdin)
assert engine.url.database=='ai_memories'
with SessionLocal() as db:
 s=db.get(ChatSessionModel,r['session']);assert s and s.family_id==r['family']
 p=db.get(FamilyMemberModel,s.primary_person_id)
 assert p.family_id==r['family'] and p.relationship=='独立验收测试'
 print(json.dumps({'life':p.life_interview,'guide':(s.information or {}).get('guided_interview')},ensure_ascii=False))
'''
def readonly_cloud(api,session,action='audit',**kw):
    assert action=='audit' and not kw,'production helper is read-only'
    req=json.dumps({'session':session,'family':api.family}).encode()
    result=subprocess.run(['flock','-w','120','/run/lock/shinian-v6-production-audit.lock','docker','exec','-i','backend-api-1','python','-c',READONLY],input=req,capture_output=True,timeout=150)
    assert result.returncode==0,'scoped synthetic-family readonly audit failed'
    return json.loads(result.stdout)

Original=v.StoryCase
class ProductionCase(Original):
    def setup(self,qid,old_flow=False):
        assert not old_flow
        Case.setup(self)
        self.qid=qid
        if self.module:
            target={'WK01':0,'FM01':0,'FM03':3}[qid]
            while guide(self.state)['topic_index']<target:
                index=guide(self.state)['topic_index']
                self.state=self.op('setup-topic-skip-'+str(index),self.prefix+'/conversation/messages',{'content':'跳过','client_request_id':v.uuid4().hex})
            self.check('target_selected_by_API',guide(self.state)['topic_index']==target)
            self.life=self.state['life_overview']
            self.events=[{'role':'interviewer','text':last_reply(self.state),'kind':'opening'}]
        else:
            self.state=self.api.send(self.prefix+'/state')
            self.life=self.state['life_overview']
        self.setup_method='official production HTTPS; new synthetic person; skeleton skipped/confirmed and target selected through public API only' if self.module else 'official production HTTPS; fresh full skeleton with public API only'
    def finish(self,error=None):
        x=super().finish(error)
        x['environment']='production_https'
        x['interviewer']='real DeepSeek v4-pro, thinking disabled'
        x['respondent_type']='fixed_synthetic'
        x['input_method']='fixed synthetic acceptance text; not a real elder and not a live AI actor'
        # Setup responses are preserved independently from the sampled Q&A.
        operations=self.api.private/'operations'/self.name
        x['setup_api_responses']=[json.loads(p.read_text())['response'] for p in sorted(operations.glob('*.json')) if p.stem.startswith(('setup-','initial-life','select-module','conversation','person')) and 'response' in json.loads(p.read_text())]
        save(self.api.output/(self.name+'.json'),x)
        return x
v.cloud=readonly_cloud
v.StoryCase=ProductionCase

def supplement(api,tag,text,has_content):
    c=ProductionCase(api,'v5f_V6_PROD_S04_'+tag,'family')
    try:
        c.setup('FM01')
        c.answer('我们是在工厂认识的，后来天天一起上下班，慢慢熟了才一起过日子。这段我不想多讲。')
        g=guide(c.state)
        c.check('answered_decline_keeps_draft',g['phase']=='supplement' and c.state.get('generation_offer') is not None)
        c.check('decline_does_not_deepen',not c.depth().get('asked'))
        before=calls(c.state);c.answer(text);g=guide(c.state);after=calls(c.state)
        c.check('end_reaches_review',g['phase']=='review')
        c.check('no_repeated_draft_or_more',last_reply(c.state)==REVIEW)
        added=[x for k,x in after.items() if k not in before]
        c.check('end_does_not_call_speaker',all(x['_stage']!='speaker' for x in added))
        if has_content:c.check('content_retained',any(x['text']==text for x in g['contract_state']['sources']))
        else:c.check('pure_end_no_model',not added)
        same=api.send(c.prefix+'/conversation/messages',c.last_body)
        c.check('duplicate_end_idempotent',same==c.state)
        return c.finish()
    except Exception as e:return c.finish(type(e).__name__+':'+str(e))

def main():
    executing=json.loads(subprocess.check_output(['docker','inspect','backend-api-1']))[0]
    live_env=dict(x.split('=',1) for x in executing['Config']['Env'])
    assert executing['Config']['Labels']['org.opencontainers.image.revision']=='8799b52b4d7590ea522c6798c364fd2fa451226a'
    assert executing['Config']['Labels']['org.opencontainers.image.version']=='V6'
    assert live_env['INTERVIEW_PIPELINE']=='v3j_v5f' and live_env['INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256']==PIN
    args=SimpleNamespace(private_dir=str(R/'production-test-private'),output_dir=str(R/'production-records'),forward_port=443,legacy_forward_port=0)
    api=API(args);log(health=api.authenticate(),tls_identity=v.HOST,version='V6')
    jobs=[('skeleton',lambda:v.run_skeleton(api,'v5f_V6_PROD_full_skeleton')),
          ('work_retry',lambda:v.run_story(api,'WK01','v5f_V6_PROD_work_retry','retry')),
          ('short_cause',lambda:v.run_story(api,'WK01','v5f_V6_PROD_short_cause','short_ready')),
          ('partial_memory',lambda:v.run_story(api,'FM01','v5f_V6_PROD_partial_memory','partial')),
          ('sensitive',lambda:v.run_story(api,'FM03','v5f_V6_PROD_sensitive','normal'))]
    for kind in ['C01_0','C01_1','C01_2','C01_3','C02_partial','C02_empty']:
        jobs.append((kind,lambda kind=kind:v.run_c_regression(api,kind)))
    for tag,text,content in [('only','没有别的要补充了。',False),('actor_phrase','嗯，认识那会儿的事，就先说这些吧，没有别的要补充了。',True),('addition','对了，我还给他补过工作服的袖口。没有别的要补充了。',True)]:
        jobs.append(('S04_'+tag,lambda tag=tag,text=text,content=content:supplement(api,tag,text,content)))
    results=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fn):name for name,fn in jobs}
        for f in as_completed(futures):
            x=f.result();results.append(x)
            log(completed=futures[f],passed=x['passed'])
    summary={'environment':'official_production_https','version':'V6','passed':all(x['passed'] for x in results),'cases':len(results),'passed_cases':sum(x['passed'] for x in results),'checks':sum(len(x['checks']) for x in results),'failed_checks':sum(not c['passed'] for x in results for c in x['checks']),'results':[{'case':x['case'],'passed':x['passed'],'error':x['error'],'checks':len(x['checks'])} for x in results],'database_seeding_used':False,'existing_family_written':False,'response_type':'fixed synthetic acceptance text','runtime_pin':PIN}
    save(R/'production-verification.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
    if not summary['passed']:sys.exit(1)
if __name__=='__main__':main()
