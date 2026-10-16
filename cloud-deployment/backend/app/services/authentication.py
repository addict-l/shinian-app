"""Password hashing, atomic registration, and one revocable session per login."""
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.db.database import SessionLocal
from app.models.authentication import FamilyAccountModel, DeviceSessionModel, AuthRateLimitModel
from app.models.family import FamilyModel
from app.schemas.authentication import AccountIdentity, LoginResponse
from app.services.workflow_service import serialized


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def hash_password(password):
    # OWASP scrypt profile: N=2^15, r=8, p=3 (32 MiB); explicit OpenSSL cap.
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
    return 'scrypt$32768$8$3$' + salt.hex() + '$' + digest.hex()


def verify_password(password, encoded):
    try:
        scheme, n, r, p, salt, expected = encoded.split('$')
        if (scheme, n, r, p) != ('scrypt', '32768', '8', '3'):
            return False
        actual = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


# Unknown accounts perform the same expensive check, avoiding a fast enumeration path.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


@dataclass(frozen=True)
class Principal:
    account_id: str
    family_id: str
    session_id: str
    username: str
    legacy: bool

    def identity(self):
        return AccountIdentity(account_id=self.account_id, family_id=self.family_id, username=self.username, legacy=self.legacy)


def throttle(key, limit, seconds):
    identity = hashlib.sha256(key.encode()).hexdigest()
    with serialized('auth-rate:' + identity):
        with SessionLocal.begin() as db:
            value = db.get(AuthRateLimitModel, identity, with_for_update=True)
            current = now()
            if value is None:
                value = AuthRateLimitModel(key=identity, started_at=current, attempts=0)
                db.add(value)
            elif aware(value.started_at) + timedelta(seconds=seconds) <= current:
                value.started_at = current
                value.attempts = 0
            if value.attempts >= limit:
                raise HTTPException(429, '尝试过于频繁，请稍后再试。', headers={'Retry-After': str(seconds)})
            value.attempts += 1


def issue_session(db, account):
    token = secrets.token_urlsafe(32)
    expires = now() + timedelta(days=30)
    db.add(DeviceSessionModel(account_id=account.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=expires))
    return LoginResponse(account_id=account.id, family_id=account.family_id, username=account.username,
                         legacy=account.legacy, token=token, expires_at=expires)


def register(username, password):
    if len(password) < 8 or len(password) > 128 or not password.strip():
        raise HTTPException(422, '密码须为 8–128 位，且不能只包含空格。')
    # The old account can only be provisioned by the controlled migration command.
    if username == os.getenv('LEGACY_FAMILY_USERNAME', 'family').strip().lower():
        raise HTTPException(409, '这个账号已被使用，请直接登录或换一个账号。')
    encoded = hash_password(password)
    try:
        with SessionLocal.begin() as db:
            family = FamilyModel(id=str(uuid4()), name='我的家庭')
            account = FamilyAccountModel(id=str(uuid4()), username=username, password_hash=encoded,
                                         family_id=family.id, enabled=True, legacy=False)
            db.add(family)
            db.flush()
            db.add(account)
            db.flush()
            return issue_session(db, account)
    except IntegrityError:
        raise HTTPException(409, '这个账号已被使用，请换一个账号。') from None


def login(username, password):
    if not password or len(password) > 128:
        raise HTTPException(401, '账号或密码不正确，请重新输入。')
    with SessionLocal.begin() as db:
        account = db.scalar(select(FamilyAccountModel).where(FamilyAccountModel.username == username))
        valid = verify_password(password, account.password_hash if account else DUMMY_PASSWORD_HASH)
        if not account or not valid or not account.enabled:
            raise HTTPException(401, '账号或密码不正确，请重新输入。')
        return issue_session(db, account)


def authenticate(token):
    if not token or len(token) > 128:
        raise HTTPException(401, '请登录家庭账号。', headers={'WWW-Authenticate': 'Bearer'})
    digest = hashlib.sha256(token.encode()).hexdigest()
    with SessionLocal() as db:
        result = db.execute(select(DeviceSessionModel, FamilyAccountModel).join(
            FamilyAccountModel, FamilyAccountModel.id == DeviceSessionModel.account_id
        ).where(DeviceSessionModel.token_hash == digest)).first()
        if result:
            session, account = result
            if session.revoked_at is None and aware(session.expires_at) > now() and account.enabled:
                return Principal(account.id, account.family_id, session.id, account.username, account.legacy)
    raise HTTPException(401, '登录已失效，请重新登录。', headers={'WWW-Authenticate': 'Bearer'})


def logout(principal):
    with SessionLocal.begin() as db:
        session = db.get(DeviceSessionModel, principal.session_id, with_for_update=True)
        if session and session.revoked_at is None:
            session.revoked_at = now()


def bind_existing_family(username, password, family_id):
    """Operator-only, idempotent migration; no API can claim an existing family."""
    from app.schemas.authentication import AccountCredentials
    credentials = AccountCredentials(username=username, password=password)
    username = credentials.username
    if not password or len(password) > 128:
        raise ValueError('Invalid existing password')
    encoded = hash_password(password)
    with SessionLocal.begin() as db:
        if db.get(FamilyModel, str(family_id)) is None:
            raise ValueError('Existing family does not exist; refusing to create replacement data')
        account = db.scalar(select(FamilyAccountModel).where(FamilyAccountModel.username == username))
        if account:
            if account.family_id != str(family_id) or not account.legacy or not verify_password(password, account.password_hash):
                raise ValueError('Existing account binding differs; refusing to overwrite')
            return account.id
        account = FamilyAccountModel(id=str(uuid4()), username=username, password_hash=encoded,
                                     family_id=str(family_id), enabled=True, legacy=True)
        db.add(account)
        db.flush()
        return account.id
