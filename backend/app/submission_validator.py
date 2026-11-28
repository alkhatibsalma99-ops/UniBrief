
from app.evidence_validator import (
    validate_source_evidence,
)


SUBMISSION_VALIDATOR_VERSION = "2.0.0"

MAX_FEEDBACK_LENGTH = 2000
MAX_IMPROVEMENT_LENGTH = 2000
MAX_EVIDENCE_LENGTH = 4000

VALID_STATUSES = {
    "fulfilled",
    "partially_fulfilled",
    "missing",
    "unclear",
}

EVIDENCE_REQUIRED_STATUSES = {
    "fulfilled",
    "partially_fulfilled",
}

REQUIRED_FIELDS = {
    "requirement_id",
    "status",
    "feedback",
    "source_page",
    "source_evidence",
    "suggested_improvement",
}


# ==========================================
# VALIDATE PDF PAGES
# ==========================================

def validate_submission_pages(
    pages: list[dict],
) -> set[int]:

    if not isinstance(pages, list) or not pages:
        raise ValueError(
            "Valid submission PDF pages are required."
        )

    page_numbers = set()
    has_text = False

    for page in pages:

        if not isinstance(page, dict):
            raise ValueError(
                "Invalid page object."
            )

        number = page.get("page_number")
        text = page.get("text")

        if type(number) is not int or number < 1:
            raise ValueError(
                "Invalid page number."
            )

        if number in page_numbers:
            raise ValueError(
                "Duplicate page number."
            )

        if not isinstance(text, str):
            raise ValueError(
                "Invalid page text."
            )

        if text.strip():
            has_text = True

        page_numbers.add(number)

    if not has_text:
        raise ValueError(
            "Submission PDF contains no text."
        )

    return page_numbers


# ==========================================
# VALIDATE EXPECTED REQUIREMENTS
# ==========================================

def get_expected_requirement_ids(
    requirements: list[dict],
) -> set[int]:

    if (
        not isinstance(requirements, list)
        or not requirements
    ):
        raise ValueError(
            "Valid requirements are required."
        )

    expected_ids = set()

    for requirement in requirements:

        if not isinstance(requirement, dict):
            raise ValueError(
                "Invalid requirement object."
            )

        requirement_id = requirement.get("id")

        if (
            type(requirement_id) is not int
            or requirement_id < 1
        ):
            raise ValueError(
                "Invalid expected requirement ID."
            )

        if requirement_id in expected_ids:
            raise ValueError(
                "Duplicate expected requirement ID."
            )

        expected_ids.add(requirement_id)

    return expected_ids


# ==========================================
# VALIDATE TEXT
# ==========================================

def validate_text(
    value,
    field: str,
    max_length: int,
    required: bool = True,
) -> list[str]:

    if not isinstance(value, str):
        return [
            f"{field} must be a string."
        ]

    errors = []

    if required and not value.strip():
        errors.append(
            f"{field} must not be empty."
        )

    if len(value.strip()) > max_length:
        errors.append(
            f"{field} exceeds {max_length} characters."
        )

    if "\x00" in value:
        errors.append(
            f"{field} contains a null character."
        )

    return errors


# ==========================================
# VALIDATE SINGLE SUBMISSION RESULT
# ==========================================

def validate_submission_result(
    result: dict,
    pages: list[dict],
    expected_ids: set[int],
    page_numbers: set[int],
) -> list[str]:

    if not isinstance(result, dict):
        return [
            "Submission result must be an object."
        ]

    missing_fields = (
        REQUIRED_FIELDS - result.keys()
    )

    if missing_fields:
        return [
            f"Missing field: {field}"
            for field in sorted(missing_fields)
        ]

    errors = []

    requirement_id = result["requirement_id"]
    status = result["status"]
    feedback = result["feedback"]
    source_page = result["source_page"]
    source_evidence = result["source_evidence"]
    improvement = result["suggested_improvement"]

    # ======================================
    # REQUIREMENT ID
    # ======================================

    if (
        type(requirement_id) is not int
        or requirement_id < 1
    ):
        errors.append(
            "Requirement ID must be a positive integer."
        )

    elif requirement_id not in expected_ids:
        errors.append(
            "Unknown requirement ID."
        )

    # ======================================
    # STATUS
    # ======================================

    valid_status = (
        isinstance(status, str)
        and status in VALID_STATUSES
    )

    if not valid_status:
        errors.append(
            "Invalid submission status."
        )

    # ======================================
    # FEEDBACK
    # ======================================

    errors.extend(
        validate_text(
            feedback,
            "feedback",
            MAX_FEEDBACK_LENGTH,
        )
    )

    # ======================================
    # SUGGESTED IMPROVEMENT
    # ======================================

    errors.extend(
        validate_text(
            improvement,
            "suggested_improvement",
            MAX_IMPROVEMENT_LENGTH,
            required=(
                valid_status
                and status != "fulfilled"
            ),
        )
    )

    # ======================================
    # EVIDENCE PRESENCE
    # ======================================

    has_page = source_page is not None
    has_evidence = source_evidence is not None

    if (
        valid_status
        and status in EVIDENCE_REQUIRED_STATUSES
        and not (has_page and has_evidence)
    ):
        errors.append(
            "Evidence is required for this status."
        )

    if has_page != has_evidence:
        errors.append(
            "Source page and evidence must be provided together."
        )

    # ======================================
    # SOURCE PAGE
    # ======================================

    if has_page:

        if (
            type(source_page) is not int
            or source_page < 1
        ):
            errors.append(
                "Source page must be a positive integer."
            )

        elif source_page not in page_numbers:
            errors.append(
                "Source page does not exist."
            )

    # ======================================
    # SOURCE EVIDENCE
    # ======================================

    if has_evidence:

        errors.extend(
            validate_text(
                source_evidence,
                "source_evidence",
                MAX_EVIDENCE_LENGTH,
            )
        )

    # ======================================
    # VERIFY EVIDENCE AGAINST PDF
    # ======================================

    if not errors and has_page and has_evidence:

        evidence_verified = (
            validate_source_evidence(
                pages=pages,
                source_page=source_page,
                source_evidence=source_evidence,
            )
        )

        if not evidence_verified:
            errors.append(
                "Source evidence could not be verified."
            )

    return errors


