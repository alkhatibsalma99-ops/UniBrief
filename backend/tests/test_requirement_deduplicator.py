import pytest

from app.requirement_deduplicator import (
    normalize_requirement_text,
    calculate_similarity,
    deduplicate_requirements,
)


def make_requirement(
    title="Implement automated tests",
    description="Implement at least eight automated tests.",
    priority="high",
    source_page=1,
    source_evidence="Implement at least eight automated tests.",
):
    return {
        "title": title,
        "description": description,
        "priority": priority,
        "source_page": source_page,
        "source_evidence": source_evidence,
        "evidence_verified": True,
    }


# ==========================================
# NORMALIZATION
# ==========================================

def test_whitespace_normalization():
    assert normalize_requirement_text(
        "  Implement   automated\n tests.  "
    ) == "Implement automated tests."


def test_unicode_normalization():
    assert normalize_requirement_text(
        "Cafe\u0301"
    ) == "Café"


# ==========================================
# EXACT DUPLICATES
# ==========================================

def test_exact_duplicate_removed():
    first = make_requirement()
    second = make_requirement()

    result = deduplicate_requirements(
        [first, second]
    )

    assert len(result["requirements"]) == 1
    assert len(result["exact_duplicates"]) == 1


def test_whitespace_duplicate_removed():
    first = make_requirement()

    second = make_requirement(
        title="Implement   automated tests",
        description=(
            "Implement at least eight\n"
            "automated tests."
        ),
    )

    result = deduplicate_requirements(
        [first, second]
    )

    assert len(result["requirements"]) == 1


def test_duplicate_evidence_preserved():
    first = make_requirement(
        source_page=1
    )

    second = make_requirement(
        source_page=5
    )

    result = deduplicate_requirements(
        [first, second]
    )

    duplicate = result["exact_duplicates"][0]

    assert duplicate["original"]["source_page"] == 1
    assert duplicate["duplicate"]["source_page"] == 5


# ==========================================
# PROTECT IMPORTANT REQUIREMENTS
# ==========================================

def test_different_numbers_not_removed():
    first = make_requirement(
        description="Implement at least eight tests."
    )

    second = make_requirement(
        description="Implement at least ten tests."
    )

    result = deduplicate_requirements(
        [first, second]
    )

    assert len(result["requirements"]) == 2


def test_different_deadlines_not_removed():
    first = make_requirement(
        title="Submit project",
        description="Submit by December 13, 2026.",
    )

    second = make_requirement(
        title="Submit project",
        description="Submit by December 20, 2026.",
    )

    result = deduplicate_requirements(
        [first, second]
    )

    assert len(result["requirements"]) == 2


def test_negation_not_removed():
    first = make_requirement(
        description="Use external APIs."
    )

    second = make_requirement(
        description="Do not use external APIs."
    )

    result = deduplicate_requirements(
        [first, second]
    )

    assert len(result["requirements"]) == 2


def test_different_priorities_not_removed():
    first = make_requirement(
        priority="high"
    )

    second = make_requirement(
        priority="medium"
    )

    result = deduplicate_requirements(
        [first, second]
    )

    assert len(result["requirements"]) == 2


def test_different_conditions_not_removed():
    first = make_requirement(
        description="Use Docker if available."
    )

    second = make_requirement(
        description="Use Docker in all cases."
    )

    result = deduplicate_requirements(
        [first, second]
    )

    assert len(result["requirements"]) == 2


# ==========================================
# POSSIBLE DUPLICATES
# ==========================================

def test_similar_requirements_flagged():
    first = make_requirement(
        description="Implement at least eight automated tests."
    )

    second = make_requirement(
        description="Implement at least nine automated tests."
    )

    result = deduplicate_requirements(
        [first, second]
    )

    assert len(result["requirements"]) == 2

    assert len(
        result["possible_duplicates"]
    ) == 1


def test_unrelated_requirements_not_flagged():
    first = make_requirement()

    second = make_requirement(
        title="Submit presentation",
        description="Upload slides to Moodle.",
    )

    result = deduplicate_requirements(
        [first, second]
    )

    assert len(result["requirements"]) == 2

    assert len(
        result["possible_duplicates"]
    ) == 0


def test_identical_similarity():
    first = make_requirement()
    second = make_requirement()

    assert calculate_similarity(
        first,
        second,
    ) == 1.0


# ==========================================
# STATISTICS AND EDGE CASES
# ==========================================

def test_empty_requirements():
    result = deduplicate_requirements([])

    assert result["requirements"] == []

    assert result["statistics"] == {
        "original_count": 0,
        "unique_count": 0,
        "exact_duplicates_count": 0,
        "possible_duplicates_count": 0,
    }


def test_single_requirement():
    result = deduplicate_requirements(
        [make_requirement()]
    )

    assert len(result["requirements"]) == 1
    assert result["exact_duplicates"] == []
    assert result["possible_duplicates"] == []


def test_statistics():
    first = make_requirement()
    second = make_requirement()

    third = make_requirement(
        title="Submit presentation",
        description="Upload slides to Moodle.",
    )

    result = deduplicate_requirements(
        [first, second, third]
    )

    assert result["statistics"] == {
        "original_count": 3,
        "unique_count": 2,
        "exact_duplicates_count": 1,
        "possible_duplicates_count": 0,
    }


def test_invalid_threshold():
    with pytest.raises(ValueError):
        deduplicate_requirements(
            [],
            similarity_threshold=1.5,
        )


def test_original_order_preserved():
    first = make_requirement()

    second = make_requirement(
        title="Submit presentation",
        description="Upload slides to Moodle.",
    )

    third = make_requirement()

    result = deduplicate_requirements(
        [first, second, third]
    )

    assert result["requirements"] == [
        first,
        second,
    ]