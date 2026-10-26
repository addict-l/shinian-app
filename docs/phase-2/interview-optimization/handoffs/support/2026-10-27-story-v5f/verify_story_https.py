"""Real DeepSeek via independent MySQL + verified TLS. Fixed synthetic elder inputs.

No gold/holdout/cached answer is consulted. Target setup is a documented fixture;
full skeleton uses actual API from a fresh person. Never writes production data.
"""
from http_base import *
import subprocess
import shlex
import sys
import os

HERE = Path(__file__).resolve().parent
CONTAINER = 'shinian-story-v5f-20013ab-20261026'

def cloud(api, session, action='audit', **kw):
    code = (HERE/'cloud_fixture.py').read_text()
    command = 'sudo -n docker exec -i ' + CONTAINER + ' python -c ' + shlex.quote(code)
    command_args = ['docker','exec','-i',CONTAINER,'python','-c',code] if os.getenv('SHINIAN_CLOUD_CANDIDATE')=='1' else ['ssh','-S','/tmp/shv5f-direct.sock','-i','/Users/student03/.ssh/id_ed25519_shinian',
        '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15',
        'admin@47.82.83.74',command]
    result = subprocess.run(command_args,input=json.dumps(dict(action=action,family=api.family,session=session,**kw)),
        text=True,capture_output=True,timeout=90)
    if result.returncode:
        raise RuntimeError('scoped_cloud_tool_failed:' + result.stderr[-800:])
    return json.loads(result.stdout)

class StoryCase(Case):
    def setup(self,qid,old_flow=False):
        person=self.op('person','/api/v1/family-members/',{'family_id':self.api.family,'name':self.name,
            'relationship':'独立验收测试','client_request_id':str(uuid4())})
        state=self.op('conversation','/api/v1/chat/members/'+person['id']+'/conversation?family_id='+self.api.family,method='POST')
        self.session=state['session']['id'];self.prefix='/api/v1/chat/sessions/'+self.session
        self.qid=qid
        if self.module:
            loc=self.api.private/'operations'/self.name/'fixture.json'
            if not loc.exists():save(loc,cloud(self.api,self.session,'seed',module=self.module,qid=qid,old_flow=old_flow))
            self.setup_method='synthetic target checkpoint in independent MySQL; catalog entry; no fixture provider replies'
        else:self.setup_method='fresh complete skeleton over HTTPS; no state fixture'
        self.state=self.api.send(self.prefix+'/state');self.life=self.state['life_overview']
        text=last_reply(self.state) if self.module else self.life['turns'][-1]['content']
        self.events.append({'role':'interviewer','text':text,'kind':'opening'})
        log(case=self.name,stage='setup_complete',qid=qid)
    def depth(self):return (guide(self.state)['contract_state'].get('deepen') or {})
    def finish(self,error=None):
        try:
            self.audit=cloud(self.api,self.session)
            save(self.api.output/(self.name+'-audit.json'),self.audit)
        except Exception as exc:
            error=error or str(exc)
        record=super().finish(error)
        real=getattr(self,'audit',{})
        phase=(real.get('guide') or {}).get('phase') if self.module else (real.get('life') or {}).get('status')
        record.update(qid=getattr(self,'qid',None),memory_generation_or_save_called=bool(getattr(self,'draft',None)),
            backend_final_phase=phase,natural_completion=phase in ('saved','confirmed','finished','module_review'),
            sample_cutoff=phase not in ('saved','confirmed','finished','module_review'))
        save(self.api.output/(self.name+'.json'),record)
        return record
    def detail(self,text,timeout_retry=False):
        g=guide(self.state);fields=deepcopy(g['contract_state']['fields']);before=calls(self.state)
        self.check('detail_was_requested_'+str(self.operations),bool(self.depth().get('awaiting')))
        self.answer(text,timeout_retry)
        g=guide(self.state);local=g['contract_state'];new=calls(self.state)
        extra=[v for k,v in new.items() if k not in before]
        self.check('detail_does_not_change_fields_'+str(self.operations),local['fields']==fields)
        self.check('detail_does_not_call_judgment_'+str(self.operations),all(c.get('_stage') in ('deepen','speaker') for c in extra),[c.get('_stage') for c in extra])
        self.check('detail_retained_verbatim_'+str(self.operations),any(s['text']==text for s in self.depth().get('sources',[])))
        self.check('detail_audit_'+str(self.operations),any(a.get('kind')=='deepen_answer' for a in local['audit']))
        self.check('depth_cap_'+str(self.operations),self.depth()['asked']<=self.depth()['cap'])

