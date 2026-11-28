from app.evidence_validator import (
    validate_source_evidence,
)


MAX_TITLE_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 2000

VALID_PRIORITIES = {
    "high",
    "medium",
    "low",
}

REQUIRED_FIELDS = {
    "title",
    "description",
    "priority",
    "source_page",
    "source_evidence",
}


def validate_requirement(
    requirement: dict,
    pages: list[dict],
) -> list[str]:

    errors = []

    if not isinstance(requirement, dict):
        return ["Requirement must be an object."]

    missing_fields = (
        REQUIRED_FIELDS - requirement.keys()
    )

    if missing_fields:
        return [
            f"Missing field: {field}"
            for field in sorted(missing_fields)
        ]

    title = requirement["title"]
    description = requirement["description"]
    priority = requirement["priority"]
    source_page = requirement["source_page"]
    source_evidence = requirement["source_evidence"]

    # ======================================
    # TITLE VALIDATION
    # ======================================

    if not isinstance(title, str):

        errors.append(
            "Title must be a string."
        )

    elif not title.strip():

        errors.append(
            "Title must not be empty."
        )

    elif len(title.strip()) > MAX_TITLE_LENGTH:

        errors.append(
            "Title exceeds 255 characters."
        )

    # ======================================
    # DESCRIPTION VALIDATION
    # ======================================

    if not isinstance(description, str):

        errors.append(
            "Description must be a string."
        )

    elif not description.strip():

        errors.append(
            "Description must not be empty."
        )

    elif (
        len(description.strip())
        > MAX_DESCRIPTION_LENGTH
    ):

        errors.append(
            "Description exceeds 2000 characters."
        )

    # ======================================
    # PRIORITY VALIDATION
    # ======================================

    if (
        not isinstance(priority, str)
        or priority not in VALID_PRIORITIES
    ):

        errors.append(
            "Invalid requirement priority."
        )

    # ======================================
    # SOURCE PAGE VALIDATION
    # ======================================

    if type(source_page) is not int:

        errors.append(
            "Source page must be an integer."
        )

    elif source_page < 1:

        errors.append(
            "Source page must be positive."
        )

    elif not any(
        page["page_number"] == source_page
        for page in pages
    ):

        errors.append(
            "Source page does not exist."
        )

    # ======================================
    # SOURCE EVIDENCE VALIDATION
    # ======================================

    if not isinstance(source_evidence, str):

        errors.append(
            "Source evidence must be a string."
        )

    elif not source_evidence.strip():

        errors.append(
            "Source evidence must not be empty."
        )

    # ======================================
    # DATABASE TEXT SAFETY
    # ======================================

    for field in (
        "title",
        "description",
        "source_evidence",
    ):

        value = requirement[field]

        if (
            isinstance(value, str)
            and "\x00" in value
        ):

            errors.append(
                f"{field} contains a null character."
            )

    # ======================================
    # EVIDENCE VERIFICATION
    # ======================================

    if not errors:

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


def validate_requirements(
    requirements: list[dict],
    pages: list[dict],
) -> dict:

    if not isinstance(requirements, list):

        raise ValueError(
            "Requirements must be a list."
        )

    if not isinstance(pages, list) or not pages:

        raise ValueError(
            "Valid PDF pages are required."
        )

    page_numbers = set()

    for page in pages:

        if not isinstance(page, dict):
            raise ValueError("Invalid page object.")

        number = page.get("page_number")
        text = page.get("text")

        if type(number) is not int or number < 1:
            raise ValueError("Invalid page number.")

        if number in page_numbers:
            raise ValueError("Duplicate page number.")

        if not isinstance(text, str):
            raise ValueError("Invalid page text.")

        page_numbers.add(number)

    valid_requirements = []

    invalid_requirements = []

    for index, requirement in enumerate(
        requirements,
        start=1,
    ):

        errors = validate_requirement(
            requirement,
            pages,
        )

        if errors:

            invalid_requirements.append(
                {
                    "index": index,
                    "requirement": requirement,
                    "errors": errors,
                }
            )

            continue

        validated = requirement.copy()

        validated["title"] = (
            validated["title"].strip()
        )

        validated["description"] = (
            validated["description"].strip()
        )

        validated["source_evidence"] = (
            validated["source_evidence"].strip()
        )

        validated["evidence_verified"] = True

        valid_requirements.append(validated)

    total = len(requirements)

    valid_count = len(valid_requirements)

    invalid_count = len(invalid_requirements)

    validation_rate = (
        round(valid_count / total * 100, 2)
        if total
        else None
    )

    return {
        "requirements": valid_requirements,

        "invalid_requirements": (
            invalid_requirements
        ),

        "statistics": {
            "total": total,
            "valid": valid_count,
            "invalid": invalid_count,
            "validation_rate": validation_rate,
        },
    }