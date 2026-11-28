import pytest

from copy import deepcopy

from app.requirement_pipeline import (
    process_requirements,
    PIPELINE_VERSION,
)


@pytest.fixture
def pages():
    return [
        {
            "page_number": 1,
            "text": (
                "Implement at least eight automated tests."
            ),
        },
        {
            "page_number": 2,
            "text": (
                "Submit the project by December 13."
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
        "source_page": 1,
        "source_evidence": (
            "Implement at least eight automated tests."
        ),
    }

    requirement.update(changes)

    return requirement


def make_submission_requirement():

    return make_requirement(
        title="Submit project",
        description=(
            "Submit the project by December 13."
        ),
        priority="medium",
        source_page=2,
        source_evidence=(
            "Submit the project by December 13."
        ),
    )


# ==========================================
# SUCCESSFUL PROCESSING
# ==========================================

def test_single_valid_requirement(pages):

    result = process_requirements(
        [make_requirement()],
        pages,
    )

    assert result["status"] == "completed"

    assert result["review_required"] is False

    assert len(result["requirements"]) == 1

    assert (
        result["requirements"][0]["evidence_verified"]
        is True
    )


def test_multiple_valid_requirements(pages):

    result = process_requirements(
        [
            make_requirement(),
            make_submission_requirement(),
        ],
        pages,
    )

    assert result["status"] == "completed"

    assert len(result["requirements"]) == 2

    assert result["statistics"]["validation_rate"] == 100.0

    assert result["statistics"]["retention_rate"] == 100.0


# ==========================================
# INVALID REQUIREMENTS
# ==========================================

def test_invalid_requirement_rejected(pages):

    result = process_requirements(
        [make_requirement(title="")],
        pages,
    )

    assert result["status"] == "failed"

    assert result["review_required"] is True

    assert result["requirements"] == []

    assert result["statistics"]["invalid_count"] == 1


def test_mixed_valid_and_invalid(pages):

    result = process_requirements(
        [
            make_requirement(),
            make_requirement(priority="urgent"),
        ],
        pages,
    )

    assert result["status"] == "review_required"

    assert len(result["requirements"]) == 1

    assert len(result["invalid_requirements"]) == 1

    assert result["statistics"]["validation_rate"] == 50.0


def test_invalid_evidence_rejected(pages):

    result = process_requirements(
        [
            make_requirement(
                source_evidence="Invented evidence.",
                evidence_verified=True,
            )
        ],
        pages,
    )

    assert result["status"] == "failed"

    assert result["requirements"] == []

    assert (
        "Source evidence could not be verified."
        in result["invalid_requirements"][0]["errors"]
    )


def test_wrong_source_page_rejected(pages):

    result = process_requirements(
        [
            make_requirement(
                source_page=2
            )
        ],
        pages,
    )

    assert result["statistics"]["invalid_count"] == 1

    assert result["requirements"] == []


# ==========================================
# DUPLICATE DETECTION
# ==========================================

def test_exact_duplicate_removed(pages):

    first = make_requirement()

    second = make_requirement()

    result = process_requirements(
        [first, second],
        pages,
    )

    assert len(result["requirements"]) == 1

    assert len(result["exact_duplicates"]) == 1

    assert result["status"] == "review_required"

    assert result["statistics"]["retention_rate"] == 50.0


def test_duplicate_information_preserved(pages):

    result = process_requirements(
        [
            make_requirement(),
            make_requirement(),
        ],
        pages,
    )

    duplicate = result["exact_duplicates"][0]

    assert duplicate["original"]["source_page"] == 1

    assert duplicate["duplicate"]["source_page"] == 1

    assert (
        duplicate["duplicate"]["source_evidence"]
        == "Implement at least eight automated tests."
    )


def test_possible_duplicates_preserved(pages):

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

    result = process_requirements(
        [first, second],
        pages,
    )

    assert len(result["requirements"]) == 2

    assert len(result["possible_duplicates"]) == 1

    assert result["exact_duplicates"] == []

    assert result["status"] == "review_required"

    assert result["statistics"]["retention_rate"] == 100.0


def test_validation_before_deduplication(pages):

    valid = make_requirement()

    invalid = make_requirement(
        source_evidence="Invented evidence."
    )

    result = process_requirements(
        [invalid, valid],
        pages,
    )

    assert result["statistics"]["valid_count"] == 1

    assert result["statistics"]["invalid_count"] == 1

    assert result["statistics"]["exact_duplicates_count"] == 0

    assert len(result["requirements"]) == 1

    assert (
        result["requirements"][0]["source_evidence"]
        == valid["source_evidence"]
    )


# ==========================================
# STATISTICS
# ==========================================

def test_statistics_consistency(pages):

    requirements = [
        make_requirement(),
        make_requirement(),
        make_submission_requirement(),
        make_requirement(priority="invalid"),
    ]

    result = process_requirements(
        requirements,
        pages,
    )

    assert result["statistics"] == {
        "original_count": 4,
        "valid_count": 3,
        "invalid_count": 1,
        "unique_count": 2,
        "exact_duplicates_count": 1,
        "possible_duplicates_count": 0,
        "validation_rate": 75.0,
        "retention_rate": 50.0,
    }


def test_priority_statistics(pages):

    result = process_requirements(
        [
            make_requirement(),
            make_submission_requirement(),
        ],
        pages,
    )

    assert result["priority_counts"] == {
        "high": 1,
        "medium": 1,
        "low": 0,
    }


def test_performance_statistics(pages):

    result = process_requirements(
        [make_requirement()],
        pages,
    )

    performance = result["performance"]

    assert performance["validation_seconds"] >= 0

    assert performance["duplicate_detection_seconds"] >= 0

    assert performance["total_seconds"] >= 0


def test_pipeline_version(pages):

    result = process_requirements(
        [make_requirement()],
        pages,
    )

    assert result["pipeline_version"] == PIPELINE_VERSION


# ==========================================
# DATA PRESERVATION
# ==========================================

def test_original_requirements_not_modified(pages):

    requirements = [
        make_requirement(
            title="  Implement automated tests  "
        )
    ]

    original = deepcopy(requirements)

    process_requirements(
        requirements,
        pages,
    )

    assert requirements == original


def test_original_pages_not_modified(pages):

    original = deepcopy(pages)

    process_requirements(
        [make_requirement()],
        pages,
    )

    assert pages == original


def test_original_order_preserved(pages):

    result = process_requirements(
        [
            make_submission_requirement(),
            make_requirement(),
        ],
        pages,
    )

    assert result["requirements"][0]["title"] == "Submit project"

    assert (
        result["requirements"][1]["title"]
        == "Implement automated tests"
    )


# ==========================================
# EDGE CASES
# ==========================================

def test_empty_requirements(pages):

    result = process_requirements(
        [],
        pages,
    )

    assert result["status"] == "empty"

    assert result["review_required"] is False

    assert result["requirements"] == []

    assert result["statistics"]["validation_rate"] is None

    assert result["statistics"]["retention_rate"] is None


def test_invalid_similarity_threshold(pages):

    with pytest.raises(ValueError):

        process_requirements(
            [make_requirement()],
            pages,
            similarity_threshold=1.5,
        )


def test_invalid_pages():

    with pytest.raises(ValueError):

        process_requirements(
            [make_requirement()],
            [],
        )