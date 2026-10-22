#!/usr/bin/env python3
"""Write failures-detail.md for a run: source, field contract, gold, actual, engine notes.

  python tools/interview_eval/explain.py RUN_DIR [--all]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def short(obj, n=600):
    text = json.dumps(obj, ensure_ascii=False)
    return text if len(text) <= n else text[:n] + '…'


def main():
    run = Path(sys.argv[1])
    show_all = '--all' in sys.argv
    scores = common.load(run / 'scores.json')
    data = common.load(run / 'dataset.json')
    cases = {c['id']: c for c in data['cases']}
    out = [f"# 失败详情 {run.name}", '']
    for row in scores['rows']:
        if row['passed'] and not show_all:
            continue
        case = cases[row['case_id']]
        turn = case['turns'][row['turn']]
        rec_path = run / 'cases' / row['case_id'] / ('turn-%03d.json' % row['turn'])
        rec = common.load(rec_path) if rec_path.exists() else {}
        payload = rec.get('payload', {})
        out.append(f"## {row['case_id']} / t{row['turn']} — {case['question_id']} {payload.get('main_question', '')}  {'PASS' if row['passed'] else 'FAIL'}")
        for t in case['turns'][:row['turn'] + 1]:
            out.append(f"- 原问：{t['source'].get('question')}")
            out.append(f"- 回答（{t['source']['id']}）：{t['source']['text']}")
        if case.get('annotation_note'):
            out.append(f"- 标注说明：{case['annotation_note']}")
        contract = payload.get('field_contract', {})
        for f in row.get('fields', []):
            fid = f['field_id']
            c = contract.get(fid, {})
            mark = 'ok' if f['passed'] else 'FAIL ' + ','.join(x['dimension'] for x in f['checks'] if not x['passed'])
            out.append(f"- **{fid}** {c.get('label', '')}（{c.get('requirement', '')}）[{mark}]")
            if not f['passed'] or show_all:
                out.append(f"  - 标准：{c.get('usable_answer', '')}")
                exp = {k: v for k, v in f['expected'].items() if k in ('state', 'states', 'value_groups', 'evidence', 'relation_evidence', 'scope', 'facts', 'state_requirements')}
                out.append(f"  - 金标准：{short(exp, 900)}")
                act = {k: v for k, v in f['actual'].items() if k in ('state', 'value', 'evidence', 'scope', 'clarifications', 'links')}
                out.append(f"  - 实际：{short(act, 900)}")
        if row.get('followup'):
            fu = row['followup']
            out.append(f"- 追问：实际 {fu['actual_decision']}/{fu['actual_target']}；预期 {fu['expected'].get('decisions')}/{fu['expected'].get('targets')}")
        result = rec.get('record', {}).get('result', {})
        notes = {k: result.get(k) for k in ('errors', 'semantic_rejections', 'optional_errors') if result.get(k)}
        if notes:
            out.append(f"- 引擎：{short(notes, 900)}")
        if row.get('execution') != 'evaluated':
            out.append(f"- 执行：{short(row.get('error'))}")
        out.append('')
    (run / 'failures-detail.md').write_text('\n'.join(out) + '\n', encoding='utf-8')
    print(run / 'failures-detail.md')


if __name__ == '__main__':
    main()
