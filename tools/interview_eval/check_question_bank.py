#!/usr/bin/env python3
"""确认某个运行时的题库与冻结的 83 题（docs/question-bank-freeze-v2.json）一致：题号、题序、入口问题、要素与回答标准不变。"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
freeze = json.loads((ROOT / 'docs/question-bank-freeze-v2.json').read_text(encoding='utf-8'))
base = json.loads((ROOT / 'docs/prototypes/full-interview-v2/single-question-v2/contracts.json').read_text(encoding='utf-8'))
target = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'docs/prototypes/full-interview-v3j/contracts.json').read_text(encoding='utf-8'))
KEYS = ('id', 'label', 'question', 'usable_answer', 'requirement', 'activation', 'allowed_states', 'scope', 'link', 'answer_format')
errors = []
if [q['id'] for q in target['questions']] != freeze['question_ids']:
    errors.append('题号或题序不同')
for a, b in zip(base['questions'], target['questions']):
    if a['main_question'] != b['main_question']:
        errors.append(a['id'] + ' 入口问题不同')
    if [{k: f.get(k) for k in KEYS} for f in a['elements']] != [{k: f.get(k) for k in KEYS} for f in b['elements']]:
        errors.append(a['id'] + ' 要素或回答标准不同')
print('与冻结题库一致' if not errors else '不一致：' + '；'.join(errors))
sys.exit(1 if errors else 0)
