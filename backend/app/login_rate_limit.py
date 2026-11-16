
import hashlib
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

# Number of failed attempts allowed in one window.
MAX_FAILED_ATTEMPTS = int(
    os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "5")
)

# Length of the window in minutes.
WINDOW_MINUTES = int(
    os.getenv("LOGIN_WINDOW_MINUTES", "15")
)

# Temporary block after reaching the limit.
BLOCK_MINUTES = int(
    os.getenv("LOGIN_BLOCK_MINUTES", "15")
)


def initialize_login_rate_limit(engine):
    """
    Create a separate table for login attempt counters.
    Existing UniBrief tables are not modified.
    """
    with engine.begin() as connection:
        connection.execute(
            text("""
                CREATE TABLE IF NOT EXISTS login_rate_limits (
                    key_hash VARCHAR(64) PRIMARY KEY,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    window_started_at TIMESTAMPTZ NOT NULL,
                    blocked_until TIMESTAMPTZ
                )
            """)
        )


def _utc_now():
    return datetime.now(timezone.utc)


def _normalize_datetime(value):
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _make_key(request: Request, email: str) -> str:
    """
    Use the connection IP and normalized email.
    Never store passwords in rate-limit records.

    Do not trust arbitrary X-Forwarded-For headers.
    """
    client_ip = (
        request.client.host
        if request.client is not None
        else "unknown"
    )

    normalized_email = email.strip().lower()

    raw_key = f"{client_ip}:{normalized_email}"

    return hashlib.sha256(
        raw_key.encode("utf-8")
    ).hexdigest()


def _lock_key(db: Session, key: str):
    """
    PostgreSQL transaction lock prevents concurrent
    requests from bypassing the attempt counter.
    """
    db.execute(
        text("""
            SELECT pg_advisory_xact_lock(
                hashtextextended(:key, 0)
            )
        """),
        {"key": key},
    )


def _get_record(db: Session, key: str):
    return db.execute(
        text("""
            SELECT
                failed_attempts,
                window_started_at,
                blocked_until
            FROM login_rate_limits
            WHERE key_hash = :key
        """),
        {"key": key},
    ).mappings().first()


def check_login_limit(
    db: Session,
    request: Request,
    email: str,
):
    """
    Check whether this IP/email combination is blocked.

    Caller must keep the database transaction open
    until the attempt is recorded or login succeeds.
    """
    key = _make_key(request, email)

    _lock_key(db, key)

    record = _get_record(db, key)

    if record is None:
        return key

    blocked_until = _normalize_datetime(
        record["blocked_until"]
    )

    now = _utc_now()

    if blocked_until is not None and now < blocked_until:
        retry_after = max(
            1,
            int((blocked_until - now).total_seconds()) + 1,
        )

        db.commit()

        raise HTTPException(
            status_code=429,
            detail=(
                "Too many failed login attempts. "
                "Please try again later."
            ),
            headers={
                "Retry-After": str(retry_after),
            },
        )

    return key


def record_failed_login(db: Session, key: str):
    """
    Record one failed login and commit it immediately.

    An HTTPException after this function will not
    roll back the recorded attempt.
    """
    now = _utc_now()

    record = _get_record(db, key)

    if record is None:
        attempts = 1
        window_started = now
    else:
        previous_start = _normalize_datetime(
            record["window_started_at"]
        )

        expired = (
            previous_start is None
            or now - previous_start
            >= timedelta(minutes=WINDOW_MINUTES)
        )

        if expired:
            attempts = 1
            window_started = now
        else:
            attempts = int(record["failed_attempts"]) + 1
            window_started = previous_start

    blocked_until = None

    if attempts >= MAX_FAILED_ATTEMPTS:
        blocked_until = now + timedelta(
            minutes=BLOCK_MINUTES
        )

    db.execute(
        text("""
            INSERT INTO login_rate_limits (
                key_hash,
                failed_attempts,
                window_started_at,
                blocked_until
            )
            VALUES (
                :key,
                :attempts,
                :window_started,
                :blocked_until
            )
            ON CONFLICT (key_hash)
            DO UPDATE SET
                failed_attempts = EXCLUDED.failed_attempts,
                window_started_at = EXCLUDED.window_started_at,
                blocked_until = EXCLUDED.blocked_until
        """),
        {
            "key": key,
            "attempts": attempts,
            "window_started": window_started,
            "blocked_until": blocked_until,
        },
    )

    db.commit()


def clear_login_attempts(db: Session, key: str):
    """
    Clear failed attempts after a successful login.

    The caller commits this deletion together with
    refresh-token creation.
    """
    db.execute(
        text("""
            DELETE FROM login_rate_limits
            WHERE key_hash = :key
        """),
        {"key": key},
    )