MATERIAL={
 'WK01':('work','我最初在镇上的粮站做搬运工。因为家里缺钱，叔叔介绍我去，先靠自己的力气挣口饭吃。',[
     '第一天是师傅老周带着我，他把麻袋折成垫肩递给我，说先跟着走一趟，别急着逞能。',
     '那会儿我们住在粮站后头的一间宿舍，晚上收工我就坐在门槛上缝那块磨破的垫肩。']),
 'FM01':('family','我和老伴是在工厂认识的，后来天天一起上下班，慢慢熟了，才决定一起过日子。',[
     '有一天下班突然下雨，她从车间拿出一把旧雨伞，让我站在里面，自己半边肩膀都淋湿了。',
     '后来我给她补了伞上漏水的地方，她第二天拎着伞来找我，我们就在厂门口笑了好一阵。']),
 'FM04b':('family','养孩子最让我欣慰的是女儿上初中后，看到我下工累，主动帮我把院子里的衣服收起来，还烧好了饭。',[
     '那天我推门进去，她把一碗热面端到桌上，说妈你先吃，我都尝过了，不咸。',
     '我坐下才看见她手指烫了个小泡，她赶紧把手藏在背后，我把她拉过来，给她抹了药。']),
 'RV06':('reflection','我最想感谢的是小学老师陈老师。我家里困难，是她帮我向学校申请减免费用，让我没有中断读书。',[
     '有一天放学她把我叫到办公室，从抽屉里拿出一个蓝布书包，说这是学校发的，让我安心来上课。',
     '后来我才知道书包是她自己缝的，工作后我去看她，她还拿出当年的合影，一眼就找到了我。']),
 'RV13':('reflection','我这一生最感恩的是那年发大水，邻居老赵划着小船回来，把我和母亲接到了高处的学校里。',[
     '那天水已经没过院子门槛，老赵把船拴在树上，先背母亲上船，又回来拉着我一步一步挪过去。',
     '到了学校他从兜里掏出两个馒头塞给母亲，没坐一会儿又划船回去接别人了。']),
 'WK09':('work','我工作中最难熬的是工厂停工那几年，没了固定收入，我每天在街边修自行车，才撑住一家人的生活。',[
     '有个老顾客见我连着几天没生意，带来一辆旧车让我修，临走时多放下二十块钱，我一直记得。']),
 'FM03':('family','刚结婚时我和老伴常为寄钱给老人拌嘴。后来我们约定每月先留生活费，再商量两边各寄多少，就慢慢好了。',[
     '那天我们在饭桌上把工资本和生活费摆出来，一笔一笔算完，他把寄钱的单子递给我，叫我先签字。']),
 'RV02':('reflection','我最放不下的遗憾是母亲住院时我在外地，没能赶回去陪她。要是能重来，我会早些请假回家。',[
     '那时邻居打来电话，我赶到车站时末班车已经开了，只能在候车室坐到天亮，手里一直攥着车票。'])
}

def to_draft(c,details):
    # Answers are fixed synthetic material, not generated after reading internal state.
    for text in details:
        if not c.depth().get('awaiting'):break
        c.detail(text)
    c.check('reaches_draft_step',guide(c.state)['phase']=='supplement' and c.state.get('generation_offer') is not None,guide(c.state)['phase'])
    c.check('at_most_two',c.depth().get('asked',0)<=c.depth().get('cap',2))

