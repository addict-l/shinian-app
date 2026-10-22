#!/usr/bin/env python3
"""Load every finished relay job (request in outputs + staged response) into the response cache.

Used when a harness process died after its job was already paid for: re-running the same
pipeline afterwards replays those answers from cache instead of calling DeepSeek again.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

added = 0
for req in sorted(common.OUT_JOBS.glob('*.request.json')):
    name = req.name[:-len('.request.json')]
    staged = next(common.IN_ROOT.rglob(name + '.response.jsonl'), None)
    if not staged:
        continue
    job = common.load(req)
    rows = {}
    for line in staged.read_text(encoding='utf-8').splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        rows[row.get('id')] = row
    for call in job.get('calls', []):
        row = rows.get(call['id'])
        if not row or not row.get('ok') or 'system_ref' not in call:
            continue
        full = {'system': job['prompts'][call['system_ref']], 'user': call['user'], 'params': call['params'], 'sample': call.get('sample')}
        path = common.CACHE / (common.Relay.key(full) + '.json')
        if path.exists():
            continue
        content = row.get('content') or ''
        try:
            row['output'], row['parse_error'] = json.loads(content), None
        except ValueError:
            row['output'], row['parse_error'] = None, 'JSONDecodeError'
        common.save(path, row)
        added += 1
print(json.dumps({'cached_new': added}))
