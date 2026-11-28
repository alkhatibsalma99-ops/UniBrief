
import pytest

from app.submission_validator import (
    validate_submission_results,
)


# ==========================================
# TEST DATA
# ==========================================

@pytest.fixture
def pages():
    return [
        {
            "page_number": 1,
            "text": (
                "The application implements user "
                "authentication with JWT tokens."
            ),
        },
        {
            "page_number": 2,
            "text": (
                "The database contains users and projects. "
                "Database relationships are not documented."
            ),
        },
        {
            "page_number": 3,
            "text": (
                "The frontend is implemented using Flutter."
            ),
        },
    ]


@pytest.fixture
def requirements():
    return [
        {
            "id": 1,
            "title": "User authentication",
            "description": "Implement authentication.",
            "priority": "high",
        },
        {
            "id": 2,
            "title": "Database documentation",
            "description": "Document database relationships.",
            "priority": "medium",
        },
        {
            "id": 3,
            "title": "Unit tests",
            "description": "Implement automated tests.",
            "priority": "high",
        },
    ]


@pytest.fixture
def valid_results():
    return [
        {
            "requirement_id": 1,
            "status": "fulfilled",
            "feedback": "JWT authentication is documented.",
            "source_page": 1,
            "source_evidence": (
                "The application implements user "
                "authentication with JWT tokens."
            ),
            "suggested_improvement": "",
        },
        {
            "requirement_id": 2,
            "status": "partially_fulfilled",
            "feedback": (
                "The database exists, but relationships "
                "are not documented."
            ),
            "source_page": 2,
            "source_evidence": (
                "The database contains users and projects."
            ),
            "suggested_improvement": (
                "Add an ER diagram and explain relationships."
            ),
        },
        {
            "requirement_id": 3,
            "status": "missing",
            "feedback": "No automated tests were found.",
            "source_page": None,
            "source_evidence": None,
            "suggested_improvement": (
                "Implement and document unit tests."
            ),
        },
    ]


# ==========================================
# HELPER
# ==========================================

def validate(results, requirements, pages):
    return validate_submission_results(
        results=results,
        requirements=requirements,
        pages=pages,
    )


def assert_rejected(report):
    assert report["can_persist"] is False
    assert report["status"] == "failed"
    assert report["review_required"] is True

    assert (
        report["statistics"]["completion_percentage"]
        is None
    )


# ==========================================
# VALID RESULTS
# ==========================================

def test_valid_complete_response(
    valid_results, requirements, pages
):
    report = validate(
        valid_results, requirements, pages
    )

    assert report["can_persist"] is True
    assert report["status"] == "completed"
    assert report["review_required"] is False

    assert len(report["results"]) == 3
    assert report["invalid_results"] == []

    assert report["statistics"]["expected"] == 3
    assert report["statistics"]["valid"] == 3
    assert report["statistics"]["invalid"] == 0

    assert (
        report["statistics"]["validation_rate"]
        == 100.0
    )

    assert (
        report["statistics"]["coverage_rate"]
        == 100.0
    )


def test_status_counts(
    valid_results, requirements, pages
):
    report = validate(
        valid_results, requirements, pages
    )

    assert report["status_counts"] == {
        "fulfilled": 1,
        "partially_fulfilled": 1,
        "missing": 1,
        "unclear": 0,
    }


def test_completion_percentage(
    valid_results, requirements, pages
):
    report = validate(
        valid_results, requirements, pages
    )

    assert (
        report["statistics"]["completion_percentage"]
        == 33.33
    )


def test_verified_evidence(
    valid_results, requirements, pages
):
    report = validate(
        valid_results, requirements, pages
    )

    assert (
        report["results"][0]["evidence_verified"]
        is True
    )

    assert (
        report["results"][1]["evidence_verified"]
        is True
    )

    assert (
        report["results"][2]["evidence_verified"]
        is None
    )

    assert (
        report["statistics"]["verified_evidence"]
        == 2
    )