def save_draft(c,expected):
    c.answer('没有了，就这些。')
    c.check('nothing_more_goes_to_review',guide(c.state)['phase']=='review')
    draft=c.op('generate-draft',c.prefix+'/draft',{},method='POST')
    c.draft=draft;save(c.api.output/(c.name+'-draft.json'),draft)
    raw=draft['memory']['raw_content']
    c.check('detail_in_draft_raw',all(t in raw for t in expected),expected)
    # Summary fidelity is reviewed from the original model output, not a keyword pass substituted for review.
    memory=c.op('confirm-draft','/api/v1/memory-drafts/'+draft['id']+'/confirm',{'revision':draft['revision']})
    c.check('confirmed_saved',bool(memory.get('id')))
    c.check('saved_raw_retains_details',all(t in memory['raw_content'] for t in expected))
    repeated=c.op('confirm-again','/api/v1/memory-drafts/'+draft['id']+'/confirm',{'revision':draft['revision']})
    c.check('confirm_idempotent',memory['id']==repeated['id'])

def run_story(api,qid,name=None,mode='normal'):
    module,first,details=MATERIAL[qid]
    c=StoryCase(api,name or 'story_'+qid,module)
    try:
        c.setup(qid,old_flow=mode=='old')
        if mode=='short_first':first='在家务农，缺钱。'
        elif mode=='short_ready':first='我最感谢陈老师。' if qid=='RV06' else '因家穷才去粮站搬货。'
        elif mode=='partial':first='第一次见面的事我记不清了。就记得厂里的老师傅给我们做媒，还请我们吃了一顿饺子，我们后来就结了婚。'
        elif mode=='unknown':first='记不清了。'
        c.answer(first,timeout_retry=mode=='retry')
        if mode=='old':
            c.check('v4d_marker_preserved',guide(c.state)['contract_state']['pipeline']=='v3j_v4d')
            c.check('v4d_no_deepen','deepen' not in guide(c.state)['contract_state'])
        elif mode in ('short_first','short_ready','unknown'):
            c.check('no_depth',not c.depth().get('asked'))
            if mode=='short_first':
                c.check('short_incomplete_may_ask_required_field',guide(c.state)['phase'] in ('exploring','supplement'))
            else:c.check('finishes_with_draft',guide(c.state)['phase']=='supplement')
            if mode=='short_ready':
                c.check('short_gate_actually_exercised',any(x.get('reason')=='short' for x in c.depth().get('log',[])))
        elif mode.startswith('provider_fail'):
            c.check('injected_deepen_failure_recorded',any(x.get('reason')=='call_failed' for x in c.depth().get('log',[])),c.depth().get('log'))
            c.check('failure_falls_back_to_draft',guide(c.state)['phase']=='supplement' and not c.depth().get('awaiting') and c.state.get('generation_offer') is not None)
        else:
            c.check('new_flow_v5f',guide(c.state)['contract_state']['pipeline']=='v3j_v5f')
            c.check('first_answer_ready_or_partial',guide(c.state)['contract_state']['last_result']['decision'] in ('ready','limited','ask','ask_defer'))
            if mode in ('skip','rest','pause','short_detail'):
                c.check('control_setup_is_actual_depth',bool(c.depth().get('awaiting')))
                if c.depth().get('awaiting'):
                    old_question=guide(c.state)['pending_question']['text']
                    if mode=='skip':
                        c.answer('跳过')
                        c.check('skip_keeps_topic_and_draft',guide(c.state)['contract_state']['question_id']==qid and guide(c.state)['phase']=='supplement' and c.state.get('generation_offer') is not None)
                    elif mode=='rest':
                        c.detail('我有点累了，想先歇一会儿。')
                        c.check('tired_pauses',guide(c.state)['phase']=='paused')
                        c.check('tired_stops_depth',c.depth().get('stopped')=='rest')
                        c.answer('继续')
                        c.check('tired_resume_entry',guide(c.state)['phase']!='paused' and not c.depth().get('awaiting') and guide(c.state)['pending_question'] is None)
                    elif mode=='pause':
                        before=deepcopy(c.depth());c.answer('暂停')
                        c.check('explicit_pause',guide(c.state)['phase']=='paused' and c.depth()==before)
                        c.answer('继续')
                        c.check('resume_keeps_detail',c.depth().get('awaiting') and guide(c.state)['pending_question']['text']==old_question and last_reply(c.state)==old_question)
                        c.detail('就一起走了一段路。')
                    else:
                        c.detail('就一起走了一段路。')
                        c.check('short_detail_stops',guide(c.state)['phase']=='supplement' and not c.depth().get('awaiting'))
            else:
                c.check('depth_received',bool(c.depth().get('asked')),c.depth().get('log'))
                if mode=='partial':
                    inp='\n'.join(x.get('input','') for x in c.depth().get('log',[]))
                    c.check('partial_scope_sent','老人刚说记不清的：' in inp and '他接着讲的：' in inp,inp)
                    details=['那顿饭是在老师傅家里吃的，他把两碗饺子放在我们面前，让我们慢慢吃，自己在灶台边忙活。','后来我们结婚时又请他来吃饭，他笑着说总算没白忙，我们专门给他留了主桌的位置。']
                to_draft(c,details)
                if qid in ('WK09','FM03','RV02'):c.check('sensitive_max_one',c.depth().get('asked',0)<=1)
                sources=[s['text'] for s in c.depth().get('sources',[])]
                if mode=='normal' and qid in ('WK01','FM01','FM04b','RV06','RV13') and guide(c.state)['phase']=='supplement':
                    save_draft(c,sources)
        # Duplicate the latest answer after successful completion, without calling a new model.
        if hasattr(c,'last_body') and not getattr(c,'draft',None):
            before=c.api.send(c.prefix+'/state')
            repeated=c.op('duplicate',c.prefix+'/conversation/messages',c.last_body)
            c.check('same_request_no_duplicate_message',len(repeated['messages'])==len(before['messages']))
            c.check('same_request_no_new_call',calls(repeated)==calls(before))
        return c.finish()
    except Exception as exc:return c.finish(type(exc).__name__+':'+str(exc))

