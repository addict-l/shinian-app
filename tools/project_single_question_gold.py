#!/usr/bin/env python3
"""Project existing immutable annotations, before calls, onto explicit new topics.

No model output is read. Source prose and historical interviewer questions are
unchanged. New follow-up expectations are derived from annotated states only.
"""
import copy,hashlib,json,itertools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'docs/prototypes/full-interview-v2/single-question-v2'
PARENT=ROOT/'docs/prototypes/full-interview-evaluation/unified-development-gold-v7.json'
OUT=ROOT/'docs/prototypes/full-interview-evaluation/single-question-v2-gold.json'
TERMINAL={'known','none','unknown','declined','deferred','not_applicable'}
def states(g):return g.get('states',[g.get('state')])
def route(q,gold,old_followup,focus):
 # Preserve explicit interaction controls; they are not completion facts.
 if set(old_followup['decisions']) <= {'paused','skipped','deferred'}:return copy.deepcopy(old_followup)
 ids=list(gold); combinations=list(itertools.product(*(states(gold[k]) for k in ids)))
 outcomes=[]
 for combo in combinations:
  s=dict(zip(ids,combo)); active=[]
  premise=next((f['id'] for f in q['elements'] if f['activation'].get('premise_check')),None)
  unavailable=premise and s[premise] in ('none','unknown','declined','deferred','not_applicable')
  for f in q['elements']:
   fid=f['id'];a=f['activation'];on=False
   if f['requirement'] in ('optional','input') or a.get('never_ask'):continue
   if unavailable:on=fid==premise
   elif a.get('premise_check'):on=not any(s[x['id']]!='missing' for x in q['elements'] if x['id']!=fid and x['requirement']!='optional')
   elif 'after_answer' in a:on=all(s[x] in ('known','none') for x in a['after_answer'])
   elif 'known' in a:on=all(s[x]=='known' for x in a['known'])
   elif 'any_known' in a:on=any(s[x]=='known' for x in a['any_known'])
   elif 'unless_none' in a:on=not any(s[x] in ('none','not_applicable') for x in a['unless_none'])
   elif 'reported_without_self' in a:on=s[a['reported_without_self'][0]]=='known' and s[a['reported_without_self'][1]]!='known'
   elif any(k.startswith('if_ambiguous') for k in a):
    on=fid in old_followup.get('targets',[]) or (focus or {}).get('field_id')==fid
   else:on=a.get('always',False) or f['required']
   if on:active.append(fid)
  pending=[fid for fid in active if s[fid] in ('missing','ambiguous','conflict')]
  if pending:
   target=next((fid for fid in pending if s[fid] in ('ambiguous','conflict')),None)
   target=target or ('SK05-E2' if 'SK05-E2' in pending else None) or (premise if premise in pending else None) or pending[0]
   outcomes.append(('ask',target))
  else:outcomes.append(('limited' if unavailable or any(s[fid] not in ('known','none') for fid in active) else 'ready',None))
 return {'decisions':sorted({d for d,t in outcomes}),'targets':list(dict.fromkeys(t for d,t in outcomes))}
def main():
 if OUT.exists():raise ValueError('never overwrite projected labels')
 data=json.loads(PARENT.read_text());contracts=json.loads((RUNTIME/'contracts.json').read_text());result=copy.deepcopy(data);result['cases']=[];audit=[]
 for case in data['cases']:
  for q in [q for q in contracts['questions'] if q['legacy_question_id']==case['question_id']]:
   nc=copy.deepcopy(case);nc.update(id=case['id']+'--'+q['id'],question_id=q['id'],legacy_case_id=case['id'])
   for t in nc['turns']:
    original=copy.deepcopy(t['expected']);new={};changes=[]
    for f in q['elements']:
     old=f['legacy_field_id'];g=copy.deepcopy(original['fields'][old])
     if q['id']=='CH01' and f['id']=='CH01-E1':
      # Concrete event annotation wins over just a memory label. Keep absent
      # event failures visible instead of making a second mandatory target.
      event=original['fields']['CH01-E2']
      if 'known' in states(event):g=copy.deepcopy(event);changes.append('merged memory/event uses original event evidence')
     if q['id']=='CH04' and f['id']=='CH04-E1':
      alt=original['fields']['CH04-E2']
      if 'known' not in states(g) and 'known' in states(alt):g=copy.deepcopy(alt);changes.append('merged interest/dream uses original dream evidence')
     if f['id']=='GR01-A1b':
      # School date does not itself become premise evidence by relabelling.
      # Actual process facts can establish applicability; otherwise ask it.
      if states(g)==['none']:g=copy.deepcopy(g)
      else:g={'state':'missing'}
      changes.append('new independent schooling premise: explicit no-school only, otherwise missing')
     if f['requirement']=='optional':g={'state':'missing','optional_unscored':True}
     new[f['id']]=g
    t['expected']['fields']=new
    own=set(new)
    if t.get('focus') and t['focus']['field_id'] not in own:t.pop('focus');changes.append('removed focus belonging to other split topic')
    if 'question_id' in t['source']:t['source']['question_id']=q['id']
    if t['source'].get('target_field_id') not in own:t['source'].pop('target_field_id',None)
    # No original question replacement; this remains retrospective transcript
    # extraction, never represented as live replies to the new wording.
    t['expected']['followup']=route(q,new,original['followup'],t.get('focus'))
    audit.append({'case':nc['id'],'source_id':t['source']['id'],'field_projection':{f['id']:f['legacy_field_id'] for f in q['elements']},'changes':changes,'original_followup':original['followup'],'new_followup':t['expected']['followup']})
   result['cases'].append(nc)
 result['authoring'].update(gold_version='single-question-v2-projection-1',parent_dataset=str(PARENT.relative_to(ROOT)),parent_dataset_sha256=hashlib.sha256(PARENT.read_bytes()).hexdigest(),business_migration='single-question-v2',source_text_and_actual_interviewer_question_unchanged=True,not_live_answer_simulation=True,annotation_audit='single-question-v2-gold.projection.json')
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 OUT.with_suffix('.projection.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'people':len(result['narrators']),'cases':len(result['cases']),'checkpoints':len(audit),'questions':len({c['question_id'] for c in result['cases']})}))
if __name__=='__main__':main()
