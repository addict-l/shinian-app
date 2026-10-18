#!/usr/bin/env python3
"""Render the canonical business migration and freeze before model execution."""
import json,hashlib,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'docs/prototypes/full-interview-v2/single-question-v2'
if (R/'manifest.json').exists():raise ValueError('already frozen; do not rewrite documents or runtime')
C=json.loads((R/'contracts.json').read_text())
BASELINE=ROOT/'docs/interview-development-baseline.md'
HISTORY=ROOT/'docs/history/interview-development-baseline-before-single-question-20261018.md'
if not HISTORY.exists():
 HISTORY.parent.mkdir(parents=True,exist_ok=True);HISTORY.write_bytes(BASELINE.read_bytes())
groups={'SK':'开篇定调骨架','CH':'家乡与童年','GR':'求学与成长','WK':'工作与劳动','FM':'家庭生活','LT':'后来的生活','RV':'人生回望'}
header='''# 拾年采访业务基准：单问句题库 v2

更新：2026-10-18。用户已明确要求：所有主问改为单个问句；相似问句合并为同一目标，独立问句拆题，递进问句作为入口回答后的缺项追问。当前候选仅本地完成与真实 DS 测试，生产仍为旧题库；未通过本次改版验收，不自动迁移已有采访记录。

本次从 62 个旧题组整理为 83 道入口问题。六模块保留，开篇骨架为 11 道；每题只发送一个入口目标，不以只有一个问号代替语义单一。旧题号保留，新拆分题加 b/c/d 后缀；字段使用稳定历史编号，归属以合同 question_id 为准，不能用编号前缀猜测。

本文件是当前业务依据。旧版完整规则、原题、历史结果见[改版前存档](history/interview-development-baseline-before-single-question-20261018.md)，旧字段判据中没有被本次明确修改的部分继续适用。可执行合同与每题字段对应见[候选合同](prototypes/full-interview-v2/single-question-v2/contracts.json)，[旧题映射](prototypes/full-interview-v2/single-question-v2/question-migration.json)。

## 本次规则

1. 每题独立，切题清空本题状态，不复用其他题的回答。拆分后的题也独立；相同材料在离线测试中重新输入，不等同线上跨题复用。
2. 入口只发一问。回答可主动覆盖本题多个要素；后续只问尚缺的一个必要目标。父项未答时，不先问原因、影响、经历细节。明确未知、拒绝或暂停时停止相应分支。
3. CH01 的记忆与发生的事合成一个可理解的早年事件；CH04 的喜欢做的事与爱好/小梦想合成一个兴趣目标。保留一项充分原话即可，不要求从相同内容制造两个答案。其他独立目标拆题，必要信息没有因拆题删除。
4. 同一目标的主体、时期、关联、原话证据仍受代码约束。未知、明确没有、不适用、拒绝、以后再讲分别记录。不能从题干推事实，不能从伴侣抱怨推实际处理行为。
5. 条件补充仍是必要的完善目标，只在表中条件成立且该项缺失时追问。可选补充不影响完成。每题资料足够不等于已经确认保存；信息有限可收口另行标记。
6. 所有 DS 提取、复核、修复、回归调用必须关闭思考模式，不传 reasoning_effort。历史失败和标注争议全部保留。
7. 新题库的真实材料回归与旧 62 题成绩口径不同，分别报告人数、新题覆盖、题例、检查点及失败。公开访谈回放不冒充受访者对新问法的实时回答。连续三轮 >95% 的正式验收要求保留；业务版本变化重新计数。本次按用户新要求先跑一组并报告。

## 默认顺序

骨架 → 家乡与童年 → 求学与成长 → 工作青年段（WK01–WK06）→ 家庭生活 → 工作中年段（WK07–WK13）→ 回望前段（RV01–RV12）→ 后来的生活 → 收尾（RV13–RV16）。同一旧题拆开的子题紧邻，按下表顺序。年龄作为阶段参考，不硬套年龄段。

## 全部入口问题

'''
catalog=header
for prefix,title in groups.items():
 qs=[q for q in C['questions'] if q['id'].startswith(prefix)]
 catalog+=f'### {title}（{len(qs)}题）\n\n| 题号 | 入口单问句 | 旧题组 |\n| --- | --- | --- |\n'
 for q in qs:catalog+=f"| {q['id']} | {q['main_question']} | {q['legacy_question_id']} |\n"
 catalog+='\n'
full=catalog+'## 每题需要的要素与缺项追问\n\n'
for q in C['questions']:
 full+=f"### {q['id']} {q['title']}\n\n入口：{q['main_question']}\n\n| 要素 | 生效条件 | 回答标准 | 缺失时的一问 |\n| --- | --- | --- | --- |\n"
 for f in q['elements']:
  a=f['activation'];condition='入口必要项' if f['id']==q['entry_field_id'] else '必要项'
  if f['requirement']=='optional':condition='可选，不自动追问'
  elif a.get('never_ask'):condition='仅记录输入，不自动询问'
  elif 'after_answer' in a:condition='、'.join(a['after_answer'])+' 已回答或明确没有后'
  elif 'known' in a:condition='、'.join(a['known'])+' 已回答后'
  elif 'any_known' in a:condition='、'.join(a['any_known'])+' 任一已回答后'
  elif a.get('premise_check'):condition='本题未能确认经历适用性时'
  elif f['requirement']=='conditional':condition='条件：'+json.dumps(a,ensure_ascii=False)
  full+=f"| {f['id']}：{f['label']} | {condition} | {f['usable_answer'].replace('|','／')} | {f['question'] or '不主动问'} |\n"
 full+='\n完成：入口及已激活的必要补充有可用回答或允许的明确否定即可；未知、拒绝、以后讲保留信息有限状态，停止对应追问；不要求可选内容。\n\n'
BASELINE.write_text(full)
(ROOT/'docs/interview-question-bank-single-sentence-v2.md').write_text(catalog)
(R/'contracts.md').write_text(full)
manifest={'version':C['version'],'parent_version':'full-interview-v1.34.0','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'engine_file':'engine.js','prompt_file':'extractor-prompt.txt','question_context_mode':'independent','experiment':'User-authorized semantic question split/merge and progressive follow-up; separate new gold projection. No person-specific prompts. Thinking disabled.','acceptance':'pending','files':{}}
for p in sorted(R.rglob('*')):
 if p.is_file() and p.name!='manifest.json':manifest['files'][str(p.relative_to(R))]=hashlib.sha256(p.read_bytes()).hexdigest()
(R/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'questions':len(C['questions']),'groups':{k:sum(q['id'].startswith(k) for q in C['questions']) for k in groups}}))
