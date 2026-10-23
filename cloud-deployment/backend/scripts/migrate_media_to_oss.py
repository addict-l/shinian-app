"""Copy DB-referenced JPEGs to private OSS; dry-run unless --apply is explicit.

The report contains IDs, byte counts and SHA-256 fingerprints only. It never
prints file contents, credentials, upstream exceptions or database URLs.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.models.media_asset import MediaAssetModel
from app.services.media_storage import LocalStorage, MediaNotFoundError, OSSStorage, get_storage

ERROR_STATUSES = {'conflict', 'missing_both', 'storage_error'}


def fingerprint(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def migrate_one(media_id, local, remote, *, apply=False):
    """Inspect/copy a single immutable ID while its caller holds the DB row lock."""
    record = {'id': media_id, 'object_key': remote.object_key(media_id)}
    try:
        source = local.read(media_id)
    except MediaNotFoundError:
        source = None
    record['local'] = fingerprint(source) if source is not None else None
    try:
        existing = remote.read_remote(media_id)
    except MediaNotFoundError:
        existing = None
    record['remote'] = fingerprint(existing) if existing is not None else None

    if source is None:
        record['status'] = 'missing_both' if existing is None else 'verified_remote_only'
        record['verification'] = ('no_source_available' if existing is None
                                  else 'remote_downloaded_without_local_comparison')
        return record
    if existing is not None:
        record['status'] = 'already_verified' if record['local'] == record['remote'] else 'conflict'
        record['verification'] = 'local_and_remote_sha256_and_length'
        return record
    if not apply:
        record['status'] = 'would_copy'
        record['verification'] = 'local_only_remote_absent'
        return record

    # Server-side forbid-overwrite also protects against external writers that
    # do not participate in the database row lock. Never replace an object.
    created = remote.put_if_absent(media_id, source)
    downloaded = remote.read_remote(media_id)
    record['remote'] = fingerprint(downloaded)
    record['verification'] = 'local_and_remote_sha256_and_length'
    if record['local'] != record['remote']:
        record['status'] = 'conflict'
    else:
        record['status'] = 'copied_and_verified' if created else 'already_verified'
    return record


def migrate(session_factory, local, remote, *, apply=False):
    """Snapshot DB photo IDs, then recheck each row under SELECT FOR UPDATE.

    Each network operation runs within that row's transaction so deletion must
    wait until copying and verification finish. No row or local file is changed.
    Newly uploaded photos after the snapshot belong to a later idempotent run.
    """
    with session_factory() as db:
        ids = list(db.scalars(select(MediaAssetModel.id)
                              .where(MediaAssetModel.type == 'image')
                              .order_by(MediaAssetModel.id)))
    records = []
    for media_id in ids:
        try:
            with session_factory.begin() as db:
                asset = db.get(MediaAssetModel, media_id, with_for_update=True)
                if asset is None:
                    record = {'id': media_id, 'status': 'skipped_deleted'}
                elif asset.type != 'image':
                    record = {'id': media_id, 'status': 'skipped_non_image'}
                else:
                    record = migrate_one(media_id, local, remote, apply=apply)
        except Exception as error:
            # Never stringify SDK/SQL exceptions: they can contain signed URLs,
            # credentials or database parameters. Keep failure reports reviewable.
            record = {'id': media_id, 'status': 'storage_error',
                      'error_type': type(error).__name__}
        records.append(record)
    counts = Counter(record['status'] for record in records)
    error_count = sum(counts[status] for status in ERROR_STATUSES)
    return {'schema_version': 1, 'mode': 'apply' if apply else 'dry-run',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'snapshot_photo_count': len(ids), 'counts': dict(sorted(counts.items())),
            'error_count': error_count, 'ok': error_count == 0, 'items': records}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='Create missing OSS objects and download them for verification.')
    parser.add_argument('--media-root', type=Path,
                        help='Override MEDIA_ROOT for this process only.')
    args = parser.parse_args(argv)
    try:
        # Lazy import keeps --help usable without DB/credential configuration.
        from app.db.database import ROOT, SessionLocal

        root = args.media_root or Path(os.getenv('MEDIA_ROOT', str(ROOT / '.runtime/media')))
        if not root.is_dir():
            raise RuntimeError('Local media directory is missing')
        remote = get_storage(root)
        if not isinstance(remote, OSSStorage):
            raise RuntimeError('Migration requires MEDIA_STORAGE=oss')
        report = migrate(SessionLocal, LocalStorage(root), remote, apply=args.apply)
    except Exception as error:
        report = {'schema_version': 1, 'mode': 'apply' if args.apply else 'dry-run',
                  'ok': False, 'error_count': 1, 'status': 'setup_error',
                  'error_type': type(error).__name__}
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