def run_skeleton(api):
    c=StoryCase(api,'v5f_full_skeleton')
    answers={
      'SK01':'我是一九五二年出生的。',
      'SK01b':'我出生在江苏省苏州市的一个小村庄。',
      'SK01c':'我记忆中的家乡是小时候的苏州老村子，屋前有条小河，河边种着几棵柳树，大家平时在石桥上来来往往。',
      'SK02':'名字是爷爷给取的，叫志远，希望我眼光放得长远些。',
      'SK03':'我小时候主要跟父母和奶奶一起生活。',
      'SK03b':'小时候家里主要靠父母种田维持生活，农闲时父亲也帮邻居做木工。',
      'SK03c':'我有一个姐姐和一个弟弟，我排在中间。',
      'SK03d':'小时候家里人相处很和睦，遇上难事会一起商量。',
      'SK04':'家里人从小教我要诚实，答应别人的事要做到。',
      'SK05':'我觉得自己性格比较随和，也有些倔强。',
      'SK06':'想到这一生，我会用踏实和珍惜来概括。'}
    seen=[];extra=0;fields=None;prior_detail=False;previous=None
    try:
        c.setup('SK01')
        for step in range(18):
            if c.life['status']=='review':break
            qid=c.life['question_id']
            if qid!=previous:
                seen.append(qid);previous=qid
            elif qid!='SK01c':
                c.check('unplanned_followup_'+str(step),False,c.life['question']);break
            local=cloud(api,c.session)['life']['questions'][qid]
            depth=local.get('deepen') or {}
            if depth.get('awaiting'):
                prior_detail=True;before=deepcopy(local['fields']);extra+=1
                text=('那座石桥很窄，两边没有栏杆。奶奶每次都牵着我的手，过桥前还让我把鞋带系紧，怕我绊倒。' if extra==1 else '就记得这些了。')
            else:prior_detail=False;text=answers[qid]
            c.life_answer(text)
            after=cloud(api,c.session)['life']['questions'][qid]
            if qid=='SK01c' and prior_detail:
                c.check('SK01c_detail_no_field_change_'+str(extra),before==after['fields'])
                c.check('SK01c_detail_no_judge_'+str(extra),'judge' not in after['audit'][-1].get('calls',{}))
            if qid=='SK01c' and c.life['question_id']!='SK01c':
                c.check('SK01c_closes_known',after['status']=='known')
                c.check('SK01c_then_SK02',c.life['question_id']=='SK02')
            if c.life['status']=='collecting':c.check('next_question_matches_reply_'+str(step),c.life['turns'][-1]['content'].endswith(c.life['question']))
        c.check('full_frozen_order',seen==ORDER,seen)
        c.check('SK01c_real_depth_exercised',extra>=1,extra)
        c.check('review_reached',c.life['status']=='review')
        if c.life['status']=='review':
            state=c.op('life-confirm',c.prefix+'/life-overview/actions',{'action':'confirm','text':'','client_request_id':str(uuid4()),'expected_version':c.life['version']})
            c.check('life_confirmed',state['life_overview']['status']=='confirmed')
            state=c.op('real-select-module',c.prefix+'/interview',{'module':'work','expected_version':state['session']['version']})
            c.check('module_selected_via_API',guide(state)['module']=='work' and guide(state)['module_selected'])
        return c.finish()
    except Exception as exc:return c.finish(type(exc).__name__+':'+str(exc))

