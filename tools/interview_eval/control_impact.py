"""0-token impact check of the elder-signal, ending-rule and supplement readings (C01-C03 of 2026-10-23).

Compares the backend speaking-layer rules of a base commit (read with `git show`, default d6b11f3) with the
working tree's `cloud-deployment/backend/app/ai/interview_speaker.py` on every recorded elder answer:

- elder_signal: old vs new on every distinct answer;
- decide (ending rules, follow-up caps off so only the signal / engine-decision rules count) on every judged
  answer of the simulated runs (their saved judge summaries);
- the supplement reading: the old exact phrases of contract_guided_interview.turn vs supplement_end, for every
  answer that came right after the draft sentence, and the answers elsewhere the new reading would take as an
  ending if they came after it.

Data (not in Git): `<runs>/sim-*/sessions/*.json`, `<runs>/datasets/full45.json` (SHINIAN_EVAL_RUNS /
SHINIAN_EVAL_HOME, as common.py), and optionally the raw records of the cloud QA of 2026-10-23
(`--cloud <dir with skeleton.json childhood.json work.json unmarried.json>`, from 问答与原始核验.zip/原始记录/).
No model call. Output is deterministic (sorted input files).

  python3 tools/interview_eval/control_impact.py --cloud <dir>/原始记录 > impact.txt
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402

ROOT = common.ROOT
SPEAKER = 'cloud-deployment/backend/app/ai/interview_speaker.py'
BASE = 'd6b11f349b9a68ab87b4baf886ea8497c371f137'
# The fixed phrases contract_guided_interview.turn takes as "nothing more" after the draft offer (both flows before C03).
OLD_SUPPLEMENT = re.compile(r'(?:没有(?:了|补充了)?|没有别的补充了|先保存|确认保存|保存吧|就这些)[。！!\s]*')
DRAFT = '这段可以先整理成草稿了。您还有什么想补充的吗？'
CFG = {'signal_close': True, 'followup_cap': 99, 'same_target_cap': 99, 'stop_after_unknown_once_asked': 99}


def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def old_speaker(base, tmp):
    source = subprocess.run(['git', '-C', str(ROOT), 'show', f'{base}:{SPEAKER}'], check=True, capture_output=True).stdout
    path = Path(tmp) / 'old_interview_speaker.py'
    path.write_bytes(source)
    return module_from(path, 'old_interview_speaker')


def collect(runs, cloud):
    items = []  # (source, where, text, judge summary or None, right after the draft sentence)
    for run in sorted(runs.glob('sim-*')):
        if not (run / 'sessions').is_dir():
            continue
        for path in sorted((run / 'sessions').glob('*.json')):
            s = common.load(path)
            for ep in s['episodes']:
                last_sys = None
                for m in ep['messages']:
                    if m['role'] == 'system':
                        last_sys = m
                    elif not m.get('scripted'):
                        after = bool(last_sys and (last_sys.get('kind') == 'supplement' or (last_sys.get('text') or '').endswith(DRAFT)))
                        items.append(('sim', f'{run.name}/{s["name"]}/{ep["qid"]}', m['text'], m.get('judge'), after))
    full45 = runs / 'datasets/full45.json'
    if full45.exists():
        for case in common.load(full45)['cases']:
            for t in case['turns']:
                items.append(('full45', case['id'], t['source']['text'], None, False))
    if cloud:
        for path in sorted(Path(cloud).glob('*.json')):
            rec = common.load(path)
            prev = None
            for e in rec['events']:
                if e['role'] == 'respondent':
                    items.append(('cloud', f'{path.stem}/{e.get("question_id")}', e['text'], None, bool(prev and prev.endswith(DRAFT))))
                elif e['role'] == 'interviewer':
                    prev = e['text']
    return items


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--base', default=BASE, help='commit whose interview_speaker.py is the "old" rules')
    ap.add_argument('--runs', default=str(common.RUNS), help='evaluation runs directory (sim-* and datasets/full45.json)')
    ap.add_argument('--cloud', help='directory of the cloud QA raw records (原始记录/*.json)')
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / 'cloud-deployment/backend'))
    from app.ai import interview_speaker as new  # noqa: E402
    with tempfile.TemporaryDirectory() as tmp:
        old = old_speaker(args.base, tmp)
    items = collect(Path(args.runs), args.cloud)

    uniq = {}
    for src, where, text, judge, after in items:
        uniq.setdefault((src, text), []).append((where, judge, after))
    print(f'base {args.base}; answers {len(items)}; distinct per source {dict(sorted(Counter(k[0] for k in uniq).items()))}; '
          f'distinct total {len(uniq)}')

    sig_changes, dec_changes, sup_rows, judged = [], [], [], 0
    for (src, text), occ in uniq.items():
        o, n = old.elder_signal(text), new.elder_signal(text)
        if o != n:
            sig_changes.append((src, text, o, n, occ[0][0], len(occ)))
        for where, judge, _ in occ:
            if judge:
                judged += 1
                a = old.decide(CFG, judge, {'followups': 0, 'ask_counts': {}, 'prev_eff': {}}, text)
                b = new.decide(CFG, judge, {'followups': 0, 'ask_counts': {}, 'prev_eff': {}}, text)
                if a != b:
                    dec_changes.append((src, where, text, judge['decision'], a, b))
        after = any(a for _, _, a in occ)
        so = 'only' if OLD_SUPPLEMENT.fullmatch(text.strip()) else None
        sup_rows.append((src, text, after, so, new.supplement_end(text), occ[0][0], len(occ)))

    print(f'\n== elder_signal changes ({len(sig_changes)}) ==')
    for src, text, o, n, where, k in sorted(sig_changes):
        print(f'[{src}] {o} -> {n}  x{k}  {where}\n    {text}')
    print(f'\n== decide changes on judged answers, caps off ({len(dec_changes)} of {judged} judged answers) ==')
    for src, where, text, d, a, b in dec_changes:
        print(f'[{src}] engine {d}: {a} -> {b}  {where}\n    {text}')
    after_rows = [r for r in sup_rows if r[2]]
    print(f'\n== answers given right after the draft sentence ({len(after_rows)} distinct) ==')
    for src, text, _, so, sn, where, k in after_rows:
        print(f'[{src}] old {so or "-"} / new {sn or "-"}  x{k} {where}\n    {text}')
    other = [r for r in sup_rows if not r[2] and r[4]]
    print(f'\n== other answers the new reading would take as an ending if they came after the draft sentence ({len(other)}) ==')
    for src, text, _, so, sn, where, k in other:
        print(f'[{src}] new {sn}  x{k} {where}\n    {text}')
    summary = {
        'distinct_answers': len(uniq), 'signal_changes': len(sig_changes),
        'decide_changes': len(dec_changes), 'decide_changes_distinct': len({(r[2], r[4], r[5]) for r in dec_changes}),
        'judged_answers': judged,
        'decide_change_kinds': {f'{a[1]}->{b[1]}': n for (a, b), n in sorted(Counter((r[4], r[5]) for r in dec_changes).items())},
        'after_draft': {f'{so or "-"}/{sn or "-"}': n for (so, sn), n in sorted(Counter((r[3], r[4]) for r in after_rows).items(),
                                                                                 key=lambda kv: (str(kv[0][0]), str(kv[0][1])))},
        'elsewhere_as_ending': dict(sorted(Counter(r[4] for r in other).items())),
    }
    print('\nsummary ' + json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
