import json

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import ai_service


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
                "Implement at least eight "
                "automated tests."
            ),
        },
    ]


def make_requirement(
    page=2,
    evidence="Implement at least eight automated tests.",
):

    return {
        "title": "Implement tests",
        "description": (
            "Implement at least eight automated tests."
        ),
        "priority": "high",
        "source_page": page,
        "source_evidence": evidence,
    }


def mock_ai(
    monkeypatch,
    requirements,
    status="completed",
):

    response = SimpleNamespace(
        status=status,
        output_text=json.dumps(
            {"requirements": requirements}
        ),
    )

    create = MagicMock(
        return_value=response
    )

    monkeypatch.setattr(
        ai_service.client.responses,
        "create",
        create,
    )

    return create


# ==========================================
# TEST 1: VERIFIED REQUIREMENT
# ==========================================

def test_verified_requirement(
    monkeypatch,
    pages,
):

    create = mock_ai(
        monkeypatch,
        [make_requirement()],
    )

    result = (
        ai_service.extract_requirements_with_evidence(
            pages
        )
    )

    assert len(result["requirements"]) == 1

    assert (
        result["requirements"][0]["evidence_verified"]
        is True
    )

    assert result["statistics"]["verified"] == 1

    assert (
        result["statistics"]["verification_rate"]
        == 100.0
    )

    create.assert_called_once()


# ==========================================
# TEST 2: WRONG PAGE
# ==========================================

def test_wrong_page(
    monkeypatch,
    pages,
):

    mock_ai(
        monkeypatch,
        [make_requirement(page=1)],
    )

    result = (
        ai_service.extract_requirements_with_evidence(
            pages
        )
    )

    assert result["requirements"] == []

    assert len(
        result["unverified_requirements"]
    ) == 1

    assert result["statistics"]["unverified"] == 1


# ==========================================
# TEST 3: INVENTED EVIDENCE
# ==========================================

def test_invented_evidence(
    monkeypatch,
    pages,
):

    mock_ai(
        monkeypatch,
        [
            make_requirement(
                evidence="Implement fifty tests."
            )
        ],
    )

    result = (
        ai_service.extract_requirements_with_evidence(
            pages
        )
    )

    assert result["requirements"] == []

    assert (
        result["statistics"]["verification_rate"]
        == 0.0
    )


# ==========================================
# TEST 4: MIXED RESULTS
# ==========================================

def test_mixed_results(
    monkeypatch,
    pages,
):

    mock_ai(
        monkeypatch,
        [
            make_requirement(),
            make_requirement(page=99),
        ],
    )

    result = (
        ai_service.extract_requirements_with_evidence(
            pages
        )
    )

    assert result["statistics"] == {
        "total": 2,
        "verified": 1,
        "unverified": 1,
        "verification_rate": 50.0,
    }


# ==========================================
# TEST 5: EMPTY DOCUMENT
# ==========================================

def test_empty_document(monkeypatch):

    create = mock_ai(
        monkeypatch,
        [],
    )

    with pytest.raises(ValueError):

        ai_service.extract_requirements_with_evidence(
            []
        )

    create.assert_not_called()


# ==========================================
# TEST 6: EMPTY PAGE TEXT
# ==========================================

def test_empty_page_text(monkeypatch):

    create = mock_ai(
        monkeypatch,
        [],
    )

    with pytest.raises(ValueError):

        ai_service.extract_requirements_with_evidence(
            [
                {
                    "page_number": 1,
                    "text": "",
                }
            ]
        )

    create.assert_not_called()


# ==========================================
# TEST 7: INCOMPLETE AI RESPONSE
# ==========================================

def test_incomplete_response(
    monkeypatch,
    pages,
):

    mock_ai(
        monkeypatch,
        [],
        status="incomplete",
    )

    with pytest.raises(RuntimeError):

        ai_service.extract_requirements_with_evidence(
            pages
        )


# ==========================================
# TEST 8: NO REQUIREMENTS
# ==========================================

def test_no_requirements(
    monkeypatch,
    pages,
):

    mock_ai(
        monkeypatch,
        [],
    )

    result = (
        ai_service.extract_requirements_with_evidence(
            pages
        )
    )

    assert result["statistics"] == {
        "total": 0,
        "verified": 0,
        "unverified": 0,
        "verification_rate": None,
    }


# ==========================================
# TEST 9: PAGE DATA SENT TO AI
# ==========================================

def test_page_data_sent_to_ai(
    monkeypatch,
    pages,
):

    create = mock_ai(
        monkeypatch,
        [make_requirement()],
    )

    ai_service.extract_requirements_with_evidence(
        pages
    )

    arguments = create.call_args.kwargs

    payload = json.loads(arguments["input"])

    assert payload["pages"] == pages

    assert arguments["model"] == ai_service.MODEL

    assert "instructions" in arguments


# ==========================================
# TEST 10: DUPLICATE PAGE NUMBERS
# ==========================================

def test_duplicate_page_numbers(
    monkeypatch,
):

    create = mock_ai(
        monkeypatch,
        [],
    )

    with pytest.raises(ValueError):

        ai_service.extract_requirements_with_evidence(
            [
                {
                    "page_number": 1,
                    "text": "First page",
                },
                {
                    "page_number": 1,
                    "text": "Second page",
                },
            ]
        )

    create.assert_not_called()