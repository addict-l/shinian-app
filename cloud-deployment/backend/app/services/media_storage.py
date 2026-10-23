"""Private photo storage behind the existing authenticated media API."""
import hashlib
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
from uuid import UUID

MAX_MEDIA_BYTES = 8 * 1024 * 1024


class MediaStorageError(OSError):
    """A retryable storage failure with no upstream credentials or URLs."""


class MediaNotFoundError(FileNotFoundError):
    """The object is genuinely absent, rather than inaccessible."""


def media_filename(media_id):
    return str(UUID(str(media_id))) + '.jpg'


def _check_size(data):
    if len(data) > MAX_MEDIA_BYTES:
        raise MediaStorageError('图片存储大小异常')
    return data


class LocalStorage:
    backend = 'local'

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def put(self, media_id, data):
        path = self.root / media_filename(media_id)
        _check_size(data)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, suffix='.upload', delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        except OSError:
            raise MediaStorageError('图片存储暂时不可用') from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    raise MediaStorageError('图片存储暂时不可用') from None

    def read(self, media_id):
        path = self.root / media_filename(media_id)
        try:
            with path.open('rb') as source:
                return _check_size(source.read(MAX_MEDIA_BYTES + 1))
        except FileNotFoundError:
            raise MediaNotFoundError('图片文件不存在') from None
        except OSError:
            raise MediaStorageError('图片存储暂时不可用') from None

    def delete(self, media_id):
        path = self.root / media_filename(media_id)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            raise MediaStorageError('图片存储暂时不可用') from None


def _service_error(error, status, code):
    # SDK operation errors wrap the actual service error. A missing bucket,
    # denied access, and transport failures must never trigger local fallback.
    for _ in range(8):
        if (getattr(error, 'status_code', None) == status
                and getattr(error, 'code', None) == code):
            return True
        unwrap = getattr(error, 'unwrap', None)
        if not callable(unwrap):
            break
        nested = unwrap()
        if nested is None or nested is error:
            break
        error = nested
    return False


def _missing_object(error):
    return _service_error(error, 404, 'NoSuchKey')


def _success(result):
    if not 200 <= (getattr(result, 'status_code', 0) or 0) < 300:
        raise MediaStorageError('图片存储暂时不可用')


