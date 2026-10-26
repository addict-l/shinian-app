"""Audit recorded calls against fixed bundles; export API wording verbatim."""
from pathlib import Path
from collections import Counter
import argparse,json,hashlib,html,sys,os

parser=argparse.ArgumentParser()
parser.add_argument('--backend',required=True);parser.add_argument('--evidence',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args();backend=Path(args.backend);root=Path(args.evidence);out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(backend))
for tag,bundle in [('V3J','v4d'),('V5F','v5f_listening')]:
    directory=backend/('app/ai/interview_runtime_v3j_'+bundle)
    os.environ['INTERVIEW_'+tag+'_RUNTIME_DIR']=str(directory)
    os.environ['INTERVIEW_'+tag+'_RUNTIME_MANIFEST_SHA256']=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
from app.services.contract_interview_state import v3j_runtime,v5f_runtime
from app.ai.contract_interview_v3j import _json
runtimes={r.pipeline:r for r in (v3j_runtime(),v5f_runtime())}
records=[];unique={};entries={};errors=[];failures={};locals_by_source={}
def walk(value,flow='v3j_v5f',path=''):
    if isinstance(value,dict):
        if value.get('pipeline') in runtimes:flow=value['pipeline']
        if value.get('question_id') and isinstance(value.get('deepen'),dict) and value.get('sources') and 'audit' in value:
            key=(flow,value['question_id'],value['sources'][0]['id'])
            old=locals_by_source.get(key)
            rank=lambda v:len(v.get('audit',[]))+len(v.get('deepen',{}).get('log',[]))
            if old is None or rank(value)>=rank(old):locals_by_source[key]=value
        if {'request_sha256','payload','response'}<=value.keys():
            rt=runtimes[flow];response=value['response'];matches=[]
            for stage in ('judge','verify','speaker','deepen'):
                prompt=getattr(rt,stage+'_prompt',None);params=getattr(rt,stage+'_params',None)
                if not prompt or not params:continue
                digest=hashlib.sha256(_json({'runtime':rt.manifest_sha256,'stage':stage,'params':params,
                    'system':prompt,'user':value['payload']}).encode()).hexdigest()
                if digest==value['request_sha256']:matches.append((stage,params))
            if len(matches)!=1:errors.append({'where':path,'error':'request digest mismatch','flow':flow})
            else:
                stage,params=matches[0];entries[value['request_sha256']]={'stage':stage,'flow':flow}
                if response.get('ok'):
                    rid=response.get('response_id')
                    if not rid or response.get('params')!=params or params['thinking']!='disabled' or 'reasoning_effort' in params or response.get('response_model')!='deepseek-v4-pro':errors.append({'where':path,'error':'model/params/id mismatch'})
                    identity={'stage':stage,'flow':flow,'params':params,'request_sha256':value['request_sha256'],'response_id':rid,'response_model':response.get('response_model'),'usage':response.get('usage')}
                    if rid in unique and unique[rid]!=identity:errors.append({'where':path,'error':'response id reused with different metadata'})
                    unique[rid]=identity
                else:failures[value['request_sha256']]={'stage':stage,'flow':flow,'error':response.get('error')}
        for k,v in value.items():walk(v,flow,path+'/'+k)
    elif isinstance(value,list):
        for i,v in enumerate(value):walk(v,flow,path+'/'+str(i))

for p in sorted(list((root/'production-records').glob('v5f_*.json'))+list((root/'interactive-candidate').glob('v5f_*.json'))):
    x=json.loads(p.read_text())
    if 'events' not in x:continue
    walk(x,path=p.name)
    audit_path=p.with_name(p.stem+'-audit.json')
    actual=json.loads(audit_path.read_text()) if audit_path.exists() else {}
    if actual:walk(actual,path=p.stem+'-audit')
    module=x.get('module')
    phase=(actual.get('guide') or {}).get('phase') if module else (actual.get('life') or {}).get('status')
    draft_path=p.with_name(p.stem+'-draft.json')
    item={'case':x['case'],'module':module,'passed':x['passed'],'setup':x['setup'],
        'respondent':x.get('input_method','fixed synthetic acceptance utterances; not a live human or live AI respondent'),
        'respondent_type':x.get('respondent_type','fixed_synthetic'),
        'interviewer':'real DeepSeek v4-pro via official production HTTPS/MySQL; no provider fault injection',
        'final_backend_phase':phase,'natural_completion':phase in ('review','saved','confirmed','finished','module_review'),
        'sample_cutoff':phase not in ('review','saved','confirmed','finished','module_review'),
        'memory_generated':draft_path.exists(),'events':x['events'],'checks':x['checks'],'error':x.get('error'),
        'original_record':p.name}
    if draft_path.exists():item['draft']=json.loads(draft_path.read_text())['memory']
    records.append(item)

