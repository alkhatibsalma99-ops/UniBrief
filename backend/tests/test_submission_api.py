
from unittest.mock import patch

import pytest

from sqlalchemy.exc import SQLAlchemyError

from app import models

from app.submission_validator import (
    validate_submission_results,
)

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
# TEST DATA
# ==================================================

PAGES = [
    {
        "page_number": 1,
        "text": (
            "Login is implemented. "
            "Task creation works but deletion is missing. "
            "Password reset is not implemented. "
            "Performance testing conditions are unknown."
        ),
    }
]

STATUSES = [
    "fulfilled",
    "partially_fulfilled",
    "missing",
    "unclear",
]

EVIDENCE = [
    "Login is implemented.",
    "Task creation works but deletion is missing.",
    "Password reset is not implemented.",
    "Performance testing conditions are unknown.",
]


# ==================================================
# HELPERS
# ==================================================

@pytest.fixture
def submission_data(db, project):

    requirements_file = create_file(
        db, project, "requirements"
    )

    submission_file = create_file(
        db, project, "submission"
    )

    requirements = []

    for index in range(4):

        requirement = models.Requirement(
            project_id=project.id,
            file_id=requirements_file.id,
            title=f"Requirement {index + 1}",
            description=f"Test requirement {index + 1}",
            priority="high",
        )

        db.add(requirement)
        db.flush()

        requirements.append(requirement.id)

    db.commit()

    return {
        "project_id": project.id,
        "file_id": submission_file.id,
        "requirement_ids": requirements,
    }


def check_url(data):

    return (
        f"/projects/{data['project_id']}/submission/"
        f"{data['file_id']}/check"
    )


def results_url(data):

    return (
        f"/projects/{data['project_id']}"
        "/submission-results"
    )


def report_url(data):

    return (
        f"/projects/{data['project_id']}/submission/"
        f"{data['file_id']}/report"
    )


def valid_evaluation(pages, requirements):

    results = []

    for index, requirement in enumerate(requirements):

        results.append({
            "requirement_id": requirement["id"],
            "status": STATUSES[index],
            "feedback": f"Evaluation {index + 1}",
            "source_page": 1,
            "source_evidence": EVIDENCE[index],
            "suggested_improvement": (
                ""
                if index == 0
                else "Complete or clarify the requirement."
            ),
        })

    return validate_submission_results(
        results=results,
        requirements=requirements,
        pages=pages,
    )


def run_evaluation(client, data, evaluator):

    with (
        patch(
            "app.main.read_pdf_pages",
            return_value=PAGES,
        ),
        patch(
            "app.main.check_submission_with_evidence",
            side_effect=evaluator,
        ),
    ):

        return client.post(check_url(data))


def create_legacy_result(
    db,
    data,
    file_id=None,
):

    result = models.SubmissionResult(
        project_id=data["project_id"],
        file_id=(
            file_id
            if file_id is not None
            else data["file_id"]
        ),
        requirement_id=data["requirement_ids"][0],
        status="fulfilled",
        feedback="Original historical result",
    )

    db.add(result)
    db.commit()
    db.refresh(result)

    return result.id


def load_results(client, data):

    response = client.get(results_url(data))

    assert response.status_code == 200, response.text

    return response.json()


# ==================================================
# 1. ALL FOUR EVALUATION STATUSES
# ==================================================

