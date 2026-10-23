"""Small isolated queue for material-grounded simulated respondents.

Workers only see original materials, visible dialogue and a response brief.
"""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parent
mode, actor = sys.argv[1:3]
folder = ROOT / 'persona-queue' / actor
folder.mkdir(parents=True, exist_ok=True)
if mode == 'next':
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        pending = [p for p in sorted(folder.glob('*.request.json'))
                   if not p.with_name(p.name.replace('.request.json', '.response.json')).exists()]
        if pending:
            p = pending[0]
            print(json.dumps({'request_id': p.name[:-13], **json.loads(p.read_text())}, ensure_ascii=False))
            break
        if (folder / 'DONE').exists():
            print('DONE')
            break
        time.sleep(0.4)
    else:
        print('IDLE')
elif mode == 'answer':
    rid = sys.argv[3]
    request = json.loads((folder / (rid + '.request.json')).read_text())
    value = json.load(sys.stdin)
    assert isinstance(value.get('reply'), str) and 1 <= len(value['reply']) <= 300
    valid = {e['id'] for e in request['materials']}
    assert set(value.get('supporting_excerpt_ids', [])) <= valid
    path = folder / (rid + '.response.json')
    assert not path.exists(), 'already answered'
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    print('OK')
else:
    raise ValueError('next or answer')
