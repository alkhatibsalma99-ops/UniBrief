import re
import unicodedata


def normalize_text(text: str) -> str:

    text = unicodedata.normalize("NFKC", text)

    text = text.replace("\u00ad", "")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_line_breaks(
    text: str,
    keep_hyphen: bool = False,
) -> str:

    text = unicodedata.normalize("NFKC", text)

    replacement = "-" if keep_hyphen else ""

    text = re.sub(
        r"(?<=[^\W\d_])-[ \t]*\r?\n[ \t]*(?=[^\W\d_])",
        replacement,
        text,
    )

    return normalize_text(text)


def validate_source_evidence(
    pages: list[dict],
    source_page: int,
    source_evidence: str,
) -> bool:

    if type(source_page) is not int:
        return False

    if source_page < 1:
        return False

    if not isinstance(source_evidence, str):
        return False

    evidence = normalize_text(source_evidence)

    if not evidence:
        return False

    for page in pages:

        if page["page_number"] != source_page:
            continue

        original_text = page["text"]

        candidates = [
            normalize_text(original_text),

            normalize_line_breaks(
                original_text,
                keep_hyphen=False,
            ),

            normalize_line_breaks(
                original_text,
                keep_hyphen=True,
            ),
        ]

        return any(
            evidence in candidate
            for candidate in candidates
        )

    return False