
from contextlib import nullcontext
from uuid import uuid4
from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import models
from app.database import SessionLocal, engine

from app.main import (
    app,
    get_db,
    get_current_user,
)


# ==================================================
# TEST DATABASE FIXTURE
# ==================================================

@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()

    session = SessionLocal(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session

    finally:
        session.close()

        if transaction.is_active:
            transaction.rollback()

        connection.close()


# ==================================================
# TEST USERS
# ==================================================

@pytest.fixture
def user(db):
    test_user = models.User(
        name="File Role Test User",
        email=f"{uuid4()}@example.com",
        password_hash="test-password-hash",
    )

    db.add(test_user)
    db.commit()
    db.refresh(test_user)

    return test_user


@pytest.fixture
def other_user(db):
    test_user = models.User(
        name="Other Test User",
        email=f"{uuid4()}@example.com",
        password_hash="test-password-hash",
    )

    db.add(test_user)
    db.commit()
    db.refresh(test_user)

    return test_user


# ==================================================
# TEST PROJECT
# ==================================================

@pytest.fixture
def project(db, user):
    test_project = models.Project(
        title="File Roles Test Project",
        description="Temporary test project",
        user_id=user.id,
    )

    db.add(test_project)
    db.commit()
    db.refresh(test_project)

    return test_project


# ==================================================
# TEST CLIENT
# ==================================================

@pytest.fixture
def client(db, user):

    def override_get_db():
        try:
            yield db
        finally:
            db.rollback()

    def override_current_user():
        return user

    fastapi_app = app.app

    previous_overrides = (
        fastapi_app.dependency_overrides.copy()
    )

    fastapi_app.dependency_overrides[get_db] = (
        override_get_db
    )

    fastapi_app.dependency_overrides[
        get_current_user
    ] = override_current_user

    try:
        with TestClient(app) as test_client:
            yield test_client

    finally:
        fastapi_app.dependency_overrides.clear()

        fastapi_app.dependency_overrides.update(
            previous_overrides
        )


# ==================================================
# BLOCK REAL AI CALLS
# ==================================================


@pytest.fixture(autouse=True)
def protect_ai():

    with (
        patch(
            "app.main.extract_requirements_with_ai",
            side_effect=RuntimeError(
                "Real AI V2 calls are forbidden in tests"
            ),
        ),
        patch(
            "app.main.extract_requirements_with_evidence",
            side_effect=RuntimeError(
                "Real AI V3 calls are forbidden in tests"
            ),
        ),
        patch(
            "app.main.check_submission_with_ai",
            side_effect=RuntimeError(
                "Real submission AI calls are forbidden in tests"
            ),
        ),
        patch(
            "app.main.ai_request_slot",
            side_effect=lambda *args, **kwargs: (
                nullcontext()
            ),
        ),
        patch(
    "app.main.check_submission_with_evidence",
    side_effect=RuntimeError(
        "Real submission evidence AI calls are forbidden in tests"
    ),
),
    ):
        yield

# ==================================================
# HELPERS
# ==================================================

def create_file(
    db,
    project,
    role="unclassified",
):
    db_file = models.ProjectFile(
        project_id=project.id,
        filename="test.pdf",
        file_path=(
            f"r2://users/{project.user_id}/"
            f"projects/{project.id}/{uuid4()}.pdf"
        ),
        file_role=role,
    )

    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    return db_file


def create_requirement(db, project, db_file):
    requirement = models.Requirement(
        project_id=project.id,
        file_id=db_file.id,
        title="Create a login page",
        description="Implement user authentication",
        priority="high",
    )

    db.add(requirement)
    db.commit()
    db.refresh(requirement)

    return requirement


def upload_pdf(client, project_id, role=None):
    data = {}

    if role is not None:
        data["file_role"] = role

    return client.post(
        f"/projects/{project_id}/files",
        files={
            "file": (
                "test.pdf",
                b"%PDF-1.4 test content",
                "application/pdf",
            )
        },
        data=data,
    )


def assign_role(
    client,
    project_id,
    file_id,
    role,
):
    return client.patch(
        f"/projects/{project_id}/files/"
        f"{file_id}/role",
        json={"file_role": role},
    )


# ==================================================
# 1-3. UPLOAD FILE ROLES
# ==================================================

@pytest.mark.parametrize(
    "role, expected",
    [
        ("requirements", "requirements"),
        ("submission", "submission"),
        (None, "unclassified"),
    ],
)
def test_upload_file_roles(
    client,
    db,
    project,
    role,
    expected,
):
    project_id = project.id

    with patch(
        "app.main.upload_file_to_r2"
    ) as upload:

        response = upload_pdf(
            client,
            project_id,
            role,
        )

        assert response.status_code == 200

        result = response.json()

        assert result["file_role"] == expected

        upload.assert_called_once()

        saved_file = db.get(
            models.ProjectFile,
            result["id"],
        )

        assert saved_file is not None
        assert saved_file.file_role == expected


# ==================================================
# 4. INVALID UPLOAD ROLE
# ==================================================

def test_invalid_upload_role(client, project):

    with patch(
        "app.main.upload_file_to_r2"
    ) as upload:

        response = upload_pdf(
            client,
            project.id,
            "invalid-role",
        )

        assert response.status_code == 422

        upload.assert_not_called()


# ==================================================
# 5. GET PROJECT FILES WITH ROLES
# ==================================================

def test_get_files_with_roles(
    client,
    db,
    project,
):
    for role in (
        "requirements",
        "submission",
        "unclassified",
    ):
        create_file(db, project, role)

    response = client.get(
        f"/projects/{project.id}/files"
    )

    assert response.status_code == 200

    roles = {
        item["file_role"]
        for item in response.json()
    }

    assert roles == {
        "requirements",
        "submission",
        "unclassified",
    }


# ==================================================
# 6-7. ASSIGN LEGACY FILE ROLE
# ==================================================

@pytest.mark.parametrize(
    "role",
    ["requirements", "submission"],
)
def test_assign_legacy_file_role(
    client,
    db,
    project,
    role,
):
    db_file = create_file(db, project)

    file_id = db_file.id

    response = assign_role(
        client,
        project.id,
        file_id,
        role,
    )

    assert response.status_code == 200

    assert response.json()["file_role"] == role

    db.expire_all()

    saved_file = db.get(
        models.ProjectFile,
        file_id,
    )

    assert saved_file.file_role == role


# ==================================================
# 8. SAME ROLE IS IDEMPOTENT
# ==================================================

def test_assign_same_role(
    client,
    db,
    project,
):
    db_file = create_file(
        db,
        project,
        "requirements",
    )

    response = assign_role(
        client,
        project.id,
        db_file.id,
        "requirements",
    )

    assert response.status_code == 200

    assert (
        response.json()["file_role"]
        == "requirements"
    )


# ==================================================
# 9. PREVENT CHANGING CLASSIFIED ROLE
# ==================================================

def test_cannot_change_classified_role(
    client,
    db,
    project,
):
    db_file = create_file(
        db,
        project,
        "requirements",
    )

    response = assign_role(
        client,
        project.id,
        db_file.id,
        "submission",
    )

    assert response.status_code == 409


# ==================================================
# 10-11. INVALID ASSIGNMENT
# ==================================================

@pytest.mark.parametrize(
    "role",
    ["invalid-role", "unclassified"],
)
def test_invalid_role_assignment(
    client,
    db,
    project,
    role,
):
    db_file = create_file(db, project)

    response = assign_role(
        client,
        project.id,
        db_file.id,
        role,
    )

    assert response.status_code == 422


# ==================================================
# 12. PROTECT OTHER USER'S FILE
# ==================================================

def test_cannot_assign_other_users_file(
    client,
    db,
    other_user,
):
    other_project = models.Project(
        title="Other User Project",
        description="Private project",
        user_id=other_user.id,
    )

    db.add(other_project)
    db.commit()
    db.refresh(other_project)

    db_file = create_file(
        db,
        other_project,
    )

    response = assign_role(
        client,
        other_project.id,
        db_file.id,
        "requirements",
    )

    assert response.status_code == 404


# ==================================================
# 13. PROTECT EXISTING REQUIREMENTS
# ==================================================

def test_protect_existing_requirements(
    client,
    db,
    project,
):
    db_file = create_file(db, project)

    requirement = create_requirement(
        db,
        project,
        db_file,
    )

    requirement_id = requirement.id

    response = assign_role(
        client,
        project.id,
        db_file.id,
        "submission",
    )

    assert response.status_code == 409

    assert db.get(
        models.Requirement,
        requirement_id,
    ) is not None

    assert db_file.file_role == "unclassified"


# ==================================================
# 14. PROTECT EXISTING SUBMISSION RESULTS
# ==================================================

def test_protect_existing_submission_results(
    client,
    db,
    project,
):
    requirements_file = create_file(
        db,
        project,
        "requirements",
    )

    submission_file = create_file(
        db,
        project,
    )

    requirement = create_requirement(
        db,
        project,
        requirements_file,
    )

    result = models.SubmissionResult(
        project_id=project.id,
        file_id=submission_file.id,
        requirement_id=requirement.id,
        status="fulfilled",
        feedback="Requirement completed",
    )

    db.add(result)
    db.commit()
    db.refresh(result)

    result_id = result.id

    response = assign_role(
        client,
        project.id,
        submission_file.id,
        "requirements",
    )

    assert response.status_code == 409

    assert db.get(
        models.SubmissionResult,
        result_id,
    ) is not None


# ==================================================
# 15. BLOCK WRONG AI ANALYSIS ROLE
# ==================================================

def test_submission_cannot_be_analyzed(
    client,
    db,
    project,
):
    db_file = create_file(
        db,
        project,
        "submission",
    )

    with (
        patch(
            "app.main.read_pdf_pages"
        ) as read_pdf,
        patch(
            "app.main.extract_requirements_with_evidence"
        ) as ai,
    ):
        response = client.post(
            f"/projects/{project.id}/files/"
            f"{db_file.id}/analyze"
        )

        assert response.status_code == 400

        read_pdf.assert_not_called()
        ai.assert_not_called()

# ==================================================
# 17. BLOCK WRONG SIMPLE EXTRACTION ROLE
# ==================================================

def test_submission_cannot_extract_requirements(
    client,
    db,
    project,
):
    db_file = create_file(
        db,
        project,
        "submission",
    )

    with patch(
        "app.main.read_pdf_text"
    ) as read_pdf:

        response = client.get(
            f"/projects/{project.id}/files/"
            f"{db_file.id}/requirements"
        )

        assert response.status_code == 400

        read_pdf.assert_not_called()


# ==================================================
# 18-19. VALID AI ANALYSIS + LEGACY SUPPORT
# ==================================================


@pytest.mark.parametrize(
    "role",
    ["requirements", "unclassified"],
)
def test_valid_ai_analysis(
    client,
    db,
    project,
    role,
):
    db_file = create_file(
        db,
        project,
        role,
    )

    pages = [
        {
            "page_number": 1,
            "text": "Create a login page.",
        }
    ]

    with (
        patch(
            "app.main.read_pdf_pages",
            return_value=pages,
        ) as read_pdf,

        patch(
            "app.main.extract_requirements_with_evidence",
            return_value={
                "requirements": [
                    {
                        "title": "Login page",
                        "description": (
                            "Create a login page."
                        ),
                        "priority": "high",
                        "source_page": 1,
                        "source_evidence": (
                            "Create a login page."
                        ),
                        "evidence_verified": True,
                    }
                ],
                "unverified_requirements": [],
                "statistics": {
                    "total": 1,
                    "verified": 1,
                    "unverified": 0,
                    "verification_rate": 100.0,
                },
            },
        ) as ai,
    ):

        response = client.post(
            f"/projects/{project.id}/files/"
            f"{db_file.id}/analyze"
        )

        assert response.status_code == 200

        data = response.json()

        assert len(data["requirements"]) == 1

        requirement = data["requirements"][0]

        # Existing fields

        assert requirement["title"] == "Login page"

        assert requirement["priority"] == "high"

        assert requirement["project_id"] == project.id

        assert requirement["file_id"] == db_file.id

        # New evidence fields

        assert requirement["source_page"] == 1

        assert requirement["source_evidence"] == (
            "Create a login page."
        )

        assert requirement["evidence_verified"] is True

        assert requirement["pipeline_version"] == "1.0.0"

        # Pipeline statistics

        analysis = data["analysis"]

        assert analysis["status"] == "completed"

        assert analysis["review_required"] is False

        assert analysis["statistics"]["original_count"] == 1

        assert analysis["statistics"]["valid_count"] == 1

        assert analysis["statistics"]["invalid_count"] == 0

        assert analysis["statistics"]["unique_count"] == 1

        assert analysis["statistics"]["validation_rate"] == 100.0

        # Database persistence

        assert analysis["persistence"]["inserted_count"] == 1

        assert analysis["persistence"]["reused_count"] == 0

        saved = db.get(
            models.Requirement,
            requirement["id"],
        )

        assert saved is not None

        assert saved.source_page == 1

        assert saved.source_evidence == (
            "Create a login page."
        )

        assert saved.evidence_verified is True

        assert saved.pipeline_version == "1.0.0"

        # Verify calls

        read_pdf.assert_called_once()

        ai.assert_called_once_with(pages)

# ==================================================
# 20-21. VALID SUBMISSION + LEGACY SUPPORT
# ==================================================

@pytest.mark.parametrize(
    "role",
    ["submission", "unclassified"],
)
def test_valid_submission_check(
    client,
    db,
    project,
    role,
):
    from app.submission_validator import (
        validate_submission_results,
    )

    requirements_file = create_file(
        db,
        project,
        "requirements",
    )

    submission_file = create_file(
        db,
        project,
        role,
    )

    requirement = create_requirement(
        db,
        project,
        requirements_file,
    )

    requirement_id = requirement.id

    pages = [
        {
            "page_number": 1,
            "text": "Completed login page",
        }
    ]

    def mock_submission(pages, requirements):
        return validate_submission_results(
            results=[
                {
                    "requirement_id": requirement_id,
                    "status": "fulfilled",
                    "feedback": "Login implemented",
                    "source_page": 1,
                    "source_evidence": "Completed login page",
                    "suggested_improvement": "",
                }
            ],
            requirements=requirements,
            pages=pages,
        )

    with (
        patch(
            "app.main.read_pdf_pages",
            return_value=pages,
        ),
        patch(
            "app.main.check_submission_with_evidence",
            side_effect=mock_submission,
        ) as ai,
    ):
        response = client.post(
            f"/projects/{project.id}/submission/"
            f"{submission_file.id}/check"
        )

        assert response.status_code == 200, response.text

        results = response.json()["results"]

        assert len(results) == 1

        assert results[0]["status"] == "fulfilled"

        assert results[0]["source_page"] == 1

        assert (
            results[0]["source_evidence"]
            == "Completed login page"
        )

        assert results[0]["evidence_verified"] is True

        assert results[0]["pipeline_version"] == "2.0.0"

        assert (
            response.json()["evaluation"]["can_persist"]
            is True
        )

        ai.assert_called_once()

        saved = db.query(
            models.SubmissionResult
        ).filter(
            models.SubmissionResult.project_id == project.id,
            models.SubmissionResult.file_id == submission_file.id,
        ).one()

        assert saved.source_page == 1

        assert saved.source_evidence == "Completed login page"

        assert saved.evidence_verified is True

        assert saved.pipeline_version == "2.0.0"


# ==================================================
# 22. DATABASE CHECK CONSTRAINT
# ==================================================

def test_database_rejects_invalid_role(
    db,
    project,
):
    invalid_file = models.ProjectFile(
        project_id=project.id,
        filename="invalid.pdf",
        file_path="r2://test/invalid.pdf",
        file_role="invalid-role",
    )

    db.add(invalid_file)

    with pytest.raises(IntegrityError):
        db.flush()

    db.rollback()


# ==================================================
# 23. DATABASE DEFAULT FOR LEGACY INSERTS
# ==================================================

def test_database_default_role(
    db,
    project,
):
    file_id = db.execute(
        text("""
            INSERT INTO project_files (
                project_id,
                filename,
                file_path,
                uploaded_at
            )
            VALUES (
                :project_id,
                :filename,
                :file_path,
                CURRENT_TIMESTAMP
            )
            RETURNING id
        """),
        {
            "project_id": project.id,
            "filename": "legacy.pdf",
            "file_path": "r2://test/legacy.pdf",
        },
    ).scalar_one()

    saved_file = db.get(
        models.ProjectFile,
        file_id,
    )

    assert saved_file.file_role == "unclassified"

def test_requirements_cannot_be_submission(
    client, db, project
):
    db_file = create_file(
        db, project, "requirements"
    )

    with (
        patch(
            "app.main.read_pdf_pages"
        ) as read_pdf,

        patch(
            "app.main.check_submission_with_evidence"
        ) as ai,
    ):
        response = client.post(
            f"/projects/{project.id}/submission/{db_file.id}/check"
        )

        assert response.status_code == 400

        read_pdf.assert_not_called()
        ai.assert_not_called()
