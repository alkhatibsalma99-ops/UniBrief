from time import perf_counter

from app.requirement_validator import (
    validate_requirements,
)

from app.requirement_deduplicator import (
    deduplicate_requirements,
)


DEFAULT_SIMILARITY_THRESHOLD = 0.85

PIPELINE_VERSION = "1.0.0"


def process_requirements(
    requirements: list[dict],
    pages: list[dict],
    similarity_threshold: float = (
        DEFAULT_SIMILARITY_THRESHOLD
    ),
) -> dict:

    start = perf_counter()

    # ======================================
    # STEP 1: OUTPUT AND EVIDENCE VALIDATION
    # ======================================

    validation_start = perf_counter()

    validation_result = validate_requirements(
        requirements=requirements,
        pages=pages,
    )

    validation_runtime = round(
        perf_counter() - validation_start,
        4,
    )

    valid_requirements = (
        validation_result["requirements"]
    )

    invalid_requirements = (
        validation_result["invalid_requirements"]
    )

    # ======================================
    # STEP 2: DUPLICATE DETECTION
    # ======================================

    duplicate_start = perf_counter()

    duplicate_result = deduplicate_requirements(
        requirements=valid_requirements,
        similarity_threshold=similarity_threshold,
    )

    duplicate_runtime = round(
        perf_counter() - duplicate_start,
        4,
    )

    unique_requirements = (
        duplicate_result["requirements"]
    )

    exact_duplicates = (
        duplicate_result["exact_duplicates"]
    )

    possible_duplicates = (
        duplicate_result["possible_duplicates"]
    )

    # ======================================
    # STEP 3: QUALITY STATISTICS
    # ======================================

    original_count = len(requirements)

    valid_count = len(valid_requirements)

    invalid_count = len(invalid_requirements)

    unique_count = len(unique_requirements)

    exact_duplicates_count = len(
        exact_duplicates
    )

    possible_duplicates_count = len(
        possible_duplicates
    )

    validation_rate = (
        round(
            valid_count / original_count * 100,
            2,
        )
        if original_count
        else None
    )

    retention_rate = (
        round(
            unique_count / original_count * 100,
            2,
        )
        if original_count
        else None
    )

    # ======================================
    # STEP 4: CONSISTENCY CHECKS
    # ======================================

    if original_count != (
        valid_count + invalid_count
    ):

        raise RuntimeError(
            "Validation count mismatch."
        )

    if valid_count != (
        unique_count + exact_duplicates_count
    ):

        raise RuntimeError(
            "Duplicate count mismatch."
        )

    # ======================================
    # STEP 5: REVIEW STATUS
    # ======================================

    review_required = (
        invalid_count > 0
        or exact_duplicates_count > 0
        or possible_duplicates_count > 0
    )

    if original_count == 0:

        status = "empty"

    elif unique_count == 0:

        status = "failed"

    elif review_required:

        status = "review_required"

    else:

        status = "completed"

    # ======================================
    # STEP 6: PRIORITY STATISTICS
    # ======================================

    priority_counts = {
        "high": 0,
        "medium": 0,
        "low": 0,
    }

    for requirement in unique_requirements:

        priority_counts[
            requirement["priority"]
        ] += 1

    # ======================================
    # STEP 7: FINAL RESULT
    # ======================================

    total_runtime = round(
        perf_counter() - start,
        4,
    )

    return {
        "pipeline_version": PIPELINE_VERSION,

        "status": status,

        "review_required": review_required,

        "similarity_threshold": (
            similarity_threshold
        ),

        "requirements": unique_requirements,

        "invalid_requirements": (
            invalid_requirements
        ),

        "exact_duplicates": exact_duplicates,

        "possible_duplicates": (
            possible_duplicates
        ),

        "priority_counts": priority_counts,

        "statistics": {
            "original_count": original_count,

            "valid_count": valid_count,

            "invalid_count": invalid_count,

            "unique_count": unique_count,

            "exact_duplicates_count": (
                exact_duplicates_count
            ),

            "possible_duplicates_count": (
                possible_duplicates_count
            ),

            "validation_rate": validation_rate,

            "retention_rate": retention_rate,
        },

        "performance": {
            "validation_seconds": (
                validation_runtime
            ),

            "duplicate_detection_seconds": (
                duplicate_runtime
            ),

            "total_seconds": total_runtime,
        },
    }