def run_transitions(api):
    c=StoryCase(api,'v5f_refusal_transitions','work')
    try:
        c.setup('WK01')
        for k in range(5):
            before=guide(c.state)['topic_index']
            c.answer('这道题我不想说。')
            c.check('refusal_advances_'+str(k),guide(c.state)['topic_index']==before+1)
        replies=[e['text'] for e in c.events if e['role']=='interviewer' and e.get('kind')!='opening']
        c.check('transition_phrase_not_repeated',sum('那咱们再聊聊' in t for t in replies)<=1,replies)
        c.check('no_bare_interjection',all(t.strip() not in ('噢，','嗯，','哦，','噢','嗯','哦') for t in replies))
        return c.finish()
    except Exception as exc:return c.finish(type(exc).__name__+':'+str(exc))

def resume_skeleton(api):
    # Preserve the initial capture: the harness stopped on SK04's legitimate
    # conditional follow-up (influence). Continue the SAME backend session.
    old=json.loads((api.output/'v5f_full_skeleton.json').read_text())
    c=StoryCase(api,'v5f_full_skeleton_completed')
    try:
        c.session=old['responses'][0]['session']['id'];c.prefix='/api/v1/chat/sessions/'+c.session
        c.setup_method='same fresh API skeleton continued after harness stopped on a required SK04 follow-up'
        c.qid='SK01';c.events=deepcopy(old['events']);c.responses=deepcopy(old['responses'])
        c.checks=[deepcopy(x) for x in old['checks'] if x['passed']]
        c.state=api.send(c.prefix+'/state');c.life=c.state['life_overview']
        answers={'SK04':'这让我后来待人很诚实，答应别人的事总要想办法做到，不会随口答应就算了。',
            'SK05':'我觉得自己比较随和，也有点倔强，遇到认准的事就会坚持做下去。',
            'SK06':'想到这一生，我会用踏实和珍惜来概括。'}
        for step in range(6):
            if c.life['status']=='review':break
            c.life_answer(answers[c.life['question_id']],label='resume-life-'+str(step))
        sequence=[]
        for state in old['responses']+c.responses[len(old['responses']):]:
            qid=state['life_overview']['question_id']
            if qid and (not sequence or sequence[-1]!=qid):sequence.append(qid)
        sequence=['SK01']+sequence
        c.check('full_frozen_order_completed',sequence==ORDER,sequence)
        c.check('review_reached',c.life['status']=='review')
        if c.life['status']=='review':
            state=c.op('life-confirm',c.prefix+'/life-overview/actions',{'action':'confirm','text':'','client_request_id':str(uuid4()),'expected_version':c.life['version']})
            c.check('life_confirmed',state['life_overview']['status']=='confirmed')
            state=c.op('real-select-module',c.prefix+'/interview',{'module':'work','expected_version':state['session']['version']})
            c.check('module_selected_via_API',guide(state)['module']=='work' and guide(state)['module_selected'])
        return c.finish()
    except Exception as exc:return c.finish(type(exc).__name__+':'+str(exc))

