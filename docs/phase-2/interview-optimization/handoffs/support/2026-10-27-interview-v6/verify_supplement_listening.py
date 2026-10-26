"""Cloud regression for the negative '要补充' discovered by a live synthetic elder."""
from verify_story_https import *
from types import SimpleNamespace
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--run-label',default='');opts=parser.parse_args()
assert not opts.run_label or re.fullmatch('[a-zA-Z0-9_-]+',opts.run_label)
args=SimpleNamespace(private_dir='/opt/shinian-releases/story-listening-20261027/supplement-private',output_dir='/opt/shinian-releases/story-listening-20261027/real-candidate',forward_port=18453,legacy_forward_port=0)
api=API(args);api.authenticate()
results=[]
scenarios=[('only','没有别的要补充了。',False),('actor','嗯，认识那会儿的事，就先说这些吧，没有别的要补充了。',True),('addition','对了，我还给他补过工作服的袖口。没有别的要补充了。',True)]
for tag,text,has_content in scenarios:
 c=StoryCase(api,'v5f_S04_'+tag+('_'+opts.run_label if opts.run_label else ''),'family')
 try:
  c.setup('FM01')
  c.answer('我们是在工厂认识的，后来天天一起上下班，慢慢熟了才一起过日子。这段我不想多讲。')
  c.check('setup_reaches_supplement',guide(c.state)['phase']=='supplement')
  before=calls(c.state);c.answer(text);g=guide(c.state);after=calls(c.state)
  c.check('negative_addition_intent_reaches_review',g['phase']=='review',g['phase'])
  c.check('no_repeated_supplement_question',last_reply(c.state)==REVIEW,last_reply(c.state))
  added=[v for k,v in after.items() if k not in before]
  c.check('no_speaker_call_after_end',all(x['_stage']!='speaker' for x in added))
  if has_content:c.check('possible_content_retained',any(s['text']==text for s in g['contract_state']['sources']))
  else:c.check('only_end_uses_no_model',not added)
  same=api.send(c.prefix+'/conversation/messages',c.last_body)
  c.check('duplicate_end_is_idempotent',same==c.state)
  result=c.finish()
 except Exception as e:result=c.finish(type(e).__name__+':'+str(e))
 results.append(result)
assert all(x['passed'] for x in results)
