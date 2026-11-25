from uuid import uuid4
from unittest.mock import patch

import pytest

from app import models
from app.database import SessionLocal
from app.main import delete_account
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from contextlib import closing
from app.translation_routes import open_cache
from fastapi import HTTPException


@pytest.fixture
def db():
    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_delete_account_with_project(db):
    unique_id = uuid4().hex

    user = models.User(
        name="Test User",
        email=f"test_{unique_id}@example.com",
        password_hash="test_hash",
    )

    other_user = models.User(
        name="Other User",
        email=f"other_{unique_id}@example.com",
        password_hash="test_hash",
    )

    db.add_all([user, other_user])
    db.flush()

    user_id = user.id
    other_user_id = other_user.id

    try:
        project = models.Project(
            title="Test Project",
            description="Account deletion test",
            user_id=user_id,
        )

        other_project = models.Project(
            title="Protected Project",
            description="Must not be deleted",
            user_id=other_user_id,
        )

        db.add_all([project, other_project])
        db.flush()

        project_id = project.id
        other_project_id = other_project.id

        object_key = (
            f"users/{user_id}/"
            f"projects/{project_id}/"
            "test.pdf"
        )

        project_file = models.ProjectFile(
            project_id=project_id,
            filename="test.pdf",
            file_path=f"r2://{object_key}",
        )

        db.add(project_file)
        db.commit()

        file_id = project_file.id

        with patch(
            "app.main.delete_file_from_r2"
        ) as mock_delete:

            result = delete_account(
                db=db,
                current_user=user,
            )

            mock_delete.assert_called_once_with(
                object_key
            )

        db.expire_all()

        assert result["message"] == (
            "Account deleted successfully"
        )

        assert db.query(models.User).filter_by(
            id=user_id
        ).first() is None

        assert db.query(models.Project).filter_by(
            id=project_id
        ).first() is None

        assert db.query(models.ProjectFile).filter_by(
            id=file_id
        ).first() is None

        assert db.query(models.User).filter_by(
            id=other_user_id
        ).first() is not None

        assert db.query(models.Project).filter_by(
            id=other_project_id
        ).first() is not None

    finally:
        db.rollback()

        db.query(models.User).filter(
            models.User.id.in_(
                [user_id, other_user_id]
            )
        ).delete(synchronize_session=False)

        db.commit()
def test_delete_account_related_data(db):
    unique_id = uuid4().hex

    user = models.User(
        name="Related Data Test",
        email=f"related_{unique_id}@example.com",
        password_hash="test_hash",
    )

    db.add(user)
    db.flush()

    user_id = user.id

    try:
        project = models.Project(
            title="Test Project",
            description="Related data deletion",
            user_id=user_id,
        )

        db.add(project)
        db.flush()

        project_id = project.id

        object_key = (
            f"users/{user_id}/"
            f"projects/{project_id}/test.pdf"
        )

        project_file = models.ProjectFile(
            project_id=project_id,
            filename="test.pdf",
            file_path=f"r2://{object_key}",
        )

        db.add(project_file)
        db.flush()

        file_id = project_file.id

        requirement = models.Requirement(
            project_id=project_id,
            file_id=file_id,
            title="Test Requirement",
            description="Test description",
            priority="high",
        )

        db.add(requirement)
        db.flush()

        requirement_id = requirement.id

        checklist_item = models.ChecklistItem(
            project_id=project_id,
            requirement_id=requirement_id,
            title="Test Checklist",
            completed=False,
        )

        submission = models.SubmissionResult(
            project_id=project_id,
            file_id=file_id,
            requirement_id=requirement_id,
            status="missing",
            feedback="Test feedback",
        )

        db.add_all([
            checklist_item,
            submission,
        ])

        db.commit()

        with patch(
            "app.main.delete_file_from_r2"
        ) as mock_delete:

            result = delete_account(
                db=db,
                current_user=user,
            )

            mock_delete.assert_called_once_with(
                object_key
            )

        db.expire_all()

        assert result["message"] == (
            "Account deleted successfully"
        )

        assert db.query(models.User).filter_by(
            id=user_id
        ).count() == 0

        assert db.query(models.Project).filter_by(
            id=project_id
        ).count() == 0

        assert db.query(models.ProjectFile).filter_by(
            project_id=project_id
        ).count() == 0

        assert db.query(models.Requirement).filter_by(
            project_id=project_id
        ).count() == 0

        assert db.query(models.ChecklistItem).filter_by(
            project_id=project_id
        ).count() == 0

        assert db.query(models.SubmissionResult).filter_by(
            project_id=project_id
        ).count() == 0

    finally:
        db.rollback()

        db.query(models.User).filter_by(
            id=user_id
        ).delete(synchronize_session=False)

        db.commit()
