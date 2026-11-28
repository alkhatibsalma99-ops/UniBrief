import pytest

from app.evidence_validator import (
    validate_source_evidence,
    normalize_text,
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
            "text": "",
        },
        {
            "page_number": 3,
            "text": (
                "The student must implement\n"
                "at least eight automated tests."
            ),
        },
    ]


# ==========================================
# ORIGINAL TESTS
# ==========================================

def test_valid_evidence(pages):
    assert validate_source_evidence(
        pages,
        3,
        "at least eight automated tests.",
    ) is True


def test_wrong_page(pages):
    assert validate_source_evidence(
        pages,
        1,
        "at least eight automated tests.",
    ) is False


def test_invented_evidence(pages):
    assert validate_source_evidence(
        pages,
        3,
        "Implement twenty automated tests.",
    ) is False


def test_empty_evidence(pages):
    assert validate_source_evidence(
        pages,
        3,
        "   ",
    ) is False


def test_invalid_page_number(pages):
    assert validate_source_evidence(
        pages,
        99,
        "University assignment",
    ) is False


def test_empty_page(pages):
    assert validate_source_evidence(
        pages,
        2,
        "Some requirement",
    ) is False


def test_whitespace_normalization(pages):
    assert validate_source_evidence(
        pages,
        3,
        "The student must implement "
        "at least eight automated tests.",
    ) is True


def test_invalid_page_type(pages):
    assert validate_source_evidence(
        pages,
        "3",
        "automated tests.",
    ) is False


def test_zero_page_number(pages):
    assert validate_source_evidence(
        pages,
        0,
        "University assignment",
    ) is False


def test_invalid_evidence_type(pages):
    assert validate_source_evidence(
        pages,
        3,
        None,
    ) is False


def test_unicode_normalization():
    assert normalize_text("ﬁle") == "file"


def test_boolean_page_number(pages):
    assert validate_source_evidence(
        pages,
        True,
        "University assignment",
    ) is False


# ==========================================
# HYPHENATION REGRESSION TESTS
# ==========================================

def test_split_simulation_word():
    pages = [
        {
            "page_number": 6,
            "text": "Run a sim-\nulation.",
        }
    ]

    assert validate_source_evidence(
        pages,
        6,
        "Run a simulation.",
    ) is True


def test_split_opencode_word():
    pages = [
        {
            "page_number": 7,
            "text": "Use Open-\nCode:opencode run",
        }
    ]

    assert validate_source_evidence(
        pages,
        7,
        "Use Open-Code:opencode run",
    ) is True


def test_split_permission_word():
    pages = [
        {
            "page_number": 7,
            "text": "Implement a permis-\nsion rule.",
        }
    ]

    assert validate_source_evidence(
        pages,
        7,
        "Implement a permission rule.",
    ) is True


def test_changed_numbers_are_rejected():
    pages = [
        {
            "page_number": 1,
            "text": "Implement at least eight tests.",
        }
    ]

    assert validate_source_evidence(
        pages,
        1,
        "Implement at least ten tests.",
    ) is False


def test_regular_hyphen_is_preserved():
    pages = [
        {
            "page_number": 1,
            "text": "Implement domain-specific tools.",
        }
    ]

    assert validate_source_evidence(
        pages,
        1,
        "Implement domainspecific tools.",
    ) is False


def test_hyphenation_does_not_accept_wrong_page():
    pages = [
        {
            "page_number": 6,
            "text": "Run a sim-\nulation.",
        }
    ]

    assert validate_source_evidence(
        pages,
        7,
        "Run a simulation.",
    ) is False