def test_pipeline_version(
    valid_results, requirements, pages
):
    report = validate(
        valid_results, requirements, pages
    )

    assert report["pipeline_version"] == "2.0.0"

    for result in report["results"]:
        assert result["pipeline_version"] == "2.0.0"


# ==========================================
# REQUIREMENT ID VALIDATION
# ==========================================

def test_duplicate_requirement_id(
    valid_results, requirements, pages
):
    valid_results.append(
        valid_results[0].copy()
    )

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)

    assert (
        report["duplicate_requirement_ids"]
        == [1]
    )


def test_missing_requirement_id(
    valid_results, requirements, pages
):
    valid_results.pop()

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)

    assert (
        report["missing_requirement_ids"]
        == [3]
    )


def test_unknown_requirement_id(
    valid_results, requirements, pages
):
    valid_results[0]["requirement_id"] = 999

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)

    assert (
        report["unknown_requirement_ids"]
        == [999]
    )

    assert (
        report["missing_requirement_ids"]
        == [1]
    )


@pytest.mark.parametrize(
    "invalid_id",
    [True, False, "1", 1.0, None, 0, -1],
)
def test_invalid_requirement_id_type(
    invalid_id,
    valid_results,
    requirements,
    pages,
):
    valid_results[0]["requirement_id"] = invalid_id

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


# ==========================================
# STATUS VALIDATION
# ==========================================

@pytest.mark.parametrize(
    "invalid_status",
    ["completed", "success", "", None, True, []],
)
def test_invalid_status(
    invalid_status,
    valid_results,
    requirements,
    pages,
):
    valid_results[0]["status"] = invalid_status

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_unclear_requires_review(
    valid_results, requirements, pages
):
    valid_results[2]["status"] = "unclear"

    report = validate(
        valid_results, requirements, pages
    )

    assert report["can_persist"] is True
    assert report["review_required"] is True

    assert (
        report["status_counts"]["unclear"] == 1
    )


# ==========================================
# EVIDENCE VALIDATION
# ==========================================

def test_invented_evidence(
    valid_results, requirements, pages
):
    valid_results[0]["source_evidence"] = (
        "The application uses biometric authentication."
    )

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)

    assert (
        "Source evidence could not be verified."
        in report["invalid_results"][0]["errors"]
    )


def test_wrong_evidence_page(
    valid_results, requirements, pages
):
    valid_results[0]["source_page"] = 2

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_nonexistent_page(
    valid_results, requirements, pages
):
    valid_results[0]["source_page"] = 999

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)

    assert (
        "Source page does not exist."
        in report["invalid_results"][0]["errors"]
    )


@pytest.mark.parametrize(
    "invalid_page",
    [True, False, 0, -1, "1", 1.0],
)
def test_invalid_page_number(
    invalid_page,
    valid_results,
    requirements,
    pages,
):
    valid_results[0]["source_page"] = invalid_page

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


@pytest.mark.parametrize(
    "index",
    [0, 1],
)
def test_required_evidence_missing(
    index,
    valid_results,
    requirements,
    pages,
):
    valid_results[index]["source_page"] = None
    valid_results[index]["source_evidence"] = None

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_evidence_without_page(
    valid_results, requirements, pages
):
    valid_results[0]["source_page"] = None

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_page_without_evidence(
    valid_results, requirements, pages
):
    valid_results[0]["source_evidence"] = None

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_missing_status_without_evidence(
    valid_results, requirements, pages
):
    report = validate(
        valid_results, requirements, pages
    )

    assert report["can_persist"] is True

    missing = report["results"][2]

    assert missing["status"] == "missing"
    assert missing["source_page"] is None
    assert missing["source_evidence"] is None
    assert missing["evidence_verified"] is None


