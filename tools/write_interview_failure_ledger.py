#!/usr/bin/env python3
"""Read-only failure ledger from an already-scored frozen run, never model input."""
import argparse
import json
from pathlib import Path

def load(p):return json.loads(p.read_text())
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    run=args.run.resolve();scores=load(run/'scores.json');dataset=load(run/'dataset.json');defs=load(run/'contracts.snapshot.json')
    bycase={c['id']:c for c in dataset['cases']};people={n['id']:n for n in dataset['narrators']};rows=[]
    for row in scores['rows']:
        if row['execution']=='unexecuted' or row.get('passed'):continue
        case=bycase[row['case_id']];turn=case['turns'][row['turn']];folder=run/'cases'/row['case_id']/('turn-%03d'%row['turn']);record=load(folder/'result.json')
        result=record.get('result',{});field_failures=[]
        for f in row.get('fields',[]):
            if f['passed']:continue
            field_failures.append({'field_id':f['field_id'],'label':defs['fields'][f['field_id']]['label'],
                'failed_dimensions':[c['dimension'] for c in f['checks'] if not c['passed']],
                'actual':f['actual'],'expected':f['expected'],'gap_question':defs['fields'][f['field_id']]['question'],
                'missed':f.get('missed'),'false_accepted':f.get('false_accept'),
                'required_stage_not_grounded':f['actual'].get('provenance')=='required_stage_not_grounded'})
        rows.append({'case_id':row['case_id'],'narrator_id':row['narrator_id'],'name':people[row['narrator_id']]['name'],
            'question_id':row['question_id'],'turn':row['turn'],'execution':row['execution'],
            'main_question':defs['questions'][row['question_id']],
            'actual_original_question':turn['source']['question'],'source_url':turn['source'].get('source_url'),
            'frozen_source_id':turn['source']['id'],'protocol_errors':result.get('errors',[]),
            'semantic_rejections':result.get('semantic_rejections',[]),'field_failures':field_failures,
            'followup':row.get('followup'),'actual_call_response_files':[str(p.relative_to(run)) for p in sorted(folder.glob('response-*.json'))],
            'internal_repairs':record.get('internal_repairs',0),'raw_result':str(folder/'result.json')})
    report={'scope':'Observed failures under this frozen gold, not proof every discrepancy is a model bug. Read-only derived ledger; never supplied to extractor or reviewer.',
        'run':str(run),'frozen_model':scores['model'],'fully_executed':scores['overall']['unexecuted']==0,
        'overall':scores['overall'],'failure_rows':rows}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    md=args.out.with_suffix('.md');lines=['# 冻结失败记录与缺口索引','',f'批次：{run.name}；模型：{scores["model"]}。',
        '', '本表按原冻结金标准展示未通过项，可能含协议问题或待复核标注；不改写旧分数，也不提供给提取模型。'
        '字段预置小问仅说明缺口意图；实际流程由代码根据本题状态选择，已讲清材料但时期未明时只澄清时期。',
        '', '| 题例 / 本轮 | 未过字段 | 协议错误 | 实际动作 / 目标 | 冻结预期动作 / 目标 |',
        '| --- | --- | --- | --- | --- |']
    for r in rows:
        follow=r['followup'] or {};actual=f'{follow.get("actual_decision",r["execution"])} / {follow.get("actual_target")}';expected=follow.get('expected',{})
        label=r['case_id']+' / '+str(r['turn'])
        lines.append('| ['+label+']('+r['raw_result']+') | '+', '.join(f['field_id']+':'+','.join(f['failed_dimensions']) for f in r['field_failures'])+' | '+', '.join(r['protocol_errors'])+' | '+actual+' | '+str(expected.get('decisions'))+' / '+str(expected.get('targets'))+' |')
    lines += ['', '逐项原话、目标、小问题与失败维度见同名JSON；全部原始模型响应仍在各题例目录。','']
    md.write_text('\n'.join(lines));print(json.dumps({'failure_rows':len(rows),'json':str(args.out),'markdown':str(md)},ensure_ascii=False))
if __name__=='__main__':main()