class OSSStorage:
    backend = 'oss'

    def __init__(self, root, bucket, region, endpoint, prefix='media/',
                 mirror_local=True, local_fallback=True, client=None):
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', bucket or ''):
            raise MediaStorageError('OSS 存储配置不完整')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)+', region or ''):
            raise MediaStorageError('OSS 存储配置不完整')
        parsed = urlsplit(endpoint)
        allowed = {f'oss-{region}.aliyuncs.com', f'oss-{region}-internal.aliyuncs.com'}
        if (parsed.scheme != 'https' or parsed.hostname not in allowed or parsed.port is not None
                or parsed.username or parsed.password or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment):
            raise MediaStorageError('OSS 必须使用对应地域的 HTTPS Endpoint')
        prefix = prefix.strip('/')
        if (not prefix or any(part in ('', '.', '..') for part in prefix.split('/'))
                or any(ord(char) < 32 for char in prefix) or '\\' in prefix):
            raise MediaStorageError('OSS 对象前缀无效')
        self.local = LocalStorage(root)
        self.root = self.local.root
        self.bucket, self.region, self.endpoint = bucket, region, endpoint
        self.prefix = prefix + '/'
        self.mirror_local, self.local_fallback = mirror_local, local_fallback
        self._client = client
        self._client_lock = Lock()

    def object_key(self, media_id):
        return self.prefix + media_filename(media_id)

    @property
    def client(self):
        with self._client_lock:
            if self._client is None:
                try:
                    import alibabacloud_oss_v2 as oss
                    values = {}
                    credentials_file = os.getenv('OSS_CREDENTIALS_FILE', '').strip()
                    if credentials_file:
                        from dotenv import dotenv_values
                        values = dotenv_values(credentials_file, interpolate=False)
                    key_id = os.getenv('OSS_ACCESS_KEY_ID') or values.get('OSS_ACCESS_KEY_ID')
                    secret = os.getenv('OSS_ACCESS_KEY_SECRET') or values.get('OSS_ACCESS_KEY_SECRET')
                    if not key_id or not secret:
                        raise MediaStorageError('OSS 访问凭据尚未配置')
                    cfg = oss.config.load_default()
                    cfg.credentials_provider = oss.credentials.StaticCredentialsProvider(
                        access_key_id=key_id, access_key_secret=secret)
                    cfg.region, cfg.endpoint = self.region, self.endpoint
                    cfg.connect_timeout, cfg.readwrite_timeout = 5, 15
                    cfg.retry_max_attempts = 2
                    self._client = oss.Client(cfg)
                except Exception:
                    raise MediaStorageError('OSS 访问配置不可用') from None
            return self._client

    def put(self, media_id, data):
        self._put_remote(media_id, data)
        if self.mirror_local:
            self.local.put(media_id, data)

    def put_if_absent(self, media_id, data):
        """Copy a legacy photo without overwriting even a concurrent writer."""
        return self._put_remote(media_id, data, forbid_overwrite=True)

    def _put_remote(self, media_id, data, forbid_overwrite=False):
        key = self.object_key(media_id)
        _check_size(data)
        try:
            import alibabacloud_oss_v2 as oss
            result = self.client.put_object(oss.PutObjectRequest(
                bucket=self.bucket, key=key, body=data, content_length=len(data),
                content_type='image/jpeg', cache_control='no-store',
                storage_class='Standard', server_side_encryption='AES256',
                forbid_overwrite=forbid_overwrite,
                metadata={'sha256': hashlib.sha256(data).hexdigest()}))
            _success(result)
            return True
        except Exception as error:
            if forbid_overwrite and _service_error(error, 409, 'FileAlreadyExists'):
                return False
            raise MediaStorageError('图片存储暂时不可用') from None

    def read_remote(self, media_id):
        key = self.object_key(media_id)
        try:
            import alibabacloud_oss_v2 as oss
            result = self.client.get_object(oss.GetObjectRequest(bucket=self.bucket, key=key))
            try:
                _success(result)
                chunks, size = [], 0
                for chunk in result.body.iter_bytes(block_size=64 * 1024):
                    size += len(chunk)
                    if size > MAX_MEDIA_BYTES:
                        raise MediaStorageError('图片存储大小异常')
                    chunks.append(chunk)
                return b''.join(chunks)
            finally:
                result.body.close()
        except Exception as error:
            if _missing_object(error):
                raise MediaNotFoundError('图片文件不存在') from None
            raise MediaStorageError('图片存储暂时不可用') from None

    def read(self, media_id):
        try:
            return self.read_remote(media_id)
        except MediaNotFoundError:
            if not self.local_fallback:
                raise
            return self.local.read(media_id)

    def delete(self, media_id):
        key = self.object_key(media_id)
        try:
            import alibabacloud_oss_v2 as oss
            _success(self.client.delete_object(oss.DeleteObjectRequest(bucket=self.bucket, key=key)))
        except Exception as error:
            if not _missing_object(error):
                raise MediaStorageError('图片存储暂时不可用') from None
        # Remove active fallback/mirror copies too, so deleted photos cannot
        # reappear after an object goes missing. Separate backups are retained.
        self.local.delete(media_id)


def _flag(name, default=True):
    value = os.getenv(name, 'true' if default else 'false').strip().lower()
    if value not in ('true', 'false'):
        raise MediaStorageError('图片存储开关配置无效')
    return value == 'true'


@lru_cache(maxsize=8)
def _storage(root, mode, bucket, region, endpoint, prefix, mirror, fallback):
    if mode == 'local':
        return LocalStorage(root)
    if mode != 'oss':
        raise MediaStorageError('图片存储类型配置无效')
    return OSSStorage(root, bucket, region, endpoint, prefix, mirror, fallback)


def get_storage(root):
    mode = os.getenv('MEDIA_STORAGE', 'local').strip().lower()
    if mode == 'local':
        return _storage(str(Path(root).resolve()), mode, '', '', '', '', False, False)
    region = os.getenv('OSS_REGION', '').strip()
    return _storage(str(Path(root).resolve()), mode, os.getenv('OSS_BUCKET', '').strip(), region,
                    os.getenv('OSS_ENDPOINT', f'https://oss-{region}-internal.aliyuncs.com').strip(),
                    os.getenv('OSS_PREFIX', 'media/'), _flag('OSS_LOCAL_MIRROR'), _flag('OSS_LOCAL_FALLBACK'))