def test_fake_verification_flag_is_ignored(
    valid_results, requirements, pages
):
    valid_results[2]["evidence_verified"] = True
    valid_results[0]["evidence_verified"] = False

    report = validate(
        valid_results, requirements, pages
    )

    assert report["can_persist"] is True

    assert (
        report["results"][2]["evidence_verified"]
        is None
    )

    assert (
        report["results"][0]["evidence_verified"]
        is True
    )


def test_fake_flag_cannot_validate_invented_evidence(
    valid_results, requirements, pages
):
    valid_results[0]["source_evidence"] = (
        "Invented evidence."
    )

    valid_results[0]["evidence_verified"] = True

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_pdf_line_break_normalization(
    valid_results, requirements, pages
):
    pages[0]["text"] = (
        "The application implements user "
        "authenti-\ncation with JWT tokens."
    )

    report = validate(
        valid_results, requirements, pages
    )

    assert report["can_persist"] is True

    assert (
        report["results"][0]["evidence_verified"]
        is True
    )


# ==========================================
# TEXT VALIDATION
# ==========================================

@pytest.mark.parametrize(
    "invalid_feedback",
    ["", "   ", None, 123, "x" * 2001],
)
def test_invalid_feedback(
    invalid_feedback,
    valid_results,
    requirements,
    pages,
):
    valid_results[0]["feedback"] = invalid_feedback

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


@pytest.mark.parametrize(
    "invalid_evidence",
    ["", "   ", 123, "x" * 4001],
)
def test_invalid_evidence_text(
    invalid_evidence,
    valid_results,
    requirements,
    pages,
):
    valid_results[0]["source_evidence"] = (
        invalid_evidence
    )

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_feedback_length_boundary(
    valid_results, requirements, pages
):
    valid_results[0]["feedback"] = "x" * 2000

    report = validate(
        valid_results, requirements, pages
    )

    assert report["can_persist"] is True


@pytest.mark.parametrize(
    "index",
    [1, 2],
)
def test_improvement_required(
    index,
    valid_results,
    requirements,
    pages,
):
    valid_results[index]["suggested_improvement"] = ""

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_improvement_required_for_unclear(
    valid_results, requirements, pages
):
    valid_results[2]["status"] = "unclear"
    valid_results[2]["suggested_improvement"] = ""

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_improvement_too_long(
    valid_results, requirements, pages
):
    valid_results[1]["suggested_improvement"] = (
        "x" * 2001
    )

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


@pytest.mark.parametrize(
    "field",
    [
        "feedback",
        "source_evidence",
        "suggested_improvement",
    ],
)
def test_null_character_rejected(
    field,
    valid_results,
    requirements,
    pages,
):
    valid_results[0][field] = "Invalid\x00text"

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_whitespace_is_trimmed(
    valid_results, requirements, pages
):
    valid_results[0]["feedback"] = (
        "  Authentication implemented.  "
    )

    report = validate(
        valid_results, requirements, pages
    )

    assert report["can_persist"] is True

    assert (
        report["results"][0]["feedback"]
        == "Authentication implemented."
    )


# ==========================================
# RESPONSE STRUCTURE
# ==========================================

@pytest.mark.parametrize(
    "field",
    [
        "requirement_id",
        "status",
        "feedback",
        "source_page",
        "source_evidence",
        "suggested_improvement",
    ],
)
def test_missing_required_field(
    field,
    valid_results,
    requirements,
    pages,
):
    del valid_results[0][field]

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_empty_ai_response(
    requirements, pages
):
    report = validate(
        [], requirements, pages
    )

    assert_rejected(report)

    assert (
        report["missing_requirement_ids"]
        == [1, 2, 3]
    )

    assert (
        report["statistics"]["coverage_rate"]
        == 0.0
    )


def test_invalid_result_object(
    valid_results, requirements, pages
):
    valid_results[0] = "Invalid result"

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)


def test_invalid_results_container(
    requirements, pages
):
    with pytest.raises(ValueError):
        validate(
            {"results": []},
            requirements,
            pages,
        )


