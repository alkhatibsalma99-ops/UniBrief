
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import text

from app.database import SessionLocal


# Maximum AI requests per user per UTC day.
AI_DAILY_LIMIT = int(
    os.getenv("AI_DAILY_LIMIT", "20")
)

# Maximum time reserved for one AI operation.
AI_RESERVATION_MINUTES = int(
    os.getenv("AI_RESERVATION_MINUTES", "15")
)


# ==================================================
# INITIALIZE AI RATE LIMIT
# ==================================================

def initialize_ai_rate_limit(engine):
    """
    Create separate AI usage tables.

    Does not modify existing UniBrief tables.
    """
    with engine.begin() as connection:
        connection.execute(
            text("""
                CREATE TABLE IF NOT EXISTS ai_daily_usage (
                    user_id INTEGER NOT NULL,
                    usage_day DATE NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, usage_day)
                )
            """)
        )

        connection.execute(
            text("""
                CREATE TABLE IF NOT EXISTS ai_active_requests (
                    user_id INTEGER PRIMARY KEY,
                    request_id VARCHAR(36) NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL
                )
            """)
        )


def _utc_now():
    return datetime.now(timezone.utc)


# ==================================================
# RESERVE AI REQUEST
# ==================================================

def _reserve_request(user_id: int) -> str:
    """
    Reserve one AI request for a user.

    PostgreSQL advisory lock serializes reservations
    for the same user, even across server instances.

    All AI endpoints share the same daily quota.
    """
    request_id = str(uuid.uuid4())
    now = _utc_now()
    today = now.date()

    db = SessionLocal()

    try:
        # Transaction-scoped per-user lock.
        db.execute(
            text("""
                SELECT pg_advisory_xact_lock(
                    :user_id
                )
            """),
            {"user_id": int(user_id)},
        )

        # Verify that the user account still exists.
        existing_user = db.execute(
            text("""
                SELECT id
                FROM users
                WHERE id = :user_id
            """),
            {"user_id": user_id},
        ).first()

        if existing_user is None:
            raise HTTPException(
                status_code=401,
                detail="User account no longer exists",
            )

        # Remove an expired reservation.
        db.execute(
            text("""
                DELETE FROM ai_active_requests
                WHERE user_id = :user_id
                  AND expires_at <= :now
            """),
            {
                "user_id": user_id,
                "now": now,
            },
        )

        # Check whether an AI request is running.
        active = db.execute(
            text("""
                SELECT expires_at
                FROM ai_active_requests
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        ).mappings().first()

        if active is not None:
            db.rollback()

            raise HTTPException(
                status_code=429,
                detail=(
                    "An AI request is already running. "
                    "Please wait for it to finish."
                ),
                headers={"Retry-After": "10"},
            )

        # Create daily usage record if needed.
        db.execute(
            text("""
                INSERT INTO ai_daily_usage (
                    user_id,
                    usage_day,
                    request_count
                )
                VALUES (
                    :user_id,
                    :usage_day,
                    0
                )
                ON CONFLICT (user_id, usage_day)
                DO NOTHING
            """),
            {
                "user_id": user_id,
                "usage_day": today,
            },
        )

        usage = db.execute(
            text("""
                SELECT request_count
                FROM ai_daily_usage
                WHERE user_id = :user_id
                  AND usage_day = :usage_day
                FOR UPDATE
            """),
            {
                "user_id": user_id,
                "usage_day": today,
            },
        ).mappings().first()

        count = int(usage["request_count"])

        if count >= AI_DAILY_LIMIT:
            db.rollback()

            next_day = datetime.combine(
                today + timedelta(days=1),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )

            retry_after = max(
                1,
                int(
                    (next_day - now).total_seconds()
                ) + 1,
            )

            raise HTTPException(
                status_code=429,
                detail=(
                    "Daily AI request limit reached. "
                    "Please try again tomorrow."
                ),
                headers={
                    "Retry-After": str(retry_after),
                },
            )

        # Count the request before calling the AI.
        db.execute(
            text("""
                UPDATE ai_daily_usage
                SET request_count = request_count + 1
                WHERE user_id = :user_id
                  AND usage_day = :usage_day
            """),
            {
                "user_id": user_id,
                "usage_day": today,
            },
        )

        # Reserve the running request.
        db.execute(
            text("""
                INSERT INTO ai_active_requests (
                    user_id,
                    request_id,
                    expires_at
                )
                VALUES (
                    :user_id,
                    :request_id,
                    :expires_at
                )
            """),
            {
                "user_id": user_id,
                "request_id": request_id,
                "expires_at": now + timedelta(
                    minutes=AI_RESERVATION_MINUTES
                ),
            },
        )

        db.commit()

        return request_id

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==================================================
# RELEASE AI REQUEST
# ==================================================

def _release_request(
    user_id: int,
    request_id: str,
):
    """
    Release only the matching reservation.

    Prevents an old request from clearing a newer
    reservation that replaced an expired one.
    """
    db = SessionLocal()

    try:
        db.execute(
            text("""
                DELETE FROM ai_active_requests
                WHERE user_id = :user_id
                  AND request_id = :request_id
            """),
            {
                "user_id": user_id,
                "request_id": request_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==================================================
# DELETE USER AI DATA
# ==================================================

def delete_user_ai_data(db, user_id: int):
    """
    Delete AI usage records for one user.

    Uses the existing account deletion transaction.
    Does not commit or close the database session.
    """

    # Prevent new reservations during account deletion.
    db.execute(
        text("""
            SELECT pg_advisory_xact_lock(
                :user_id
            )
        """),
        {"user_id": int(user_id)},
    )

    now = _utc_now()

    active_request = db.execute(
        text("""
            SELECT request_id
            FROM ai_active_requests
            WHERE user_id = :user_id
              AND expires_at > :now
        """),
        {
            "user_id": user_id,
            "now": now,
        },
    ).first()

    if active_request is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "An AI request is currently running. "
                "Please wait before deleting your account."
            ),
            headers={"Retry-After": "10"},
        )

    db.execute(
        text("""
            DELETE FROM ai_active_requests
            WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    )

    db.execute(
        text("""
            DELETE FROM ai_daily_usage
            WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    )


# ==================================================
# AI REQUEST CONTEXT MANAGER
# ==================================================

@contextmanager
def ai_request_slot(user_id: int):
    """
    Protect one AI operation.

    Usage:
        with ai_request_slot(current_user.id):
            result = call_ai()

    The slot is released even when AI raises an error.
    """
    request_id = _reserve_request(user_id)

    try:
        yield

    finally:
        _release_request(
            user_id=user_id,
            request_id=request_id,
        )
