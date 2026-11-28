
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
)


# ==================================================
# HELPERS
# ==================================================

def make_requirement(
    db,
    project,
    db_file,
    title="Implement authentication",
    priority="high",
    with_evidence=True,
):

    requirement = models.Requirement(
        project_id=project.id,
        file_id=db_file.id,
        title=title,
        description=f"Complete task: {title}",
        priority=priority,
        source_page=2 if with_evidence else None,
        source_evidence=(
            "Implement authentication."
            if with_evidence else None
        ),
        evidence_verified=(
            True if with_evidence else None
        ),
        pipeline_version=(
            "1.0.0" if with_evidence else None
        ),
    )

    db.add(requirement)
    db.commit()
    db.refresh(requirement)

    return requirement


def generate(client, project_id):

    return client.post(
        f"/projects/{project_id}/checklist/generate"
    )


def get_items(client, project_id):

    response = client.get(
        f"/projects/{project_id}/checklist"
    )

    assert response.status_code == 200

    return response.json()


def count_items(db, project_id):

    return (
        db.query(models.ChecklistItem)
        .filter(
            models.ChecklistItem.project_id == project_id
        )
        .count()
    )


# ==================================================
# 1. GENERATE CHECKLIST
# ==================================================

def test_generate_smart_checklist(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    requirement = make_requirement(
        db, project, db_file
    )

    response = generate(client, project.id)

    assert response.status_code == 200

    items = response.json()

    assert len(items) == 1
    assert items[0]["requirement_id"] == requirement.id
    assert items[0]["completed"] is False
    assert items[0]["priority"] == "high"
    assert count_items(db, project.id) == 1


# ==================================================
# 2. NO DUPLICATES
# ==================================================

def test_regenerate_without_duplicates(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    make_requirement(db, project, db_file)

    first = generate(client, project.id)
    second = generate(client, project.id)

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json() == second.json()
    assert count_items(db, project.id) == 1


# ==================================================
# 3. PRESERVE COMPLETED ITEMS
# ==================================================

def test_regenerate_preserves_progress(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    make_requirement(db, project, db_file)

    response = generate(client, project.id)

    assert response.status_code == 200

    item_id = response.json()[0]["id"]

    update = client.patch(
        f"/checklist/{item_id}",
        json={"completed": True},
    )

    assert update.status_code == 200
    assert update.json()["completed"] is True

    regenerated = generate(client, project.id)

    assert regenerated.status_code == 200

    item = regenerated.json()[0]

    assert item["id"] == item_id
    assert item["completed"] is True

    saved = get_items(client, project.id)

    assert saved[0]["completed"] is True
    assert count_items(db, project.id) == 1


# ==================================================
# 4. ADD NEW REQUIREMENTS
# ==================================================

def test_regenerate_adds_only_new_items(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    make_requirement(
        db, project, db_file,
        title="Create login page",
    )

    first = generate(client, project.id)

    assert first.status_code == 200

    old_id = first.json()[0]["id"]

    update = client.patch(
        f"/checklist/{old_id}",
        json={"completed": True},
    )

    assert update.status_code == 200

    make_requirement(
        db, project, db_file,
        title="Create database",
    )

    second = generate(client, project.id)

    assert second.status_code == 200

    items = second.json()

    assert len(items) == 2

    old_item = next(
        item for item in items
        if item["id"] == old_id
    )

    new_item = next(
        item for item in items
        if item["id"] != old_id
    )

    assert old_item["completed"] is True
    assert new_item["completed"] is False
    assert count_items(db, project.id) == 2


# ==================================================
# 5. PRIORITY SORTING
# ==================================================

def test_checklist_priority_sorting(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    for priority in ["low", "high", "medium"]:

        make_requirement(
            db, project, db_file,
            title=f"Task {priority}",
            priority=priority,
        )

    response = generate(client, project.id)

    assert response.status_code == 200

    expected = ["high", "medium", "low"]

    assert [
        item["priority"]
        for item in response.json()
    ] == expected

    assert [
        item["priority"]
        for item in get_items(client, project.id)
    ] == expected


# ==================================================
# 6. SOURCE EVIDENCE
# ==================================================

def test_checklist_returns_source_evidence(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    requirement = make_requirement(
        db, project, db_file
    )

    response = generate(client, project.id)

    assert response.status_code == 200

    item = response.json()[0]

    assert item["file_id"] == db_file.id
    assert item["source_filename"] == db_file.filename
    assert item["source_page"] == 2

    assert (
        item["source_evidence"]
        == requirement.source_evidence
    )

    assert item["evidence_verified"] is True
    assert item["pipeline_version"] == "1.0.0"
    assert item["description"] == requirement.description

    saved = get_items(client, project.id)

    assert saved[0] == item


# ==================================================
# 7. LEGACY REQUIREMENTS
# ==================================================

def test_checklist_supports_legacy_requirements(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    make_requirement(
        db, project, db_file,
        with_evidence=False,
    )

    response = generate(client, project.id)

    assert response.status_code == 200

    item = response.json()[0]

    assert item["source_page"] is None
    assert item["source_evidence"] is None
    assert item["evidence_verified"] is None
    assert item["pipeline_version"] is None


# ==================================================
# 8. UPDATE COMPLETION
# ==================================================

def test_checklist_can_be_uncompleted(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    make_requirement(db, project, db_file)

    response = generate(client, project.id)

    assert response.status_code == 200

    item_id = response.json()[0]["id"]

    for completed in [True, False]:

        update = client.patch(
            f"/checklist/{item_id}",
            json={"completed": completed},
        )

        assert update.status_code == 200
        assert update.json()["completed"] is completed
        assert update.json()["source_page"] == 2
        assert update.json()["priority"] == "high"

        items = get_items(client, project.id)

        assert items[0]["completed"] is completed


# ==================================================
# 9. EMPTY PROJECT
# ==================================================

def test_empty_project_checklist(
    client, db, project
):

    response = generate(client, project.id)

    assert response.status_code == 404
    assert get_items(client, project.id) == []
    assert count_items(db, project.id) == 0


# ==================================================
# 10. OWNERSHIP PROTECTION
# ==================================================

def test_other_user_checklist_is_protected(
    client, db, other_user
):

    other_project = models.Project(
        title="Private project",
        description="Private project description",
        user_id=other_user.id,
    )

    db.add(other_project)
    db.commit()
    db.refresh(other_project)

    db_file = create_file(
        db, other_project, "requirements"
    )

    requirement = make_requirement(
        db, other_project, db_file
    )

    item = models.ChecklistItem(
        project_id=other_project.id,
        requirement_id=requirement.id,
        title=requirement.title,
        completed=0,
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    assert generate(
        client, other_project.id
    ).status_code == 404

    assert client.get(
        f"/projects/{other_project.id}/checklist"
    ).status_code == 404

    assert client.patch(
        f"/checklist/{item.id}",
        json={"completed": True},
    ).status_code == 404

    db.refresh(item)

    assert item.completed == 0


# ==================================================
# 11. TRANSACTION ROLLBACK
# ==================================================

def test_checklist_generation_rolls_back(
    client, db, project
):

    db_file = create_file(
        db, project, "requirements"
    )

    make_requirement(db, project, db_file)

    with patch(
        "app.main.load_smart_checklist",
        side_effect=RuntimeError(
            "Simulated generation failure"
        ),
    ):

        response = generate(client, project.id)

    assert response.status_code == 500
    assert count_items(db, project.id) == 0

    # Generation must work after the failure.
    retry = generate(client, project.id)

    assert retry.status_code == 200
    assert count_items(db, project.id) == 1


# ==================================================
# 12. NO AI REQUESTS
# ==================================================


def test_checklist_does_not_call_ai(
    client, db, project
):
    db_file = create_file(
        db, project, "requirements"
    )

    make_requirement(db, project, db_file)

    with (
        patch(
            "app.main.extract_requirements_with_evidence"
        ) as extract_ai,

        patch(
            "app.main.check_submission_with_ai"
        ) as submission_ai,

        patch(
            "app.main.check_submission_with_evidence"
        ) as submission_evidence_ai,

        patch(
            "app.ai_service.client.responses.create"
        ) as openai_request,
    ):

        response = generate(client, project.id)

        assert response.status_code == 200

        item_id = response.json()[0]["id"]

        assert client.patch(
            f"/checklist/{item_id}",
            json={"completed": True},
        ).status_code == 200

        get_items(client, project.id)

        extract_ai.assert_not_called()
        submission_ai.assert_not_called()
        submission_evidence_ai.assert_not_called()
        openai_request.assert_not_called()