def test_all_four_submission_statuses(
    client,
    submission_data,
):

    response = run_evaluation(
        client,
        submission_data,
        valid_evaluation,
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert len(body["results"]) == 4

    assert {
        result["status"]
        for result in body["results"]
    } == set(STATUSES)

    assert body["evaluation"]["can_persist"] is True

    assert body["evaluation"]["review_required"] is True

    assert body["evaluation"]["pipeline_version"] == "2.0.0"

    assert body["evaluation"]["status_counts"] == {
        "fulfilled": 1,
        "partially_fulfilled": 1,
        "missing": 1,
        "unclear": 1,
    }

    statistics = body["evaluation"]["statistics"]

    assert statistics["completion_percentage"] == 25.0

    assert statistics["coverage_rate"] == 100.0

    assert statistics["validation_rate"] == 100.0

    for result in body["results"]:

        assert result["source_page"] == 1

        assert result["evidence_verified"] is True

        assert result["source_evidence"] in EVIDENCE

        assert result["pipeline_version"] == "2.0.0"


# ==================================================
# 2. DATABASE PERSISTENCE
# ==================================================

def test_submission_evidence_is_persisted(
    client,
    db,
    submission_data,
):

    response = run_evaluation(
        client,
        submission_data,
        valid_evaluation,
    )

    assert response.status_code == 200, response.text

    saved = (
        db.query(models.SubmissionResult)
        .filter(
            models.SubmissionResult.project_id
            == submission_data["project_id"],

            models.SubmissionResult.file_id
            == submission_data["file_id"],
        )
        .all()
    )

    assert len(saved) == 4

    for result in saved:

        assert result.source_page == 1

        assert result.source_evidence in EVIDENCE

        assert result.evidence_verified is True

        assert result.pipeline_version == "2.0.0"

        if result.status != "fulfilled":

            assert result.suggested_improvement


# ==================================================
# 3. INVALID EVIDENCE PRESERVES OLD RESULTS
# ==================================================

def test_fake_evidence_preserves_old_results(
    client,
    db,
    submission_data,
):

    create_legacy_result(db, submission_data)

    before = load_results(client, submission_data)

    def invalid_evaluation(pages, requirements):

        report = valid_evaluation(
            pages,
            requirements,
        )

        results = report["results"]

        results[0]["source_evidence"] = (
            "Invented evidence that does not exist."
        )

        return validate_submission_results(
            results=results,
            requirements=requirements,
            pages=pages,
        )

    response = run_evaluation(
        client,
        submission_data,
        invalid_evaluation,
    )

    assert response.status_code == 502

    after = load_results(client, submission_data)

    assert after == before


# ==================================================
# 4. INCOMPLETE EVALUATION IS REJECTED
# ==================================================

def test_incomplete_evaluation_preserves_results(
    client,
    db,
    submission_data,
):

    create_legacy_result(db, submission_data)

    before = load_results(client, submission_data)

    def incomplete_evaluation(pages, requirements):

        report = valid_evaluation(
            pages,
            requirements,
        )

        return validate_submission_results(
            results=report["results"][:-1],
            requirements=requirements,
            pages=pages,
        )

    response = run_evaluation(
        client,
        submission_data,
        incomplete_evaluation,
    )

    assert response.status_code == 502

    assert load_results(
        client, submission_data
    ) == before


# ==================================================
# 5. AI PROVIDER FAILURE
# ==================================================

def test_ai_failure_preserves_old_results(
    client,
    db,
    submission_data,
):

    create_legacy_result(db, submission_data)

    before = load_results(client, submission_data)

    def failing_evaluation(pages, requirements):

        raise RuntimeError("Simulated AI provider failure")

    response = run_evaluation(
        client,
        submission_data,
        failing_evaluation,
    )

    assert response.status_code == 500

    assert load_results(
        client, submission_data
    ) == before


# ==================================================
# 6. DATABASE FAILURE AND ROLLBACK
# ==================================================

def test_database_failure_rolls_back_evaluation(
    client,
    db,
    submission_data,
):

    create_legacy_result(db, submission_data)

    before = load_results(client, submission_data)

    original_flush = db.flush

    insert_attempts = 0

    def failing_flush(*args, **kwargs):

        nonlocal insert_attempts

        if any(
            isinstance(item, models.SubmissionResult)
            for item in db.new
        ):

            insert_attempts += 1

            if insert_attempts == 2:

                raise SQLAlchemyError(
                    "Simulated database write failure"
                )

        return original_flush(*args, **kwargs)

    with patch.object(
        db,
        "flush",
        side_effect=failing_flush,
    ):

        response = run_evaluation(
            client,
            submission_data,
            valid_evaluation,
        )

    assert response.status_code == 500

    assert insert_attempts == 2

    assert load_results(
        client, submission_data
    ) == before


# ==================================================
# 7. RE-EVALUATION PROTECTS OTHER FILES
# ==================================================

def test_reevaluation_only_replaces_selected_file(
    client,
    db,
    project,
    submission_data,
):

    other_file = create_file(
        db, project, "submission"
    )

    other_file_id = other_file.id

    create_legacy_result(db, submission_data)

    other_result_id = create_legacy_result(
        db,
        submission_data,
        file_id=other_file_id,
    )

    before = load_results(client, submission_data)

    protected_result = next(
        result
        for result in before
        if result["id"] == other_result_id
    )

    for _ in range(2):

        response = run_evaluation(
            client,
            submission_data,
            valid_evaluation,
        )

        assert response.status_code == 200, response.text

        after = load_results(
            client,
            submission_data,
        )

        assert len(after) == 5

        selected_results = [
            result
            for result in after
            if result["file_id"]
            == submission_data["file_id"]
        ]

        assert len(selected_results) == 4

        assert protected_result in after


# ==================================================
# 8. EMPTY SUBMISSION TEXT
# ==================================================

def test_empty_submission_does_not_call_ai(
    client,
    submission_data,
):

    with (
        patch(
            "app.main.read_pdf_pages",
            return_value=[
                {
                    "page_number": 1,
                    "text": "   ",
                }
            ],
        ),
        patch(
            "app.main.check_submission_with_evidence"
        ) as ai,
    ):

        response = client.post(
            check_url(submission_data)
        )

        assert response.status_code == 400

        ai.assert_not_called()


# ==================================================
# 9. NO REQUIREMENTS
# ==================================================

def test_no_requirements_does_not_call_ai(
    client,
    db,
    project,
):

    submission_file = create_file(
        db, project, "submission"
    )

    data = {
        "project_id": project.id,
        "file_id": submission_file.id,
    }

    with (
        patch(
            "app.main.read_pdf_pages",
            return_value=PAGES,
        ),
        patch(
            "app.main.check_submission_with_evidence"
        ) as ai,
    ):

        response = client.post(check_url(data))

        assert response.status_code == 404

        ai.assert_not_called()


# ==================================================
# 10. WRONG FILE ROLE
# ==================================================

def test_requirements_file_cannot_be_evaluated(
    client,
    db,
    project,
):

    requirements_file = create_file(
        db, project, "requirements"
    )

    data = {
        "project_id": project.id,
        "file_id": requirements_file.id,
    }

    with (
        patch(
            "app.main.read_pdf_pages"
        ) as read_pdf,
        patch(
            "app.main.check_submission_with_evidence"
        ) as ai,
    ):

        response = client.post(check_url(data))

        assert response.status_code == 400

        read_pdf.assert_not_called()

        ai.assert_not_called()


# ==================================================
# 11. OTHER USER'S PROJECT
# ==================================================

def test_cannot_evaluate_other_users_submission(
    client,
    db,
    other_user,
):

    other_project = models.Project(
        title="Private project",
        description="Ownership test",
        user_id=other_user.id,
    )

    db.add(other_project)
    db.commit()
    db.refresh(other_project)

    submission_file = create_file(
        db, other_project, "submission"
    )

    data = {
        "project_id": other_project.id,
        "file_id": submission_file.id,
    }

    with (
        patch(
            "app.main.read_pdf_pages"
        ) as read_pdf,
        patch(
            "app.main.check_submission_with_evidence"
        ) as ai,
    ):

        response = client.post(check_url(data))

        assert response.status_code == 404

        read_pdf.assert_not_called()

        ai.assert_not_called()

    assert client.get(
        results_url(data)
    ).status_code == 404

    assert client.get(
        report_url(data)
    ).status_code == 404


# ==================================================
# 12. GET RESULTS WITH NEW EVIDENCE FIELDS
# ==================================================

def test_get_submission_results_with_evidence(
    client,
    submission_data,
):

    response = run_evaluation(
        client,
        submission_data,
        valid_evaluation,
    )

    assert response.status_code == 200, response.text

    results = load_results(
        client,
        submission_data,
    )

    assert len(results) == 4

    assert results == response.json()["results"]


# ==================================================
# 13. LEGACY RESULTS REMAIN READABLE
# ==================================================

def test_legacy_submission_results_are_readable(
    client,
    db,
    submission_data,
):

    create_legacy_result(db, submission_data)

    results = load_results(
        client,
        submission_data,
    )

    assert len(results) == 1

    result = results[0]

    assert result["status"] == "fulfilled"

    assert result["feedback"] == (
        "Original historical result"
    )

    assert result["source_page"] is None

    assert result["source_evidence"] is None

    assert result["evidence_verified"] is None

    assert result["suggested_improvement"] is None

    assert result["pipeline_version"] is None


# ==================================================
# 14. REPORT WITHOUT RESULTS
# ==================================================

def test_report_without_results_returns_404(
    client,
    submission_data,
):

    response = client.get(
        report_url(submission_data)
    )

    assert response.status_code == 404


# ==================================================
# 15. REQUIREMENTS CHANGE DURING EVALUATION
# ==================================================

def test_changed_requirements_preserve_old_results(
    client,
    db,
    submission_data,
):

    create_legacy_result(db, submission_data)

    before = load_results(client, submission_data)

    def changed_evaluation(pages, requirements):

        report = valid_evaluation(
            pages,
            requirements,
        )

        requirement = db.get(
            models.Requirement,
            requirements[0]["id"],
        )

        requirement.description = (
            "Requirement changed during evaluation"
        )

        db.flush()

        return report

    response = run_evaluation(
        client,
        submission_data,
        changed_evaluation,
    )

    assert response.status_code == 409

    assert load_results(
        client, submission_data
    ) == before


# ==================================================
# 16. COMPLETE SMART SUBMISSION REPORT
# ==================================================

def test_complete_smart_submission_report(
    client,
    submission_data,
):
    response = run_evaluation(
        client,
        submission_data,
        valid_evaluation,
    )

    assert response.status_code == 200, response.text

    report_response = client.get(
        report_url(submission_data)
    )

    assert report_response.status_code == 200

    report = report_response.json()

    assert report["project_id"] == submission_data["project_id"]

    assert report["file_id"] == submission_data["file_id"]

    assert report["submission_filename"] == "test.pdf"

    assert report["summary"] == {
        "total_requirements": 4,
        "fulfilled": 1,
        "partially_fulfilled": 1,
        "missing": 1,
        "unclear": 1,
        "unknown_status_count": 0,
        "completion_percentage": 25.0,
    }

    assert report["evidence_summary"] == {
        "verified_evidence": 4,
        "unverified_evidence": 0,
        "evidence_not_available": 0,
        "evidence_coverage_percentage": 100.0,
        "missing_required_evidence": 0,
    }

    assert report["evaluation"] == {
        "pipeline_versions": ["2.0.0"],
        "is_legacy_report": False,
        "legacy_results": 0,
        "review_required": True,
    }

    assert report["details"] == response.json()["results"]


# ==================================================
# 17. LEGACY SUBMISSION REPORT
# ==================================================

def test_legacy_submission_report(
    client,
    db,
    submission_data,
):
    create_legacy_result(
        db,
        submission_data,
    )

    response = client.get(
        report_url(submission_data)
    )

    assert response.status_code == 200

    report = response.json()

    assert report["summary"]["total_requirements"] == 1

    assert report["summary"]["fulfilled"] == 1

    assert report["summary"]["completion_percentage"] == 100.0

    evidence = report["evidence_summary"]

    assert evidence["verified_evidence"] == 0

    assert evidence["unverified_evidence"] == 0

    assert evidence["evidence_not_available"] == 1

    assert evidence["evidence_coverage_percentage"] == 0.0

    assert evidence["missing_required_evidence"] == 1

    evaluation = report["evaluation"]

    assert evaluation["is_legacy_report"] is True

    assert evaluation["legacy_results"] == 1

    assert evaluation["pipeline_versions"] == []

    assert evaluation["review_required"] is True

    assert report["details"][0]["source_evidence"] is None


# ==================================================
# 18. FULLY COMPLETED REPORT
# ==================================================

def test_fully_completed_report(
    client,
    submission_data,
):
    def fulfilled_evaluation(pages, requirements):

        results = [
            {
                "requirement_id": requirement["id"],
                "status": "fulfilled",
                "feedback": "Requirement completed.",
                "source_page": 1,
                "source_evidence": "Requirement is implemented.",
                "suggested_improvement": "",
            }
            for requirement in requirements
        ]

        return validate_submission_results(
            results=results,
            requirements=requirements,
            pages=pages,
        )

    with (
        patch(
            "app.main.read_pdf_pages",
            return_value=[
                {
                    "page_number": 1,
                    "text": "Requirement is implemented.",
                }
            ],
        ),
        patch(
            "app.main.check_submission_with_evidence",
            side_effect=fulfilled_evaluation,
        ),
    ):
        response = client.post(
            check_url(submission_data)
        )

    assert response.status_code == 200, response.text

    response = client.get(
        report_url(submission_data)
    )

    assert response.status_code == 200

    report = response.json()

    assert report["summary"]["fulfilled"] == 4

    assert report["summary"]["completion_percentage"] == 100.0

    assert (
        report["evidence_summary"]["evidence_coverage_percentage"]
        == 100.0
    )

    assert report["evaluation"]["review_required"] is False


# ==================================================
# 19. PARTIAL COMPLETION IS NOT FULL COMPLETION
# ==================================================

def test_partial_completion_percentage(
    client,
    submission_data,
):
    def partial_evaluation(pages, requirements):

        results = [
            {
                "requirement_id": requirement["id"],
                "status": "partially_fulfilled",
                "feedback": "Requirement is partially completed.",
                "source_page": 1,
                "source_evidence": (
                    "Task creation works but deletion is missing."
                ),
                "suggested_improvement": (
                    "Implement task deletion."
                ),
            }
            for requirement in requirements
        ]

        return validate_submission_results(
            results=results,
            requirements=requirements,
            pages=pages,
        )

    response = run_evaluation(
        client,
        submission_data,
        partial_evaluation,
    )

    assert response.status_code == 200, response.text

    response = client.get(
        report_url(submission_data)
    )

    assert response.status_code == 200

    report = response.json()

    assert report["summary"]["partially_fulfilled"] == 4

    assert report["summary"]["fulfilled"] == 0

    assert report["summary"]["completion_percentage"] == 0.0

    assert (
        report["evidence_summary"]["evidence_coverage_percentage"]
        == 100.0
    )


# ==================================================
# 20. MISSING EVIDENCE REQUIRES REVIEW
# ==================================================

def test_report_detects_missing_required_evidence(
    client,
    db,
    submission_data,
):
    result = models.SubmissionResult(
        project_id=submission_data["project_id"],
        file_id=submission_data["file_id"],
        requirement_id=submission_data["requirement_ids"][0],
        status="fulfilled",
        feedback="Stored result without evidence",
        source_page=None,
        source_evidence=None,
        evidence_verified=None,
        suggested_improvement="",
        pipeline_version="2.0.0",
    )

    db.add(result)
    db.commit()

    response = client.get(
        report_url(submission_data)
    )

    assert response.status_code == 200

    report = response.json()

    assert report["evaluation"]["is_legacy_report"] is False

    assert report["evidence_summary"]["missing_required_evidence"] == 1

    assert report["evaluation"]["review_required"] is True


# ==================================================
# 21. UNVERIFIED EVIDENCE REQUIRES REVIEW
# ==================================================

def test_report_detects_unverified_evidence(
    client,
    db,
    submission_data,
):
    result = models.SubmissionResult(
        project_id=submission_data["project_id"],
        file_id=submission_data["file_id"],
        requirement_id=submission_data["requirement_ids"][0],
        status="missing",
        feedback="Stored unverified evidence",
        source_page=1,
        source_evidence="Unverified text",
        evidence_verified=False,
        suggested_improvement="Complete the requirement.",
        pipeline_version="2.0.0",
    )

    db.add(result)
    db.commit()

    response = client.get(
        report_url(submission_data)
    )

    assert response.status_code == 200

    report = response.json()

    evidence = report["evidence_summary"]

    assert evidence["verified_evidence"] == 0

    assert evidence["unverified_evidence"] == 1

    assert evidence["evidence_not_available"] == 0

    assert evidence["missing_required_evidence"] == 0

    assert report["evaluation"]["review_required"] is True


# ==================================================
# 22. MIXED PIPELINE VERSIONS
# ==================================================

def test_report_detects_mixed_pipeline_versions(
    client,
    db,
    submission_data,
):
    for index, version in enumerate(
        ["1.0.0", "2.0.0"]
    ):
        result = models.SubmissionResult(
            project_id=submission_data["project_id"],
            file_id=submission_data["file_id"],
            requirement_id=submission_data["requirement_ids"][index],
            status="fulfilled",
            feedback="Completed requirement",
            source_page=1,
            source_evidence="Login is implemented.",
            evidence_verified=True,
            suggested_improvement="",
            pipeline_version=version,
        )

        db.add(result)

    db.commit()

    response = client.get(
        report_url(submission_data)
    )

    assert response.status_code == 200

    report = response.json()

    evaluation = report["evaluation"]

    assert evaluation["pipeline_versions"] == [
        "1.0.0",
        "2.0.0",
    ]

    assert evaluation["legacy_results"] == 0

    assert evaluation["is_legacy_report"] is False

    assert evaluation["review_required"] is True


# ==================================================
# 23. UNKNOWN STATUS
# ==================================================

def test_report_handles_unknown_status(
    client,
    db,
    submission_data,
):
    result = models.SubmissionResult(
        project_id=submission_data["project_id"],
        file_id=submission_data["file_id"],
        requirement_id=submission_data["requirement_ids"][0],
        status="unknown",
        feedback="Unsupported historical status",
        source_page=1,
        source_evidence="Login is implemented.",
        evidence_verified=True,
        suggested_improvement="Review this result.",
        pipeline_version="2.0.0",
    )

    db.add(result)
    db.commit()

    response = client.get(
        report_url(submission_data)
    )

    assert response.status_code == 200

    report = response.json()

    assert report["summary"]["unknown_status_count"] == 1

    assert report["summary"]["total_requirements"] == 1

    assert report["summary"]["completion_percentage"] == 0.0

    assert report["evaluation"]["review_required"] is True
