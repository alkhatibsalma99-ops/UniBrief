import re
import unicodedata

from difflib import SequenceMatcher


def normalize_requirement_text(text: str) -> str:

    text = unicodedata.normalize("NFC", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def requirement_key(requirement: dict) -> tuple:

    return (
        normalize_requirement_text(
            requirement["title"]
        ),
        normalize_requirement_text(
            requirement["description"]
        ),
        requirement["priority"],
    )


def calculate_similarity(
    first: dict,
    second: dict,
) -> float:

    first_text = normalize_requirement_text(
        first["title"] + " " + first["description"]
    ).casefold()

    second_text = normalize_requirement_text(
        second["title"] + " " + second["description"]
    ).casefold()

    return SequenceMatcher(
        None,
        first_text,
        second_text,
        autojunk=False,
    ).ratio()


def deduplicate_requirements(
    requirements: list[dict],
    similarity_threshold: float = 0.85,
) -> dict:

    if not 0 <= similarity_threshold <= 1:
        raise ValueError(
            "Invalid similarity threshold."
        )

    unique_requirements = []

    exact_duplicates = []

    possible_duplicates = []

    seen = {}

    # ======================================
    # EXACT DUPLICATE DETECTION
    # ======================================

    for requirement in requirements:

        key = requirement_key(requirement)

        if key in seen:

            exact_duplicates.append(
                {
                    "original": seen[key],
                    "duplicate": requirement,
                }
            )

            continue

        seen[key] = requirement

        unique_requirements.append(requirement)

    # ======================================
    # SIMILARITY DETECTION
    # ======================================

    for i, first in enumerate(unique_requirements):

        for second in unique_requirements[i + 1:]:

            similarity = calculate_similarity(
                first,
                second,
            )

            if similarity >= similarity_threshold:

                possible_duplicates.append(
                    {
                        "first": first,
                        "second": second,
                        "similarity": round(
                            similarity,
                            4,
                        ),
                    }
                )

    # ======================================
    # FINAL RESULT
    # ======================================

    return {
        "requirements": unique_requirements,

        "exact_duplicates": exact_duplicates,

        "possible_duplicates": possible_duplicates,

        "statistics": {
            "original_count": len(requirements),

            "unique_count": len(
                unique_requirements
            ),

            "exact_duplicates_count": len(
                exact_duplicates
            ),

            "possible_duplicates_count": len(
                possible_duplicates
            ),
        },
    }