def test_extra_fields_are_removed(
    valid_results, requirements, pages
):
    valid_results[0]["unexpected_field"] = (
        "Untrusted value"
    )

    report = validate(
        valid_results, requirements, pages
    )

    assert report["can_persist"] is True

    assert (
        "unexpected_field"
        not in report["results"][0]
    )


# ==========================================
# INPUT VALIDATION
# ==========================================

def test_empty_requirements(
    valid_results, pages
):
    with pytest.raises(ValueError):
        validate(valid_results, [], pages)


def test_duplicate_expected_requirements(
    valid_results, requirements, pages
):
    requirements.append(
        requirements[0].copy()
    )

    with pytest.raises(ValueError):
        validate(
            valid_results, requirements, pages
        )


def test_invalid_expected_requirement_id(
    valid_results, requirements, pages
):
    requirements[0]["id"] = True

    with pytest.raises(ValueError):
        validate(
            valid_results, requirements, pages
        )


def test_empty_pages(
    valid_results, requirements
):
    with pytest.raises(ValueError):
        validate(
            valid_results, requirements, []
        )


def test_pdf_without_text(
    valid_results, requirements
):
    pages = [
        {
            "page_number": 1,
            "text": "   ",
        },
    ]

    with pytest.raises(ValueError):
        validate(
            valid_results, requirements, pages
        )


def test_duplicate_pdf_pages(
    valid_results, requirements, pages
):
    pages.append(
        pages[0].copy()
    )

    with pytest.raises(ValueError):
        validate(
            valid_results, requirements, pages
        )


def test_invalid_pdf_page_text(
    valid_results, requirements, pages
):
    pages[0]["text"] = None

    with pytest.raises(ValueError):
        validate(
            valid_results, requirements, pages
        )


# ==========================================
# DATA INTEGRITY
# ==========================================

def test_original_data_is_not_modified(
    valid_results, requirements, pages
):
    from copy import deepcopy

    original_results = deepcopy(valid_results)
    original_requirements = deepcopy(requirements)
    original_pages = deepcopy(pages)

    validate(
        valid_results, requirements, pages
    )

    assert valid_results == original_results
    assert requirements == original_requirements
    assert pages == original_pages


def test_invalid_response_cannot_persist(
    valid_results, requirements, pages
):
    valid_results[1]["source_evidence"] = (
        "Evidence that does not exist."
    )

    report = validate(
        valid_results, requirements, pages
    )

    assert_rejected(report)

    assert report["statistics"]["valid"] == 2
    assert report["statistics"]["invalid"] == 1

    assert (
        report["unvalidated_requirement_ids"]
        == [2]
    )


def test_result_order_does_not_affect_validation(
    valid_results, requirements, pages
):
    valid_results.reverse()

    report = validate(
        valid_results, requirements, pages
    )

    assert report["can_persist"] is True

    assert (
        report["statistics"]["coverage_rate"]
        == 100.0
    )


def test_all_requirements_fulfilled(
    requirements, pages
):
    results = []

    for requirement in requirements:
        results.append({
            "requirement_id": requirement["id"],
            "status": "fulfilled",
            "feedback": "Simulated fulfilled result.",
            "source_page": 1,
            "source_evidence": (
                "The application implements user "
                "authentication with JWT tokens."
            ),
            "suggested_improvement": "",
        })

    report = validate(
        results, requirements, pages
    )

    assert report["can_persist"] is True

    assert (
        report["statistics"]["completion_percentage"]
        == 100.0
    )


def test_all_requirements_missing(
    requirements, pages
):
    results = []

    for requirement in requirements:
        results.append({
            "requirement_id": requirement["id"],
            "status": "missing",
            "feedback": "Requirement not found.",
            "source_page": None,
            "source_evidence": None,
            "suggested_improvement": (
                "Implement the requirement."
            ),
        })

    report = validate(
        results, requirements, pages
    )

    assert report["can_persist"] is True

    assert (
        report["statistics"]["completion_percentage"]
        == 0.0
    )
