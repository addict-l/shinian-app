"""Audit recorded calls against fixed bundles; export API wording verbatim."""
from pathlib import Path
from collections import Counter
import argparse,json,hashlib,html,sys,os

parser=argparse.ArgumentParser()
parser.add_argument('--backend',required=True);parser.add_argument('--evidence',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args();backend=Path(args.backend);root=Path(args.evidence);out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(backend))
for tag,bundle in [('V3J','v4d'),('V5F','v5f')]:
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

for p in sorted((root/'real-candidate').glob('v5f_*.json')):
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
        'respondent':'fixed synthetic acceptance utterances; not a live human or live AI respondent',
        'interviewer':'real DeepSeek v4-pro via candidate HTTPS/MySQL; fault injection separately marked',
        'final_backend_phase':phase,'natural_completion':phase in ('saved','confirmed','finished','module_review'),
        'sample_cutoff':phase not in ('saved','confirmed','finished','module_review'),
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
tool_attempts={'v5f_WK01_short_first','v5f_full_skeleton','v5f_FM01_provider_fail'}
final=[x for x in records if x['case'] not in tool_attempts]
summary={'candidate_passed':False,'production_switched':False,'quality_acceptance_passed':False,
    'candidate_code_sha':'20013ab6339b4f2c34205b3bcda5318bb4234631',
    'checked_checkout_sha':'9915707504d3edc8e813961c0e958b14ea068313',
    'captures':len(records),'final_cases':len(final),'final_cases_passed':sum(x['passed'] for x in final),
    'final_cases_failed':[x['case'] for x in final if not x['passed']],
    'retained_initial_harness_attempts':sorted(tool_attempts),
    'final_checks':sum(len(x['checks']) for x in final),'final_failed_checks':sum(not c['passed'] for x in final for c in x['checks']),
    'provider_audit':{k:v for k,v in audit.items() if k!='calls'},
    'main_issue':'WK01-E2: repetition_is_not_explanation discards a sentence containing explicit cause and work; unnecessary follow-up',
    'additional_issue':'first-answer deepen failure falls back correctly but drops saved deepen request/response envelope from the final audit',
    'holdout_used_for_tuning':False,'production':json.loads((root/'production-unchanged.json').read_text())}
(out/'verification-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(out/'原样问答.json').write_text(json.dumps({'metadata':summary,'cases':records},ensure_ascii=False,indent=2)+'\n')
final.sort(key=lambda x:(x['case']!='v5f_WK01_short_ready',x['case']))
intro='故事题深挖 v5f｜云端候选验证\n候选未通过，未发布生产。生产仍为 a1ecee6 / v3j_v4d。另有一次故障回退漏归档完整调用摘要。\n采访者为真实 DeepSeek v4-pro（thinking disabled）；受访回答是固定合成验收文本，不是真人访谈。候选使用独立 MySQL、媒体目录和已验证证书的 HTTPS。\n'
lines=[intro];cards=[];expected=[]
for x in final:
    title=x['case'];state='通过' if x['passed'] else '发现问题'
    lines.extend(['\n'+title+' · '+state,'实际阶段：'+str(x['final_backend_phase'])+'；自然完成：'+str(x['natural_completion'])+'；采样截断：'+str(x['sample_cutoff'])])
    qa=[]
    for e in x['events']:
        label='采访者' if e['role']=='interviewer' else '受访回答（合成）'
        lines.extend([label+'：',e['text']]);expected.append(e['text'])
        qa.append('<div class="turn '+e['role']+'"><small>'+label+'</small><pre>'+html.escape(e['text'])+'</pre></div>')
    if x.get('draft'):
        lines.extend(['实际生成的草稿：',x['draft']['summary']]);expected.append(x['draft']['summary'])
        qa.append('<details><summary>实际生成的草稿</summary><pre>'+html.escape(x['draft']['summary'])+'</pre></details>')
    cards.append('<section id="'+html.escape(title)+'"><h2>'+html.escape(title)+' <span>'+state+'</span></h2><p class="meta">阶段 '+str(x['final_backend_phase'])+' · 自然完成 '+str(x['natural_completion'])+' · 采样截断 '+str(x['sample_cutoff'])+'</p>'+''.join(qa)+'</section>')
text='\n'.join(lines)+'\n';(out/'云端故事题深挖问答.txt').write_text(text)
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>故事题深挖 · 云端候选问答</title><style>
body{margin:0;background:#f5f2eb;color:#292d29;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;line-height:1.7}main{max-width:900px;margin:auto;padding:42px 22px}h1{font-size:29px;line-height:1.4}h2{font-size:17px;overflow-wrap:anywhere}header{padding-bottom:25px}.notice{background:#fff0df;border-left:4px solid #aa6530;padding:16px 20px}section{background:#fffefb;border:1px solid #deded2;border-radius:14px;padding:25px;margin:26px 0}h2 span{font-size:12px;color:#74523d}p.meta,small{color:#738074;font-size:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;margin:5px 0}.turn{padding:14px 18px;margin:12px 0;border-radius:9px;background:#eef2eb}.respondent{margin-left:40px;background:#f3ece0}.interviewer{margin-right:40px}details{border-top:1px solid #ddd;padding-top:12px}summary{cursor:pointer}a{color:#50634f}
</style><main><header><p>拾年 · 20013ab · 2026-10-26–27</p><h1>故事题深挖<br>云端候选原样问答</h1><div class="notice"><b>候选未通过，生产未切换。</b><br>已交代入行原因仍重复追问的问题，附在第一段；另有一次故障回退漏归档调用摘要。生产保持 a1ecee6 / v3j_v4d。</div><p>采访者：真实 DeepSeek v4-pro，thinking disabled。受访回答：固定合成验收文本，不是真人或实时 AI 受访者。环境：独立 MySQL、独立媒体、真实 HTTPS；故障注入场景单独标明。</p><p>采样结束时的实际阶段逐段列出。草稿已保存与控制场景的中途截断分别标注。初次测试工具中断及全部 API 状态保留在原始证据包中。以下话语未经润色。</p></header>'''+''.join(cards)+'</main></html>'
(out/'云端故事题深挖问答.html').write_text(page)
assert all(html.escape(t) in page and t in text for t in expected)
roundtrip={'verbatim_texts_checked':len(expected),'html_txt_json_verbatim':True,'original_case_records_preserved':True}
(out/'export-integrity.json').write_text(json.dumps(roundtrip,indent=2)+'\n')
print(json.dumps({**summary,'provider_audit':{k:v for k,v in summary['provider_audit'].items() if k!='errors'}},ensure_ascii=False))
