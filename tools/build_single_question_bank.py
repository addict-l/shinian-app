#!/usr/bin/env python3
"""Explicitly authored business migration; no model outputs or person identifiers."""
import copy, hashlib, json, shutil, datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/prototypes/full-interview-v1/candidate39-null-states'
OUT=ROOT/'docs/prototypes/full-interview-v2/single-question-v2'
def write(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n' if not isinstance(x,str) else x)
# Each tuple: entry wording, retained substantive suffixes. Dependencies stay
# inside one new question. Independent dimensions get isolated new questions.
PLAN={
'SK01':[('您大概是什么时候出生的？',['E1']),('您出生在哪个地方？',['E2']),('您记忆中的家乡是什么样子的？',['E4','E3.place','E3.period'])],
'SK02':[('您知道自己的名字有什么来历吗？',None)],
'SK03':[('您小时候主要跟谁一起生活？',['E1']),('小时候家里主要靠什么维持生活？',['E2']),('您有兄弟姐妹吗？',['E3']),('小时候家里人相处得怎么样？',['E4'])],
'SK04':[('从小到大，家里人通常怎样教导您？',None)],
'SK05':[('您会怎样形容自己的性格？',None)],
'SK06':[('想到自己这一生，您会用什么词来概括？',None)],
'CH01':[('您最早记得的一件事是什么？',['E1'])],
'CH02':[('小时候家里的生活条件怎么样？',['E1']),('小时候您平常一天是怎么过的？',['E2'])],
'CH03':[('小时候哪位亲人最疼爱您？',['E1','E3']),('童年时哪位亲人对您的影响比较深？',['E2'])],
'CH04':[('小时候有什么让您特别向往的活动或梦想？',['E1'])],
'CH05':[('童年有什么让您印象深刻的事？',None)],
'CH06':[('小时候邻里或亲友之间相处得怎么样？',['E1']),('童年时有没有一份人情温暖让您记到现在？',['E2'])],
'CH07':[('哪段童年经历影响了您后来的待人处事？',None)],
'GR01':[('您大概多大时开始上学的？',['E1']),('您的求学过程是怎样的？',['E2','E3'])],
'GR02':[('学生时代您会怎样形容自己的性格？',['E1']),('学生时代您的成绩大致怎么样？',['E2'])],
'GR03':[('求学时有没有一位对您影响很大的老师或同学？',None)],
'GR04':[('少年时您最大的烦恼是什么？',['E1']),('少年时什么事最让您快乐？',['E2'])],
'GR05':[('求学时家里的条件怎么样？',None)],
'GR06':[('青春期有没有一段让您感到迷茫或叛逆的日子？',None)],
'GR07':[('离开学校时您怎样设想以后的生活？',None)],
'WK01':[('您最初做的是什么工作？',None)],
'WK02':[('刚步入社会时您遇到过什么难题？',None)],
'WK03':[('您觉得青年时打拼的日子辛苦吗？',None)],
'WK04':[('工作初期有什么小成就让您感到骄傲？',None)],
'WK05':[('青年时有没有一个改变人生方向的选择？',None)],
'WK06':[('青年时您待人交友有什么原则？',['E1']),('青年时您收获过哪些珍贵的情谊？',['E2'])],
'WK07':[('您怎样形容中年时的忙碌程度？',None)],
'WK08':[('这一生您最专注坚持的是哪份工作？',None)],
'WK09':[('事业或生活中有没有一段您觉得处于低谷的经历？',None)],
'WK10':[('难熬的时候是什么支撑着您？',None)],
'WK11':[('中年时您觉得自己最大的收获是什么？',['E1']),('中年时您觉得自己发生了什么变化？',['E2'])],
'WK12':[('您曾经需要承担哪些家庭责任？',None)],
'WK13':[('这一生有什么工作成果让您引以为傲？',None)],
'FM01':[('您和伴侣是怎样认识的？',['E1','E2']),('您和伴侣平时是怎样相伴生活的？',['E3','E4'])],
'FM02':[('刚组建家庭时生活条件怎么样？',None)],
'FM03':[('婚姻中有没有一段需要磨合的日子？',None)],
'FM04':[('养育子女时什么让您觉得辛苦？',['E1']),('养育子女时什么让您觉得欣慰？',['E2'])],
'FM05':[('教育子女时您最看重什么？',None)],
'FM06':[('您觉得维系家庭和睦最重要的是什么？',None)],
'FM07':[('对您来说家人意味着什么？',None)],
'LT01':[('您现在的日子大致是怎样过的？',['E1']),('现在您最喜欢怎样安排日常生活？',['E2'])],
'LT02':[('和以前忙碌的时候相比，您现在的心态有什么变化？',None)],
'LT03':[('回头看您会怎样评价自己这一生？',None)],
'LT04':[('您想给晚辈留下什么人生忠告？',None)],
'LT05':[('您希望后人记住自己怎样的品格？',['E1']),('您希望后人记住自己的哪件往事？',['E2'])],
'LT06':[('对于以后的日子您最盼望什么？',None)],
'RV01':[('回头看哪项人生选择让您觉得选对了？',None)],
'RV02':[('这一生有没有让您放不下的遗憾？',None)],
'RV03':[('您有没有误会别人或被别人误会的经历？',None)],
'RV04':[('人生路上有什么让您觉得吃过亏的经历？',None)],
'RV05':[('您有没有放弃过的梦想或错过的机会？',None)],
'RV06':[('一路走来您最想感谢谁？',['E1']),('有没有谁让您觉得有所亏欠？',['E2'])],
'RV07':[('您觉得人这一生什么品质最重要？',None)],
'RV08':[('您觉得什么样的朋友值得深交？',['E1']),('在您看来什么样的事不必计较？',['E2'])],
'RV09':[('您怎样理解人生里的吃苦？',['E1']),('您怎样理解人生里的努力？',['E2']),('您怎样理解人生里的运气？',['E3'])],
'RV10':[('家庭幸福、事业成功、身体健康，您最看重什么？',None)],
'RV11':[('走到今天您对人生最想明白的一点是什么？',None)],
'RV12':[('您觉得人生最珍贵的财富是什么？',None)],
'RV13':[('这一生您最想感恩的一件事是什么？',None)],
'RV14':[('如果用一句话总结人生您会怎么说？',None)],
'RV15':[('您觉得自己这一生活得值得吗？',None)],
'RV16':[('还有什么您想留给后人的心里话？',None)],
}
# Required explanations remain required AFTER an entry answer; lack of an
# entry never activates an invented causal or example question.
AFTER={'SK02':('E2',['E3']),'SK04':('E1',['E3']), 'GR05':('E1',['E2']),
 'WK03':('E1',['E2']),'WK07':('E1',['E2']), 'FM01':('E1',['E2']),
 'FM01b':('E3',['E4']),'FM02':('E1',['E2']),'FM05':('E1',['E2']),'FM07':('E1',['E2'])}
def build():
 if (OUT/'manifest.json').exists():raise ValueError('candidate frozen; do not overwrite')
 OUT.mkdir(parents=True,exist_ok=True)
 for f in BASE.iterdir():
  if f.suffix in ('.js','.txt','.json') and f.name not in ('manifest.json','all-contract-boundaries.json'):
   shutil.copy2(f,OUT/f.name)
 c=json.loads((BASE/'contracts.json').read_text()); old=copy.deepcopy(c)
 assert set(PLAN)=={q['id'] for q in c['questions']}
 result=[]; mapping=[]
 for q in c['questions']:
  for idx,(wording,keep) in enumerate(PLAN[q['id']]):
   n=copy.deepcopy(q);n['id']=q['id']+('' if idx==0 else chr(97+idx));n['legacy_question_id']=q['id']
   n['main_question']=wording
   n['elements']=[copy.deepcopy(f) for f in q['elements'] if keep is None or f['id'].split('-',1)[1] in keep or f['requirement']=='optional' or f['activation'].get('premise_check')]
   for f in n['elements']:
    f['legacy_field_id']=f['id']; f['question_id']=n['id']
    if idx and (f['requirement']=='optional' or f['activation'].get('premise_check')): f['id']+=chr(97+idx)
   # Additional independent school-history question needs its own premise,
   # never the previous question's remembered "I did not attend school".
   if n['id']=='GR01b':
    template=next(x for x in old['questions'] if x['id']=='GR02')
    a=copy.deepcopy(template['elements'][0]);a.update(id='GR01-A1b',question_id=n['id'],legacy_field_id='GR01-E1')
    n['elements'].insert(0,a);n['premise']=copy.deepcopy(template['premise'])
    for f in n['elements']:
     if f['id'] in ('GR01-E2','GR01-E3'):f.update(required=True,requirement='required',activation={'always':True})
   if q['id']=='CH03':
    for f in n['elements']:
     if f['id']=='CH03-E3':f['activation']={'known':['CH03-E1']}
   n['entry_field_id']=next(f['id'] for f in n['elements'] if f['requirement']=='required')
   if n['id']=='CH01':
    f=next(f for f in n['elements'] if f['id']=='CH01-E1')
    f.update(label='本人早年记得的一件事情',usable_answer='至少一项本人早年记忆，能理解当时发生了什么；一句事情描述即可，不再把记忆标题和事情经过作为两个必答要素。可明确没有。')
   if n['id']=='CH04':
    f=next(f for f in n['elements'] if f['id']=='CH04-E1')
    f.update(label='童年喜欢的活动、爱好或向往的梦想',usable_answer='本人童年喜欢做的活动、爱好或小梦想任一即可；同一兴趣只提取一次，不要求另答梦想。可明确没有。')
   if n['id'] in AFTER:
    p,kids=AFTER[n['id']];parent=q['id']+'-'+p
    for f in n['elements']:
     if f['id'] in [q['id']+'-'+x for x in kids]: f.update(required=False,requirement='conditional',activation={'after_answer':[parent]})
   n['title']=next(f['label'] for f in n['elements'] if f['id']==n['entry_field_id'])
   # Ensure every template is a single interrogative; enum choices are one target.
   for f in n['elements']:
    if not f['activation'].get('never_ask'):
     assert f['question'].count('？')==1 and '?' not in f['question'],f['id']
   result.append(n);mapping.append({'old_question_id':q['id'],'new_question_id':n['id'],'main_question':wording,'entry_field_id':n['entry_field_id'],'fields':{f['id']:f['legacy_field_id'] for f in n['elements']}})
 c.update(version='full-interview-v2.0.0',questions=result,default_order=[n['new_question_id'] for oid in c['default_order'] for n in mapping if n['old_question_id']==oid])
 c['output_protocol']['model_field_contract_keys'].append('question_id')
 c['global_rules'].append('每道主问只发一个入口问句；相似目标合并，独立目标分题；递进要素只有入口得到本人回答后才激活，缺失才补问。')
 write(OUT/'contracts.json',c);write(OUT/'question-migration.json',mapping)
 write(OUT/'README.md','# 单问句题库 v2\n\n按用户2026-10-18指示进行业务重构，旧冻结版本和失败记录不变。当前为本地候选，未上线。\n')
 # Deliberate generic engine changes; stable field IDs preserve semantic guards.
 p=OUT/'engine.js';s=p.read_text()
 s=s.replace("const t=normalize(question||'');if(t===baseQuestion[fields[id]?.question_id])return false;", "const t=normalize(question||'');const owner=qmap[fields[id]?.question_id];if(t===baseQuestion[owner?.id])return owner?.entry_field_id===id;")
 s=s.replace("const app=map[qid+'-A1'];", "const premiseId=defs.find(f=>f.activation?.premise_check)?.id;const app=map[premiseId];")
 s=s.replace("qid+'-A1:absence_does_not_prove_premise'", "premiseId+':absence_does_not_prove_premise'")
 s=s.replace("qid+'-A1'", 'premiseId')
 s=s.replace("if(qid==='SK03'&&", "if(fields[atmosphereId]?.question_id===qid&&")
 s=s.replace("s.question===baseQuestion.SK03", "s.question===baseQuestion[fields[atmosphereId].question_id]")
 s=s.replace("if(a.known)return", "if(a.after_answer)return statesFor(a.after_answer).every(s=>['known','none'].includes(s));\n    if(a.known)return")
 write(p,s)
 p=OUT/'field-review.js';s=p.read_text().replace("dep.startsWith(payload.question_id+'-')",'payload.field_contract[dep]');write(p,s)
 p=OUT/'field-steps.js';s=p.read_text()
 s=s.replace("function frontier(payload", "const OWN=Object.fromEntries(require('./contracts.json').questions.flatMap(q=>q.elements.map(f=>[f.id,q.id])));\nfunction frontier(payload")
 s=s.replace("!id.startsWith(qid+'-')",'OWN[id]!==qid').replace("!fieldId.startsWith(qid+'-')",'OWN[fieldId]!==qid')
 s=s.replace("const premise=qid+'-A1';", "const premise=all.find(([,f])=>f.activation?.premise_check)?.[0];")
 write(p,s)
 for filename in ['extractor-prompt.txt','reviewer-prompt.txt']:
  p=OUT/filename
  write(p,'当前题库已按独立目标拆分。只处理 field_contract 中明确属于当前 question_id 的字段，字段编号前缀是历史编号，不能据此前缀猜测归属。主问只有一个入口目标。after_answer 表示父项 known 或明确 none 后才追问补充；未知、拒绝、暂停不强迫继续。不得用别题状态填本题。一个回答可主动包含本题后续要素，已答不重复问。\n'+p.read_text())
 return c,mapping
if __name__=='__main__':
 c,m=build();print(json.dumps({'questions':len(c['questions']),'fields':sum(len(q['elements']) for q in c['questions'])}))