# ==========================================
# VALIDATE COMPLETE AI RESPONSE
# ==========================================

def validate_submission_results(
    results: list[dict],
    requirements: list[dict],
    pages: list[dict],
) -> dict:

    if not isinstance(results, list):
        raise ValueError(
            "Submission results must be a list."
        )

    expected_ids = (
        get_expected_requirement_ids(
            requirements
        )
    )

    page_numbers = (
        validate_submission_pages(pages)
    )

    valid_results = []
    invalid_results = []

    seen_ids = set()
    duplicate_ids = set()
    unknown_ids = set()

    # ======================================
    # VALIDATE EACH RESULT
    # ======================================

    for index, result in enumerate(
        results,
        start=1,
    ):

        errors = validate_submission_result(
            result=result,
            pages=pages,
            expected_ids=expected_ids,
            page_numbers=page_numbers,
        )

        if isinstance(result, dict):

            requirement_id = result.get(
                "requirement_id"
            )

            if type(requirement_id) is int:

                if requirement_id in seen_ids:

                    duplicate_ids.add(
                        requirement_id
                    )

                    errors.append(
                        "Duplicate requirement ID."
                    )

                seen_ids.add(requirement_id)

                if requirement_id not in expected_ids:

                    unknown_ids.add(
                        requirement_id
                    )

        if errors:

            invalid_results.append(
                {
                    "index": index,
                    "result": result,
                    "errors": errors,
                }
            )

            continue

        # Build a clean result.
        # Do not trust AI-generated verification flags.

        validated = {
            "requirement_id": result["requirement_id"],
            "status": result["status"],
            "feedback": result["feedback"].strip(),
            "source_page": result["source_page"],
            "source_evidence": (
                result["source_evidence"].strip()
                if result["source_evidence"] is not None
                else None
            ),
            "suggested_improvement": (
                result["suggested_improvement"].strip()
            ),
            "evidence_verified": (
                True
                if result["source_evidence"] is not None
                else None
            ),
            "pipeline_version": (
                SUBMISSION_VALIDATOR_VERSION
            ),
        }

        valid_results.append(validated)

    # ======================================
    # COMPLETENESS CHECK
    # ======================================

    missing_ids = expected_ids - seen_ids

    valid_ids = {
        result["requirement_id"]
        for result in valid_results
    }

    unvalidated_ids = expected_ids - valid_ids

    can_persist = (
        not invalid_results
        and not missing_ids
        and not duplicate_ids
        and not unknown_ids
        and not unvalidated_ids
        and len(valid_results) == len(expected_ids)
    )

    # ======================================
    # STATISTICS
    # ======================================

    status_counts = {
        "fulfilled": 0,
        "partially_fulfilled": 0,
        "missing": 0,
        "unclear": 0,
    }

    for result in valid_results:

        status_counts[result["status"]] += 1

    verified_count = sum(
        1
        for result in valid_results
        if result["evidence_verified"] is True
    )

    total = len(results)
    valid_count = len(valid_results)
    invalid_count = len(invalid_results)

    validation_rate = (
        round(valid_count / total * 100, 2)
        if total
        else None
    )

    coverage_rate = round(
        len(valid_ids) / len(expected_ids) * 100,
        2,
    )

    completion_percentage = (
        round(
            status_counts["fulfilled"]
            / len(expected_ids)
            * 100,
            2,
        )
        if can_persist
        else None
    )

    # ======================================
    # FINAL RESPONSE
    # ======================================

    return {
        "pipeline_version": (
            SUBMISSION_VALIDATOR_VERSION
        ),

        "status": (
            "completed"
            if can_persist
            else "failed"
        ),

        "can_persist": can_persist,

        "review_required": (
            not can_persist
            or status_counts["unclear"] > 0
        ),

        "results": valid_results,

        "invalid_results": invalid_results,

        "missing_requirement_ids": sorted(
            missing_ids
        ),

        "duplicate_requirement_ids": sorted(
            duplicate_ids
        ),

        "unknown_requirement_ids": sorted(
            unknown_ids
        ),

        "unvalidated_requirement_ids": sorted(
            unvalidated_ids
        ),

        "status_counts": status_counts,

        "statistics": {
            "expected": len(expected_ids),
            "total": total,
            "valid": valid_count,
            "invalid": invalid_count,
            "verified_evidence": verified_count,
            "validation_rate": validation_rate,
            "coverage_rate": coverage_rate,
            "completion_percentage": (
                completion_percentage
            ),
        },
    }
