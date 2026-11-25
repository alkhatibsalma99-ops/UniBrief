from app.database import SessionLocal
from app.login_rate_limit import (
    cleanup_expired_login_attempts,
)


def main():
    db = SessionLocal()

    try:
        deleted_count = cleanup_expired_login_attempts(db)

        db.commit()

        print(
            f"Deleted {deleted_count} "
            "expired login records."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()