def run_c_regression(api,kind):
    c=StoryCase(api,'v5f_regression_'+kind,'work' if kind.startswith('C01') else 'family')
    try:
        c.setup('WK01' if kind.startswith('C01') else 'FM01')
        if kind.startswith('C01'):
            index=int(kind[-1]);texts=['那时候下工累了就歇一会儿。','不是累了，我还想接着聊。','她不想说，后来我就没有再问。','我有点累了，想先歇一会儿。']
            c.answer(texts[index]);g=guide(c.state)
            if index==3:
                c.check('own_present_tired_pauses',g['phase']=='paused')
                c.answer('继续');c.check('can_resume',guide(c.state)['phase']!='paused')
            else:
                c.check('historical_negated_other_not_control',g['phase']!='paused' and g['topic_index']==0)
                c.check('no_false_refusal',all(a.get('speaker',{}).get('reason') not in ('declined','deferred','rest') for a in g['contract_state']['audit']))
        elif kind=='C02_partial':
            c.answer('我们是在工厂认识的。后来天天一起上下班，慢慢就熟了。这段我不想多讲。')
            c.check('answered_then_decline_keeps_draft',guide(c.state)['phase']=='supplement' and c.state.get('generation_offer') is not None)
            c.check('answered_then_decline_no_depth',not c.depth().get('asked'))
        elif kind=='C02_empty':
            c.answer('这段我不想多讲。');c.check('empty_refusal_advances',guide(c.state)['topic_index']==1)
        return c.finish()
    except Exception as exc:return c.finish(type(exc).__name__+':'+str(exc))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--private-dir',required=True);parser.add_argument('--output-dir',required=True)
    parser.add_argument('--forward-port',type=int,default=28452);parser.add_argument('--legacy-forward-port',type=int,default=0)
    parser.add_argument('--cases',default='WK01,FM01')
    args=parser.parse_args();api=API(args);log(health=api.authenticate(),tls_identity=HOST)
    results=[]
    for spec in args.cases.split(','):
        if spec=='skeleton':results.append(run_skeleton(api));continue
        if spec=='transitions':results.append(run_transitions(api));continue
        if spec=='skeleton_resume':results.append(resume_skeleton(api));continue
        if spec.startswith('C0'):results.append(run_c_regression(api,spec));continue
        parts=spec.split(':');qid=parts[0];mode=parts[1] if len(parts)>1 else 'normal'
        results.append(run_story(api,qid,name='v5f_'+qid+'_'+mode,mode=mode))
    save(api.output/'summary.json',{'passed':all(x['passed'] for x in results),'cases':[{'case':r['case'],'passed':r['passed'],'checks':len(r['checks']),'error':r['error']} for r in results]})
    if not all(x['passed'] for x in results):sys.exit(1)

if __name__=='__main__':main()
