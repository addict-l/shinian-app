#!/usr/bin/env python3
"""Print a simulated run's dialogues as compact text:  python3 show.py RUN [NID_or_session_substring]"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
from score import label_messages  # noqa: E402

run = sys.argv[1]
flt = sys.argv[2] if len(sys.argv) > 2 else ''
sc = common.load(common.RUNS / run / 'scores.json').get('scores', {}) if (common.RUNS / run / 'scores.json').exists() else {}
for f in sorted((common.RUNS / run / 'sessions').glob('*.json')):
    if flt and flt not in f.name:
        continue
    s = common.load(f)
    print('=' * 20, s['session'], s['name'])
    for i, ep in enumerate(s['episodes']):
        e = (sc.get(s['session']) or {}).get(str(i)) or {}
        print(f"--- {ep['qid']} close={ep['close_reason']} final={ep['final_decision']}")
        for label, m in label_messages(ep):
            if m['role'] == 'system':
                t = (e.get('turns') or {}).get(label) or {}
                score = ' '.join(f"{k[:3]}{t[k]}" for k in ('natural', 'grounded', 'timing', 'single', 'tone') if k in t)
                extra = f" [{m.get('kind')}{':' + m['target'] if m.get('target') else ''}{' FB' if (m.get('speaker') or {}).get('fallback') else ''}] {score} {t.get('violations') or ''}"
                print(f"  {label} 问：{m['text']}{extra}")
            else:
                j = m.get('judge') or {}
                print(f"  {label} 答（{m.get('behavior', '')}{'+asr' if m.get('asr') else ''}）：{m['text']}   <{j.get('decision', '')} {j.get('target') or ''}>")
        if e.get('fabrication') or e.get('record_errors'):
            print('  !!', e.get('fabrication'), e.get('record_errors'))
        if e.get('note'):
            print('  note:', e['note'])
