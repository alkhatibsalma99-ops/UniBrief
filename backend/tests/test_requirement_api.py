
from unittest.mock import patch

from app import models

from test_file_roles import (
    db,
    user,
    other_user,
    project,
    client,
    protect_ai,
    create_file,
    create_requirement,
)


# ==================================================
# HELPERS
# ==================================================

def make_pages():
    return [
        {
            "page_number": 1,
            "text": "University project assignment.",
        },
        {
            "page_number": 2,
            "text": (
                "Implement at least eight automated tests."
            ),
        },
        {
            "page_number": 3,
            "text": (
                "Implement at least nine automated tests."
            ),
        },
    ]


def make_requirement(**changes):

    requirement = {
        "title": "Implement automated tests",
        "description": (
            "Implement at least eight automated tests."
        ),
        "priority": "high",
        "source_page": 2,
        "source_evidence": (
            "Implement at least eight automated tests."
        ),
        "evidence_verified": True,
    }

    requirement.update(changes)

    return requirement


def analyze(
    client,
    project_id,
    file_id,
    requirements,
    pages=None,
):

    if pages is None:
        pages = make_pages()

    with (
        patch(
            "app.main.read_pdf_pages",
            return_value=pages,
        ),
        patch(
            "app.main.extract_requirements_with_evidence",
            return_value={
                "requirements": requirements,
                "unverified_requirements": [],
            },
        ),
    ):

        return client.post(
            f"/projects/{project_id}/files/"
            f"{file_id}/analyze"
        )


def get_saved(client, project_id):

    response = client.get(
        f"/projects/{project_id}/requirements"
    )

    assert response.status_code == 200

    return response.json()


def count_requirements(db, project_id, file_id):

    return (
        db.query(models.Requirement)
        .filter(
            models.Requirement.project_id == project_id,
            models.Requirement.file_id == file_id,
        )
        .count()
    )


# ==================================================
# 01. SAVE AND RETRIEVE EVIDENCE
# ==================================================

