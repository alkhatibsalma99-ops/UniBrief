from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.main import upload_file, MAX_PDF_SIZE


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def user():
    return MagicMock(id=1)


def make_file(filename, content):
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
    )


# 1. Successful PDF upload
def test_upload_pdf_success(db, user):
    file = make_file(
        "document.pdf",
        b"%PDF-1.4 test content",
    )

    with patch("app.main.get_owned_project"), \
         patch("app.main.upload_file_to_r2") as upload:

        result = upload_file(
            project_id=10,
            file=file,
            db=db,
            current_user=user,
        )

        upload.assert_called_once()

        arguments = upload.call_args.kwargs

        assert arguments["object_key"].startswith(
            "users/1/projects/10/"
        )

        assert arguments["file_bytes"].startswith(
            b"%PDF-"
        )

        assert result["filename"] == "document.pdf"

        db.add.assert_called_once()
        db.commit.assert_called_once()


# 2. Reject non-PDF files
def test_reject_non_pdf(db, user):
    file = make_file("document.txt", b"Hello")

    with patch("app.main.get_owned_project"), \
         patch("app.main.upload_file_to_r2") as upload:

        with pytest.raises(HTTPException) as error:
            upload_file(10, file, db, user)

        assert error.value.status_code == 400
        upload.assert_not_called()


# 3. Reject empty files
def test_reject_empty_pdf(db, user):
    file = make_file("empty.pdf", b"")

    with patch("app.main.get_owned_project"), \
         patch("app.main.upload_file_to_r2") as upload:

        with pytest.raises(HTTPException) as error:
            upload_file(10, file, db, user)

        assert error.value.status_code == 400
        upload.assert_not_called()


# 4. Reject invalid PDF content
def test_reject_invalid_pdf(db, user):
    file = make_file(
        "invalid.pdf",
        b"This is not a PDF",
    )

    with patch("app.main.get_owned_project"), \
         patch("app.main.upload_file_to_r2") as upload:

        with pytest.raises(HTTPException) as error:
            upload_file(10, file, db, user)

        assert error.value.status_code == 400
        upload.assert_not_called()


# 5. Reject oversized PDF
def test_reject_large_pdf(db, user):
    content = b"%PDF-" + b"x" * MAX_PDF_SIZE
    file = make_file("large.pdf", content)

    with patch("app.main.get_owned_project"), \
         patch("app.main.upload_file_to_r2") as upload:

        with pytest.raises(HTTPException) as error:
            upload_file(10, file, db, user)

        assert error.value.status_code == 413
        upload.assert_not_called()


# 6. Reject unauthorized project access
def test_reject_wrong_owner(db, user):
    file = make_file("document.pdf", b"%PDF-1.4")

    with patch(
        "app.main.get_owned_project",
        side_effect=HTTPException(
            status_code=404,
            detail="Project not found",
        ),
    ), patch("app.main.upload_file_to_r2") as upload:

        with pytest.raises(HTTPException) as error:
            upload_file(10, file, db, user)

        assert error.value.status_code == 404
        upload.assert_not_called()
        db.add.assert_not_called()


# 7. Handle R2 storage failure
def test_upload_r2_failure(db, user):
    file = make_file("document.pdf", b"%PDF-1.4")

    with patch("app.main.get_owned_project"), \
         patch(
             "app.main.upload_file_to_r2",
             side_effect=RuntimeError("Storage failure"),
         ):

        with pytest.raises(HTTPException) as error:
            upload_file(10, file, db, user)

        assert error.value.status_code == 502
        db.add.assert_not_called()
        db.commit.assert_not_called()
def test_upload_database_failure(db, user):
    file = make_file(
        "document.pdf",
        b"%PDF-1.4",
    )

    db.flush.side_effect = RuntimeError(
        "Database failure"
    )

    with (
        patch("app.main.get_owned_project"),
        patch("app.main.upload_file_to_r2") as upload,
        patch("app.main.delete_file_from_r2") as cleanup,
    ):
        with pytest.raises(HTTPException) as error:
            upload_file(10, file, db, user)

        assert error.value.status_code == 500

        db.rollback.assert_called_once()
        db.commit.assert_not_called()

        object_key = upload.call_args.kwargs["object_key"]

        cleanup.assert_called_once_with(object_key)