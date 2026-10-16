"""Read-only fingerprints for comparing business data before/after auth migration.

Run in a protected container during a write pause. Prints counts and SHA-256
digests only; never prints row contents, filenames, passwords, or session tokens.
"""
import hashlib
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import MetaData, Table, inspect, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.database import engine

EXCLUDED = {'alembic_version', 'family_accounts', 'device_sessions', 'auth_rate_limits'}


def encode(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(type(value).__name__)


def manifest():
    tables = {}
    with engine.connect() as connection, connection.begin():
        for name in sorted(set(inspect(connection).get_table_names()) - EXCLUDED):
            table = Table(name, MetaData(), autoload_with=connection)
            rows = []
            for row in connection.execute(select(table)).mappings():
                encoded = json.dumps(dict(row), sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), default=encode).encode('utf-8')
                rows.append(hashlib.sha256(encoded).hexdigest())
            tables[name] = {'count': len(rows), 'sha256': hashlib.sha256(
                '\n'.join(sorted(rows)).encode()).hexdigest()}
    root = Path(os.getenv('MEDIA_ROOT', '/data/media'))
    if not root.is_dir():
        raise RuntimeError('Media directory is missing; refusing an incomplete manifest')
    files = []
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        files.append(str(path.relative_to(root)) + '\0' + digest.hexdigest())
    return {'business_tables': tables, 'media': {'count': len(files), 'sha256':
            hashlib.sha256('\n'.join(files).encode()).hexdigest()}}


if __name__ == '__main__':
    print(json.dumps(manifest(), sort_keys=True, indent=2))
