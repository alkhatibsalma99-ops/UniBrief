import pytest

from app.requirement_validator import (
    validate_requirement,
    validate_requirements,
)


@pytest.fixture
def pages():
    return [
        {
            "page_number": 1,
            "text": "University assignment",
        },
        {
            "page_number": 2,
            "text": (
                "Implement at least eight automated tests."
            ),
        },
        {
            "page_number": 3,
            "text": "Submit the project by December 13.",
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
    }

    requirement.update(changes)

    return requirement


# ==========================================
# VALID REQUIREMENTS
# ==========================================

def test_valid_requirement(pages):

    errors = validate_requirement(
        make_requirement(),
        pages,
    )

    assert errors == []


def test_valid_priorities(pages):

    for priority in ["high", "medium", "low"]:

        errors = validate_requirement(
            make_requirement(priority=priority),
            pages,
        )

        assert errors == []


def test_valid_length_boundaries(pages):

    errors = validate_requirement(
        make_requirement(
            title="A" * 255,
            description="B" * 2000,
        ),
        pages,
    )

    assert errors == []


# ==========================================
# TITLE VALIDATION
# ==========================================

def test_empty_title(pages):

    errors = validate_requirement(
        make_requirement(title="   "),
        pages,
    )

    assert "Title must not be empty." in errors


def test_title_too_long(pages):

    errors = validate_requirement(
        make_requirement(title="A" * 256),
        pages,
    )

    assert "Title exceeds 255 characters." in errors


def test_invalid_title_type(pages):

    errors = validate_requirement(
        make_requirement(title=123),
        pages,
    )

    assert "Title must be a string." in errors


# ==========================================
# DESCRIPTION VALIDATION
# ==========================================

def test_empty_description(pages):

    errors = validate_requirement(
        make_requirement(description=""),
        pages,
    )

    assert "Description must not be empty." in errors


def test_description_too_long(pages):

    errors = validate_requirement(
        make_requirement(description="A" * 2001),
        pages,
    )

    assert (
        "Description exceeds 2000 characters."
        in errors
    )


def test_invalid_description_type(pages):

    errors = validate_requirement(
        make_requirement(description=None),
        pages,
    )

    assert "Description must be a string." in errors


# ==========================================
# PRIORITY VALIDATION
# ==========================================

def test_invalid_priority(pages):

    errors = validate_requirement(
        make_requirement(priority="urgent"),
        pages,
    )

    assert "Invalid requirement priority." in errors


def test_invalid_priority_type(pages):

    errors = validate_requirement(
        make_requirement(priority=["high"]),
        pages,
    )

    assert "Invalid requirement priority." in errors


# ==========================================
# SOURCE PAGE VALIDATION
# ==========================================

def test_invalid_source_page_type(pages):

    errors = validate_requirement(
        make_requirement(source_page="2"),
        pages,
    )

    assert "Source page must be an integer." in errors


def test_boolean_source_page(pages):

    errors = validate_requirement(
        make_requirement(source_page=True),
        pages,
    )

    assert "Source page must be an integer." in errors


def test_zero_source_page(pages):

    errors = validate_requirement(
        make_requirement(source_page=0),
        pages,
    )

    assert "Source page must be positive." in errors


def test_nonexistent_source_page(pages):

    errors = validate_requirement(
        make_requirement(source_page=99),
        pages,
    )

    assert "Source page does not exist." in errors


def test_wrong_source_page(pages):

    errors = validate_requirement(
        make_requirement(source_page=1),
        pages,
    )

    assert (
        "Source evidence could not be verified."
        in errors
    )


# ==========================================
# SOURCE EVIDENCE VALIDATION
# ==========================================

def test_empty_source_evidence(pages):

    errors = validate_requirement(
        make_requirement(source_evidence="   "),
        pages,
    )

    assert (
        "Source evidence must not be empty."
        in errors
    )


def test_invalid_source_evidence_type(pages):

    errors = validate_requirement(
        make_requirement(source_evidence=None),
        pages,
    )

    assert (
        "Source evidence must be a string."
        in errors
    )


def test_invented_source_evidence(pages):

    errors = validate_requirement(
        make_requirement(
            source_evidence="Implement twenty tests."
        ),
        pages,
    )

    assert (
        "Source evidence could not be verified."
        in errors
    )


def test_false_verification_flag_not_trusted(pages):

    requirement = make_requirement(
        source_evidence="Invented evidence.",
        evidence_verified=True,
    )

    result = validate_requirements(
        [requirement],
        pages,
    )

    assert result["statistics"]["invalid"] == 1
    assert result["requirements"] == []


# ==========================================
# DATA SAFETY
# ==========================================

def test_missing_required_field(pages):

    requirement = make_requirement()

    del requirement["title"]

    errors = validate_requirement(
        requirement,
        pages,
    )

    assert "Missing field: title" in errors


def test_invalid_requirement_object(pages):

    errors = validate_requirement(
        "Invalid requirement",
        pages,
    )

    assert errors == [
        "Requirement must be an object."
    ]


def test_null_characters(pages):

    requirement = make_requirement(
        title="Invalid\x00title",
        description="Invalid\x00description",
        source_evidence="Invalid\x00evidence",
    )

    errors = validate_requirement(
        requirement,
        pages,
    )

    assert "title contains a null character." in errors

    assert (
        "description contains a null character."
        in errors
    )

    assert (
        "source_evidence contains a null character."
        in errors
    )


# ==========================================
# BATCH VALIDATION
# ==========================================

def test_mixed_requirements(pages):

    valid = make_requirement()

    invalid = make_requirement(
        priority="urgent"
    )

    result = validate_requirements(
        [valid, invalid],
        pages,
    )

    assert len(result["requirements"]) == 1

    assert len(
        result["invalid_requirements"]
    ) == 1

    assert result["statistics"] == {
        "total": 2,
        "valid": 1,
        "invalid": 1,
        "validation_rate": 50.0,
    }


def test_invalid_requirement_preserved(pages):

    invalid = make_requirement(
        title=""
    )

    result = validate_requirements(
        [invalid],
        pages,
    )

    rejected = result["invalid_requirements"][0]

    assert rejected["index"] == 1

    assert rejected["requirement"] == invalid

    assert (
        "Title must not be empty."
        in rejected["errors"]
    )


def test_whitespace_removed(pages):

    requirement = make_requirement(
        title="  Implement tests  ",
        description="  Implement eight tests.  ",
    )

    result = validate_requirements(
        [requirement],
        pages,
    )

    validated = result["requirements"][0]

    assert validated["title"] == "Implement tests"

    assert (
        validated["description"]
        == "Implement eight tests."
    )

    assert validated["evidence_verified"] is True


def test_original_requirement_not_modified(pages):

    requirement = make_requirement(
        title="  Implement tests  "
    )

    original = requirement.copy()

    validate_requirements(
        [requirement],
        pages,
    )

    assert requirement == original


def test_empty_requirements(pages):

    result = validate_requirements(
        [],
        pages,
    )

    assert result["statistics"] == {
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "validation_rate": None,
    }


def test_all_requirements_invalid(pages):

    result = validate_requirements(
        [
            make_requirement(title=""),
            make_requirement(priority="urgent"),
        ],
        pages,
    )

    assert result["statistics"] == {
        "total": 2,
        "valid": 0,
        "invalid": 2,
        "validation_rate": 0.0,
    }


# ==========================================
# INVALID INPUT
# ==========================================

def test_invalid_requirements_list(pages):

    with pytest.raises(ValueError):

        validate_requirements(
            "invalid",
            pages,
        )


def test_empty_pages():

    with pytest.raises(ValueError):

        validate_requirements(
            [],
            [],
        )


def test_duplicate_page_numbers():

    invalid_pages = [
        {
            "page_number": 1,
            "text": "First page",
        },
        {
            "page_number": 1,
            "text": "Duplicate page",
        },
    ]

    with pytest.raises(ValueError):

        validate_requirements(
            [],
            invalid_pages,
        )


def test_invalid_page_text():

    invalid_pages = [
        {
            "page_number": 1,
            "text": None,
        }
    ]

    with pytest.raises(ValueError):

        validate_requirements(
            [],
            invalid_pages,
        )