def saved_payloads(value):
    if isinstance(value,dict):
        found=[value['payload']] if {'request_sha256','payload','response'}<=value.keys() else []
        return found+[x for v in value.values() for x in saved_payloads(v)]
    if isinstance(value,list):return [x for v in value for x in saved_payloads(v)]
    return []
missing=[]
for key,local in locals_by_source.items():
    retained=saved_payloads(local['audit'])
    for log in local['deepen'].get('log',[]):
        if log.get('input') and log['input'] not in retained:
            missing.append({'pipeline':key[0],'question_id':key[1],'source_id':key[2],
                'reason':log['reason'],'raw_preserved':log.get('raw') is not None,
                'request_digest_and_response_envelope_missing':True})
audit={'passed':not errors and not missing,'retained_calls_verified':not errors,'full_call_trace_complete':not missing,
    'missing_deepen_call_entries':missing,'errors':errors,'unique_successful_response_ids':len(unique),
    'successful_by_stage':dict(Counter(v['stage'] for v in unique.values())),
    'successful_by_flow':dict(Counter(v['flow'] for v in unique.values())),
    'unique_request_digests':len(entries),'recorded_failed_provider_calls':list(failures.values()),
    'calls':sorted(unique.values(),key=lambda x:(x['flow'],x['stage'],x['response_id']))}
