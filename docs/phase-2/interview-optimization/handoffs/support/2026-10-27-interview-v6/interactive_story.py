"""Candidate interview driver. Stdout exposes only visible dialogue, never judge/audit/gold.

The actor supplies answers via UTF-8 file. Parent keeps private/output paths from
actors and relays the sanitized result. Each case must use a distinct name.
"""
from pathlib import Path
from contextlib import redirect_stdout
import argparse,io,json,re,sys
from http_base import API,save,guide,last_reply
from verify_story_https import StoryCase,cloud

p=argparse.ArgumentParser();p.add_argument('--private-dir',required=True);p.add_argument('--output-dir',required=True)
p.add_argument('--forward-port',type=int,default=18453);p.add_argument('--legacy-forward-port',type=int,default=0)
p.add_argument('--case',required=True);p.add_argument('--module',choices=('childhood','growth','work','family','reflection','later_life'))
p.add_argument('--qid');p.add_argument('--answer-file');p.add_argument('--finalize',action='store_true');p.add_argument('--max-answers',type=int,default=8)
a=p.parse_args();assert re.fullmatch(r'v5f_actor_[a-zA-Z0-9_-]{1,50}',a.case)
assert 1<=a.max_answers<=8
api=API(a);meta_path=api.private/'actor-sessions'/(a.case+'.json')
# This stream also suppresses helper setup messages which contain internal qids.
with redirect_stdout(io.StringIO()):
    api.authenticate()
    if meta_path.exists():
        meta=json.loads(meta_path.read_text());assert not a.module or a.module==meta['module']
        c=StoryCase(api,a.case,meta['module']);c.session=meta['session'];c.prefix='/api/v1/chat/sessions/'+c.session
        c.qid=meta['qid'];c.events=meta['events'];c.responses=meta['responses'];c.operations=meta['answers'];c.checks=meta['checks']
        c.setup_method=meta['setup'];c.state=api.send(c.prefix+'/state');c.life=c.state['life_overview']
    else:
        assert a.module and a.qid and not a.answer_file and not a.finalize, 'Initialize a case before answering'
        c=StoryCase(api,a.case,a.module);c.setup(a.qid)
        meta={'case':a.case,'module':a.module,'qid':a.qid,'session':c.session,'answers':0,'setup':c.setup_method,'events':c.events,'responses':c.responses,'checks':c.checks}
        save(meta_path,meta)
    if a.answer_file:
        assert c.operations<a.max_answers,'sample cap reached'
        assert guide(c.state)['phase'] not in ('review','saved','finished','module_review'), 'interview already complete'
        text=Path(a.answer_file).read_text().strip();assert text and len(text)<=1500
        assert not meta.get('pending_answer') or meta['pending_answer']==text, 'Retry must use the original answer file'
        meta['pending_answer']=text;save(meta_path,meta)
        c.answer(text)
        meta.pop('pending_answer',None)
    if a.finalize:
        assert guide(c.state)['phase']=='review','Finalize requires the interview to reach review naturally'
        draft=c.op('actor-generate-draft',c.prefix+'/draft',{},method='POST');c.draft=draft
        save(api.output/(c.name+'-draft.json'),draft)
        memory=c.op('actor-confirm-draft','/api/v1/memory-drafts/'+draft['id']+'/confirm',{'revision':draft['revision']})
        c.check('actor_draft_saved',bool(memory.get('id')))
        c.state=api.send(c.prefix+'/state')
    meta.update(events=c.events,responses=c.responses,answers=c.operations,checks=c.checks)
    save(meta_path,meta)
    record=c.finish()
    record['input_method']='live Codex subagent roleplay from private synthetic biography and visible dialogue only; no gold or internal judgment'
    record['respondent_type']='live_agent_roleplay'
    record['sample_answer_cap']=a.max_answers
    record['sample_cutoff']=c.operations>=a.max_answers and record['backend_final_phase'] not in ('saved','confirmed','finished','module_review')
    # Review is a natural end of Q&A, while persistence remains separately visible.
    record['conversation_completed']=record['backend_final_phase'] in ('review','saved','confirmed','finished','module_review')
    save(api.output/(c.name+'.json'),record)
phase=guide(c.state)['phase']
visible={'case':a.case,'dialogue':[{'role':x['role'],'text':x['text']} for x in c.events],
         'input_allowed':phase not in ('review','saved','finished','module_review') and c.operations<a.max_answers,
         'ready_to_review':phase=='review','saved':phase=='saved','answer_count':c.operations,'sample_cap':a.max_answers}
print(json.dumps(visible,ensure_ascii=False,indent=2))
