from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import User, UserSession

VALID_ROLES = {'admin', 'operator', 'viewer'}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 120_000).hex()
    return f'pbkdf2_sha256${salt}${digest}'


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, salt, expected = stored_hash.split('$', 2)
    except ValueError:
        return False
    if scheme != 'pbkdf2_sha256':
        return False
    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 120_000).hex()
    return hmac.compare_digest(actual, expected)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def create_server_session(session: Session, user: User, ttl_hours: int) -> tuple[str, UserSession]:
    raw_token = secrets.token_urlsafe(32)
    now_dt = datetime.now(timezone.utc)
    record = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=now_dt + timedelta(hours=ttl_hours),
        revoked_at=None,
    )
    session.add(record)
    session.flush()
    return raw_token, record


def get_user_by_session_token(session: Session, raw_token: str | None) -> User | None:
    if not raw_token:
        return None
    token_digest = hash_token(raw_token)
    now_dt = datetime.now(timezone.utc)
    stmt = (
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_digest,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now_dt,
            User.is_active.is_(True),
        )
    )
    return session.scalar(stmt)


def revoke_session_token(session: Session, raw_token: str | None) -> bool:
    if not raw_token:
        return False
    token_digest = hash_token(raw_token)
    record = session.scalar(select(UserSession).where(UserSession.token_hash == token_digest))
    if not record or record.revoked_at is not None:
        return False
    record.revoked_at = datetime.now(timezone.utc)
    session.flush()
    return True