def test_save_and_retrieve_evidence(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    response = analyze(
        client,
        project.id,
        db_file.id,
        [make_requirement()],
    )

    assert response.status_code == 200

    data = response.json()

    saved = data["requirements"][0]

    assert saved["source_page"] == 2

    assert saved["source_evidence"] == (
        "Implement at least eight automated tests."
    )

    assert saved["evidence_verified"] is True

    assert saved["pipeline_version"] == "1.0.0"

    record = db.get(
        models.Requirement,
        saved["id"],
    )

    assert record is not None
    assert record.source_page == 2
    assert record.evidence_verified is True

    retrieved = get_saved(
        client, project.id
    )

    assert retrieved == [saved]


# ==================================================
# 02. REJECT INVENTED EVIDENCE
# ==================================================

def test_reject_invented_evidence(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    valid = make_requirement()

    invalid = make_requirement(
        title="Invented requirement",
        source_evidence="This text does not exist.",
        evidence_verified=True,
    )

    response = analyze(
        client,
        project.id,
        db_file.id,
        [valid, invalid],
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["requirements"]) == 1

    assert data["analysis"]["review_required"] is True

    assert (
        data["analysis"]["statistics"]["invalid_count"]
        == 1
    )

    assert len(
        data["analysis"]["invalid_requirements"]
    ) == 1

    assert count_requirements(
        db, project.id, db_file.id
    ) == 1


# ==================================================
# 03. REJECT WRONG SOURCE PAGE
# ==================================================

def test_reject_wrong_source_page(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    invalid = make_requirement(
        source_page=1
    )

    response = analyze(
        client,
        project.id,
        db_file.id,
        [invalid],
    )

    assert response.status_code == 200

    data = response.json()

    assert data["requirements"] == []

    assert data["analysis"]["status"] == "failed"

    assert count_requirements(
        db, project.id, db_file.id
    ) == 0


# ==================================================
# 04. REMOVE EXACT DUPLICATES
# ==================================================

def test_exact_duplicates_not_saved_twice(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    response = analyze(
        client,
        project.id,
        db_file.id,
        [
            make_requirement(),
            make_requirement(),
        ],
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["requirements"]) == 1

    assert (
        data["analysis"]["statistics"]
        ["exact_duplicates_count"] == 1
    )

    assert count_requirements(
        db, project.id, db_file.id
    ) == 1


# ==================================================
# 05. PRESERVE SIMILAR REQUIREMENTS
# ==================================================

def test_similar_requirements_preserved(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    first = make_requirement()

    second = make_requirement(
        description=(
            "Implement at least nine automated tests."
        ),
        source_page=3,
        source_evidence=(
            "Implement at least nine automated tests."
        ),
    )

    response = analyze(
        client,
        project.id,
        db_file.id,
        [first, second],
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["requirements"]) == 2

    assert (
        data["analysis"]["statistics"]
        ["possible_duplicates_count"] == 1
    )

    assert data["analysis"]["review_required"] is True

    assert count_requirements(
        db, project.id, db_file.id
    ) == 2


# ==================================================
# 06. PRESERVE DIFFERENT SOURCE PAGES
# ==================================================

def test_different_source_pages_preserved(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    pages = make_pages()

    pages[2]["text"] = (
        "Implement at least eight automated tests."
    )

    first = make_requirement()

    second = make_requirement(
        source_page=3
    )

    response = analyze(
        client,
        project.id,
        db_file.id,
        [first, second],
        pages=pages,
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["requirements"]) == 2

    assert {
        item["source_page"]
        for item in data["requirements"]
    } == {2, 3}

    assert (
        data["analysis"]["persistence"]
        ["preserved_source_count"] == 1
    )

    assert count_requirements(
        db, project.id, db_file.id
    ) == 2


# ==================================================
# 07. REPEATED ANALYSIS
# ==================================================

def test_repeated_analysis_reuses_existing_id(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    first = analyze(
        client,
        project.id,
        db_file.id,
        [make_requirement()],
    )

    assert first.status_code == 200

    second = analyze(
        client,
        project.id,
        db_file.id,
        [make_requirement()],
    )

    assert second.status_code == 200

    first_data = first.json()
    second_data = second.json()

    assert (
        first_data["requirements"][0]["id"]
        == second_data["requirements"][0]["id"]
    )

    assert (
        second_data["analysis"]["persistence"]
        ["inserted_count"] == 0
    )

    assert (
        second_data["analysis"]["persistence"]
        ["reused_count"] == 1
    )

    assert count_requirements(
        db, project.id, db_file.id
    ) == 1


# ==================================================
# 08. PRESERVE LEGACY REQUIREMENTS
# ==================================================

def test_legacy_requirements_preserved(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    legacy = create_requirement(
        db, project, db_file
    )

    legacy_id = legacy.id

    response = analyze(
        client,
        project.id,
        db_file.id,
        [make_requirement()],
    )

    assert response.status_code == 200

    records = get_saved(
        client, project.id
    )

    assert len(records) == 2

    old_record = next(
        item for item in records
        if item["id"] == legacy_id
    )

    assert old_record["title"] == (
        "Create a login page"
    )

    assert old_record["description"] == (
        "Implement user authentication"
    )

    assert old_record["source_page"] is None
    assert old_record["source_evidence"] is None
    assert old_record["evidence_verified"] is None
    assert old_record["pipeline_version"] is None


# ==================================================
# 09. PRESERVE EXISTING CHECKLIST
# ==================================================

def test_existing_checklist_preserved(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    legacy = create_requirement(
        db, project, db_file
    )

    legacy_id = legacy.id

    checklist = models.ChecklistItem(
        project_id=project.id,
        requirement_id=legacy_id,
        title="Existing checklist task",
        completed=1,
    )

    db.add(checklist)
    db.commit()
    db.refresh(checklist)

    checklist_id = checklist.id

    response = analyze(
        client,
        project.id,
        db_file.id,
        [make_requirement()],
    )

    assert response.status_code == 200

    db.expire_all()

    saved = db.get(
        models.ChecklistItem,
        checklist_id,
    )

    assert saved is not None

    assert saved.requirement_id == legacy_id

    assert saved.title == "Existing checklist task"

    assert saved.completed == 1


# ==================================================
# 10. PRESERVE HISTORICAL SUBMISSION REPORT
# ==================================================

def test_historical_submission_report_preserved(
    client, db, project
):

    requirements_file = create_file(
        db, project, "requirements"
    )

    submission_file = create_file(
        db, project, "submission"
    )

    legacy = create_requirement(
        db, project, requirements_file
    )

    legacy_id = legacy.id

    result = models.SubmissionResult(
        project_id=project.id,
        file_id=submission_file.id,
        requirement_id=legacy_id,
        status="fulfilled",
        feedback="Historical evaluation.",
    )

    db.add(result)
    db.commit()
    db.refresh(result)

    result_id = result.id

    response = analyze(
        client,
        project.id,
        requirements_file.id,
        [make_requirement()],
    )

    assert response.status_code == 200

    db.expire_all()

    saved = db.get(
        models.SubmissionResult,
        result_id,
    )

    assert saved is not None

    assert saved.requirement_id == legacy_id

    assert saved.file_id == submission_file.id

    assert saved.status == "fulfilled"

    assert saved.feedback == "Historical evaluation."

    report = client.get(
        f"/projects/{project.id}/submission/"
        f"{submission_file.id}/report"
    )

    assert report.status_code == 200


# ==================================================
# 11. UNAUTHORIZED ACCESS
# ==================================================

def test_other_user_cannot_access_requirements(
    client, db, other_user
):

    foreign_project = models.Project(
        title="Private project",
        description="Another user's project",
        user_id=other_user.id,
    )

    db.add(foreign_project)
    db.commit()
    db.refresh(foreign_project)

    foreign_file = create_file(
        db,
        foreign_project,
        "requirements",
    )

    create_requirement(
        db, foreign_project, foreign_file
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
            f"/projects/{foreign_project.id}/files/"
            f"{foreign_file.id}/analyze"
        )

        assert response.status_code in (403, 404)

        read_pdf.assert_not_called()
        ai.assert_not_called()

    response = client.get(
        f"/projects/{foreign_project.id}/requirements"
    )

    assert response.status_code in (403, 404)


# ==================================================
# 12. AI FAILURE
# ==================================================

def test_ai_failure_does_not_save_requirements(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    with (
        patch(
            "app.main.read_pdf_pages",
            return_value=make_pages(),
        ),
        patch(
            "app.main.extract_requirements_with_evidence",
            side_effect=RuntimeError(
                "Simulated AI failure"
            ),
        ),
    ):

        response = client.post(
            f"/projects/{project.id}/files/"
            f"{db_file.id}/analyze"
        )

    assert response.status_code == 500

    assert count_requirements(
        db, project.id, db_file.id
    ) == 0


# ==================================================
# 13. DATABASE ROLLBACK
# ==================================================

def test_database_failure_rolls_back_all_requirements(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    project_id = project.id
    file_id = db_file.id

    legacy = create_requirement(
        db, project, db_file
    )

    legacy_id = legacy.id

    first = make_requirement()

    second = make_requirement(
        description=(
            "Implement at least nine automated tests."
        ),
        source_page=3,
        source_evidence=(
            "Implement at least nine automated tests."
        ),
    )

    original_flush = db.flush

    flush_count = 0

    def fail_second_flush(*args, **kwargs):

        nonlocal flush_count

        flush_count += 1

        if flush_count == 2:

            raise RuntimeError(
                "Simulated database failure"
            )

        return original_flush(
            *args, **kwargs
        )

    with patch.object(
        db,
        "flush",
        side_effect=fail_second_flush,
    ):

        response = analyze(
            client,
            project_id,
            file_id,
            [first, second],
        )

    assert response.status_code == 500

    assert flush_count >= 2

    assert count_requirements(
        db, project_id, file_id
    ) == 1

    assert db.get(
        models.Requirement,
        legacy_id,
    ) is not None


# ==================================================
# 14. EMPTY PDF
# ==================================================

def test_empty_pdf_does_not_call_ai(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    pages = [
        {
            "page_number": 1,
            "text": "",
        },
        {
            "page_number": 2,
            "text": "   ",
        },
    ]

    with (
        patch(
            "app.main.read_pdf_pages",
            return_value=pages,
        ),
        patch(
            "app.main.extract_requirements_with_evidence"
        ) as ai,
    ):

        response = client.post(
            f"/projects/{project.id}/files/"
            f"{db_file.id}/analyze"
        )

        assert response.status_code == 400

        ai.assert_not_called()

    assert count_requirements(
        db, project.id, db_file.id
    ) == 0


# ==================================================
# 15. EMPTY AI RESULT
# ==================================================

def test_empty_ai_result(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    response = analyze(
        client,
        project.id,
        db_file.id,
        [],
    )

    assert response.status_code == 200

    data = response.json()

    assert data["requirements"] == []

    assert data["analysis"]["status"] == "empty"

    assert data["analysis"]["review_required"] is False

    assert count_requirements(
        db, project.id, db_file.id
    ) == 0


# ==================================================
# 16. REJECT ALL INVALID AI REQUIREMENTS
# ==================================================

def test_all_invalid_requirements_rejected(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    requirements = [
        make_requirement(
            priority="invalid-priority"
        ),
        make_requirement(
            source_evidence="Invented evidence."
        ),
    ]

    response = analyze(
        client,
        project.id,
        db_file.id,
        requirements,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["requirements"] == []

    assert data["analysis"]["status"] == "failed"

    assert data["analysis"]["review_required"] is True

    assert (
        data["analysis"]["statistics"]["invalid_count"]
        == 2
    )

    assert count_requirements(
        db, project.id, db_file.id
    ) == 0