def test_delete_account_security_data(db):
    unique_id = uuid4().hex
    now = datetime.now(timezone.utc)

    user = models.User(
        name="Security Data Test",
        email=f"security_{unique_id}@example.com",
        password_hash="test_hash",
    )

    db.add(user)
    db.flush()

    user_id = user.id

    try:
        project = models.Project(
            title="Security Test Project",
            description="Test security data deletion",
            user_id=user_id,
        )

        db.add(project)
        db.flush()

        project_id = project.id

        refresh_token = models.RefreshToken(
            user_id=user_id,
            token_hash=uuid4().hex,
            created_at=now,
            expires_at=now + timedelta(days=7),
            revoked=False,
        )

        db.add(refresh_token)

        db.execute(
            text("""
                INSERT INTO ai_daily_usage
                (user_id, usage_day, request_count)
                VALUES (:user_id, :usage_day, 3)
            """),
            {
                "user_id": user_id,
                "usage_day": now.date(),
            },
        )

        db.commit()

        cache_key = uuid4().hex

        with closing(open_cache()) as cache:
            cache.execute(
                """
                INSERT INTO translations
                (
                    cache_key,
                    translated_text,
                    user_id,
                    project_id
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    cache_key,
                    "Test translation",
                    user_id,
                    project_id,
                ),
            )
            cache.commit()

        with patch(
            "app.main.delete_file_from_r2"
        ) as mock_delete:

            result = delete_account(
                db=db,
                current_user=user,
            )

            mock_delete.assert_not_called()

        assert result["message"] == (
            "Account deleted successfully"
        )

        db.expire_all()

        assert db.query(models.User).filter_by(
            id=user_id
        ).count() == 0

        assert db.query(models.RefreshToken).filter_by(
            user_id=user_id
        ).count() == 0

        ai_usage_count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM ai_daily_usage
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        ).scalar()

        assert ai_usage_count == 0

        with closing(open_cache()) as cache:
            translation_count = cache.execute(
                """
                SELECT COUNT(*)
                FROM translations
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()[0]

        assert translation_count == 0

    finally:
        db.rollback()

        db.execute(
            text("""
                DELETE FROM ai_daily_usage
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )

        db.query(models.User).filter_by(
            id=user_id
        ).delete(synchronize_session=False)

        db.commit()

        with closing(open_cache()) as cache:
            cache.execute(
                """
                DELETE FROM translations
                WHERE user_id = ?
                """,
                (user_id,),
            )
            cache.commit()
def test_delete_account_active_ai_request(db):
    unique_id = uuid4().hex
    now = datetime.now(timezone.utc)

    user = models.User(
        name="Active AI Test",
        email=f"active_{unique_id}@example.com",
        password_hash="test_hash",
    )

    db.add(user)
    db.flush()

    user_id = user.id

    try:
        db.execute(
            text("""
                INSERT INTO ai_active_requests
                (user_id, request_id, expires_at)
                VALUES (:user_id, :request_id, :expires_at)
            """),
            {
                "user_id": user_id,
                "request_id": uuid4().hex,
                "expires_at": now + timedelta(minutes=10),
            },
        )

        db.commit()

        with patch(
            "app.main.delete_file_from_r2"
        ) as mock_delete:

            with pytest.raises(HTTPException) as error:
                delete_account(
                    db=db,
                    current_user=user,
                )

            assert error.value.status_code == 409

            mock_delete.assert_not_called()

        db.expire_all()

        assert db.query(models.User).filter_by(
            id=user_id
        ).count() == 1

    finally:
        db.rollback()

        db.execute(
            text("""
                DELETE FROM ai_active_requests
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )

        db.query(models.User).filter_by(
            id=user_id
        ).delete(synchronize_session=False)

        db.commit()
def test_delete_account_r2_failure(db):
    unique_id = uuid4().hex

    user = models.User(
        name="R2 Failure Test",
        email=f"r2_{unique_id}@example.com",
        password_hash="test_hash",
    )

    db.add(user)
    db.flush()

    user_id = user.id

    try:
        project = models.Project(
            title="R2 Failure Project",
            description="Test rollback",
            user_id=user_id,
        )

        db.add(project)
        db.flush()

        project_id = project.id

        object_key = (
            f"users/{user_id}/"
            f"projects/{project_id}/test.pdf"
        )

        project_file = models.ProjectFile(
            project_id=project_id,
            filename="test.pdf",
            file_path=f"r2://{object_key}",
        )

        db.add(project_file)
        db.commit()

        file_id = project_file.id

        with patch(
            "app.main.delete_file_from_r2",
            side_effect=RuntimeError("R2 failure"),
        ) as mock_delete:

            with pytest.raises(HTTPException) as error:
                delete_account(
                    db=db,
                    current_user=user,
                )

            assert error.value.status_code == 500

            mock_delete.assert_called_once_with(
                object_key
            )

        db.expire_all()

        assert db.query(models.User).filter_by(
            id=user_id
        ).count() == 1

        assert db.query(models.Project).filter_by(
            id=project_id
        ).count() == 1

        assert db.query(models.ProjectFile).filter_by(
            id=file_id
        ).count() == 1

    finally:
        db.rollback()

        db.query(models.User).filter_by(
            id=user_id
        ).delete(synchronize_session=False)

        db.commit()