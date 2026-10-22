#!/usr/bin/env python3
"""Total DeepSeek tokens actually spent through the relay (all cached responses, excluding seeded replays)."""
import json
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

total, calls = Counter(), 0
for path in common.CACHE.glob('*.json'):
    row = json.loads(path.read_text(encoding='utf-8'))
    if row.get('seeded_from'):
        continue
    calls += 1
    for k, v in (row.get('usage') or {}).items():
        if isinstance(v, (int, float)):
            total[k] += v
print(json.dumps({'calls': calls, 'total_tokens': total['total_tokens'], 'prompt_tokens': total['prompt_tokens'],
                  'prompt_cache_hit_tokens': total['prompt_cache_hit_tokens'], 'completion_tokens': total['completion_tokens']}))