(out/'provider-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
assert not errors,json.dumps(errors[:5],ensure_ascii=False)
final=records
verification=json.loads((root/'production-verification.json').read_text())
summary={'version':'V6','code_sha':'8799b52b4d7590ea522c6798c364fd2fa451226a',
 'source_kind':'fixed_git_commit','production_switched':True,'quality_acceptance_passed':False,
 'final_cases':len(final),'final_cases_passed':sum(x['passed'] for x in final),
 'final_checks':sum(len(x['checks']) for x in final),'final_failed_checks':sum(not c['passed'] for x in final for c in x['checks']),
 'production_verification':verification,
 'initial_failed_attempts_retained':1,'initial_failure':'parallel synthetic person opening caused MySQL deadlock; same request retried; concurrency defect not fixed',
 'provider_audit':{k:v for k,v in audit.items() if k!='calls'},
 'production':json.loads((root/'final-runtime-verification.json').read_text()),
 'deployment':json.loads((root/'deployment.json').read_text()),
 'holdout_used_for_tuning':False,'live_actor_cases':0,
 'respondent':'fixed synthetic acceptance inputs; no real elder or live AI actor',
 'candidate_dialogues_are_separate':True,
 'all_final_functional_checks_passed':all(x['passed'] for x in final) and audit['passed'],
 'scope':'Official HTTPS, independent synthetic family, actual API setup, no production DB seeding; draft-generation calls are not included in this interview-provider audit'}
(out/'verification-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(out/'原样问答.json').write_text(json.dumps({'metadata':summary,'cases':records},ensure_ascii=False,indent=2)+'\n')
final.sort(key=lambda x:(x['case']!='v5f_V6_PROD_work_retry',x['case']!='v5f_V6_PROD_full_skeleton',x['case']))
intro='V6 正式云端原样问答\n生产已切换 V6 / 8799b52 / v3j_v5f，模型 DeepSeek v4-pro、thinking disabled。受访回答为固定合成文本，不是真人或实时 AI 老人。\n首次并发入口曾死锁503，同人物同请求重试恢复；初次失败保留，并发问题未宣称修复。\n'
lines=[intro];cards=[];expected=[]
for x in final:
    title={'v5f_V6_PROD_work_retry':'V6 生产｜工作故事、超时重试、草稿保存',
 'v5f_V6_PROD_full_skeleton':'V6 生产｜完整人生骨架',
 'v5f_V6_PROD_partial_memory':'V6 生产｜部分记不清，接着讲',
 'v5f_V6_PROD_sensitive':'V6 生产｜敏感题只追问一次',
 'v5f_V6_PROD_short_cause':'V6 生产｜明确原因短答',
 'v5f_V6_PROD_S04_only':'V6 生产｜没有别的要补充了',
 'v5f_V6_PROD_S04_actor_phrase':'V6 生产｜原老人模拟结束语回归',
 'v5f_V6_PROD_S04_addition':'V6 生产｜先补充再结束',
 'v5f_regression_C01_0':'V6 生产｜过去的累不暂停',
 'v5f_regression_C01_1':'V6 生产｜否定累不暂停',
 'v5f_regression_C01_2':'V6 生产｜他人不想说不拒答',
 'v5f_regression_C01_3':'V6 生产｜本人累了暂停、继续',
 'v5f_regression_C02_partial':'V6 生产｜已答后不想展开',
 'v5f_regression_C02_empty':'V6 生产｜整题无内容拒答跳过'}.get(x['case'],x['case'])
    state=('实时模拟 · 待审阅' if x['respondent_type']=='live_agent_roleplay' else '功能检查通过') if x['passed'] else '发现问题／目标路径未到达'
    lines.extend(['\n'+title+' · '+state,'实际阶段：'+str(x['final_backend_phase'])+'；自然完成：'+str(x['natural_completion'])+'；采样截断：'+str(x['sample_cutoff'])])
    qa=[]
    for e in x['events']:
        label='采访者' if e['role']=='interviewer' else ('老人（实时子代理模拟）' if x['respondent_type']=='live_agent_roleplay' else '受访回答（固定合成）')
        lines.extend([label+'：',e['text']]);expected.append(e['text'])
        qa.append('<div class="turn '+e['role']+'"><small>'+label+'</small><pre>'+html.escape(e['text'])+'</pre></div>')
    if x.get('draft'):
        lines.extend(['实际生成的草稿：',x['draft']['summary']]);expected.append(x['draft']['summary'])
        qa.append('<details><summary>实际生成的草稿</summary><pre>'+html.escape(x['draft']['summary'])+'</pre></details>')
    cards.append('<section id="'+html.escape(title)+'"><h2>'+html.escape(title)+' <span>'+state+'</span></h2><p class="meta">阶段 '+str(x['final_backend_phase'])+' · 自然完成 '+str(x['natural_completion'])+' · 采样截断 '+str(x['sample_cutoff'])+'</p>'+''.join(qa)+'</section>')
text='\n'.join(lines)+'\n';(out/'云端故事题深挖问答.txt').write_text(text)
page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V6 正式云端原样问答</title><style>\nbody{margin:0;background:#f5f2eb;color:#292d29;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;line-height:1.7}main{max-width:900px;margin:auto;padding:42px 22px}h1{font-size:29px;line-height:1.4}h2{font-size:17px;overflow-wrap:anywhere}header{padding-bottom:25px}.notice{background:#fff0df;border-left:4px solid #aa6530;padding:16px 20px}section{background:#fffefb;border:1px solid #deded2;border-radius:14px;padding:25px;margin:26px 0}h2 span{font-size:12px;color:#74523d}p.meta,small{color:#738074;font-size:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;margin:5px 0}.turn{padding:14px 18px;margin:12px 0;border-radius:9px;background:#eef2eb}.respondent{margin-left:40px;background:#f3ece0}.interviewer{margin-right:40px}details{border-top:1px solid #ddd;padding-top:12px}summary{cursor:pointer}a{color:#50634f}\n</style><main><header><p>拾年 · V6 · 2026-10-27</p><h1>V6 正式云端<br>原样采访问答</h1><div class="notice"><b>生产已切换 V6。</b><br>独立测试家庭，通过正式 HTTPS 实际运行；固定合成受访回答，采访者为真实 DeepSeek v4-pro、thinking disabled。没有使用数据库夹具准备题目。</div><p>最终14个场景功能检查通过，首次并发入口503另保留：MySQL死锁回滚后，同人物同请求重试恢复，并发问题未修复。既有入口代码未在V6改动，但未进行旧镜像同负载对照，不能仅凭此断言非回归。</p><p>下列原话未经润色。工作段完成实际草稿生成、确认和重复确认；骨架完成核对与确认。每段实际阶段单独列出。仍有第三方亲历选点、主观评价和补充节奏问题，正式三轮质量门槛未宣称通过。上轮实时老人子代理对话仍在候选证据包中。</p></header>'+''.join(cards)+'</main></html>'
(out/'云端故事题深挖问答.html').write_text(page)
assert all(html.escape(t) in page and t in text for t in expected)
roundtrip={'verbatim_texts_checked':len(expected),'html_txt_json_verbatim':True,'original_case_records_preserved':True}
(out/'export-integrity.json').write_text(json.dumps(roundtrip,indent=2)+'\n')
print(json.dumps({**summary,'provider_audit':{k:v for k,v in summary['provider_audit'].items() if k!='errors'}},ensure_ascii=False))
