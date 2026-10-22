#!/usr/bin/env python3
"""DeepSeek tokens actually sent by this stage's relay jobs (job names starting with sim- / rp4-), by job prefix and model."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

PREFIXES = tuple(sys.argv[1:]) or ('sim-', 'rp4-')
total, by_run, by_model = Counter(), defaultdict(Counter), defaultdict(Counter)
for f in common.IN_ROOT.rglob('*.response.jsonl'):
    name = f.name[:-len('.response.jsonl')]
    if not name.startswith(PREFIXES):
        continue
    run = name.rsplit('-', 1)[0]
    for line in f.read_text(encoding='utf-8').splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        u = r.get('usage') or {}
        for k in ('total_tokens', 'prompt_tokens', 'prompt_cache_hit_tokens', 'completion_tokens'):
            total[k] += u.get(k, 0)
            by_run[run][k] += u.get(k, 0)
        by_model[r.get('model_requested')]['total_tokens'] += u.get('total_tokens', 0)
        by_model[r.get('model_requested')]['calls'] += 1
print(json.dumps({'stage_total': dict(total), 'by_model': {k: dict(v) for k, v in by_model.items()},
                  'by_run': {k: v['total_tokens'] for k, v in sorted(by_run.items())}}, ensure_ascii=False, indent=1))
