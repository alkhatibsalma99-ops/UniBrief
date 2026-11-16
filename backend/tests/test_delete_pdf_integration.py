
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app import models
from app.main import delete_project_pdf


PROJECT_ID = 10
FILE_ID = 20
USER_ID = 1

R2_PATH = (
    f"r2://users/{USER_ID}/"
    f"projects/{PROJECT_ID}/document.pdf"
)


@pytest.fixture
def setup_delete():
    db = MagicMock()

    user = models.User(
        id=USER_ID,
        name="Test User",
        email="test@example.com",
        password_hash="test-hash",
    )

    project_file = models.ProjectFile(
        id=FILE_ID,
        project_id=PROJECT_ID,
        filename="document.pdf",
        file_path=R2_PATH,
    )

    # Query for locking the file row.
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = project_file

    # Queries returning requirement IDs.
    db.query.return_value.filter.return_value.all.return_value = [
        (30,)
    ]

    return db, user, project_file


def test_delete_pdf_success(setup_delete):
    db, user, project_file = setup_delete

    with (
        patch(
            "app.main.get_owned_project_file",
            return_value=project_file,
        ),
        patch("app.main.delete_file_from_r2") as mock_r2,
    ):
        result = delete_project_pdf(
            PROJECT_ID, FILE_ID, db, user
        )

    assert result["file_id"] == FILE_ID
    assert result["project_id"] == PROJECT_ID
    assert result["message"] == "PDF deleted successfully"

    db.delete.assert_called_once_with(project_file)
    db.flush.assert_called_once()
    db.commit.assert_called_once()

    mock_r2.assert_called_once_with(
        f"users/{USER_ID}/projects/{PROJECT_ID}/document.pdf"
    )


def test_delete_pdf_wrong_owner(setup_delete):
    db, user, _ = setup_delete

    with patch(
        "app.main.get_owned_project_file",
        side_effect=HTTPException(
            status_code=404,
            detail="Project not found",
        ),
    ):
        with pytest.raises(HTTPException) as error:
            delete_project_pdf(
                PROJECT_ID, FILE_ID, db, user
            )

    assert error.value.status_code == 404
    db.commit.assert_not_called()


def test_delete_pdf_invalid_r2_path(setup_delete):
    db, user, project_file = setup_delete

    project_file.file_path = (
        "r2://users/999/projects/10/document.pdf"
    )

    with patch(
        "app.main.get_owned_project_file",
        return_value=project_file,
    ):
        with pytest.raises(HTTPException) as error:
            delete_project_pdf(
                PROJECT_ID, FILE_ID, db, user
            )

    assert error.value.status_code == 400
    db.commit.assert_not_called()


def test_delete_pdf_r2_failure(setup_delete):
    db, user, project_file = setup_delete

    with (
        patch(
            "app.main.get_owned_project_file",
            return_value=project_file,
        ),
        patch(
            "app.main.delete_file_from_r2",
            side_effect=RuntimeError("R2 unavailable"),
        ),
    ):
        with pytest.raises(HTTPException) as error:
            delete_project_pdf(
                PROJECT_ID, FILE_ID, db, user
            )

    assert error.value.status_code == 502
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_delete_pdf_database_failure(setup_delete):
    db, user, project_file = setup_delete
    db.commit.side_effect = RuntimeError("Database unavailable")

    with (
        patch(
            "app.main.get_owned_project_file",
            return_value=project_file,
        ),
        patch("app.main.delete_file_from_r2") as mock_r2,
    ):
        with pytest.raises(HTTPException) as error:
            delete_project_pdf(
                PROJECT_ID, FILE_ID, db, user
            )

    assert error.value.status_code == 502
    db.rollback.assert_called_once()

    # Demonstrates that R2 deletion happened
    # before the failed database commit.
    mock_r2.assert_called_once()
