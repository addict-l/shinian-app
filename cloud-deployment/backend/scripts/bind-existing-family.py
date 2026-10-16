"""Run inside the protected backend container; credentials arrive via stdin only."""
import json
import sys
from pathlib import Path
from uuid import UUID
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.authentication import bind_existing_family

if __name__ == '__main__':
    values = json.load(sys.stdin)
    account_id = bind_existing_family(values['username'], values['password'], UUID(values['family_id']))
    print(json.dumps({'status': 'bound', 'account_id': account_id, 'existing_family_preserved': True}))
