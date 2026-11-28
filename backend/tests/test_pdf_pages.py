import importlib

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fastapi import HTTPException


main = importlib.import_module("app.main")


@pytest.fixture
def mock_pdf(monkeypatch):

    def configure(page_texts):

        reader = MagicMock()

        reader.pages = []

        for text in page_texts:

            page = MagicMock()
            page.extract_text.return_value = text

            reader.pages.append(page)

        monkeypatch.setattr(
            main,
            "get_file_bytes",
            lambda db_file: b"mock-pdf",
        )

        monkeypatch.setattr(
            main,
            "PdfReader",
            lambda stream: reader,
        )

        return SimpleNamespace(
            filename="assignment.pdf"
        )

    return configure


# ==========================================
# TEST 1: CORRECT PAGE NUMBERS
# ==========================================

def test_read_pdf_pages_preserves_page_numbers(
    mock_pdf,
):

    db_file = mock_pdf(
        ["Page one", "Page two", "Page three"]
    )

    result = main.read_pdf_pages(db_file)

    assert result == [
        {
            "page_number": 1,
            "text": "Page one",
        },
        {
            "page_number": 2,
            "text": "Page two",
        },
        {
            "page_number": 3,
            "text": "Page three",
        },
    ]


# ==========================================
# TEST 2: EMPTY PAGES
# ==========================================

def test_empty_pages_are_preserved(mock_pdf):

    db_file = mock_pdf(
        ["First page", "", "Third page"]
    )

    result = main.read_pdf_pages(db_file)

    assert len(result) == 3
    assert result[1]["page_number"] == 2
    assert result[1]["text"] == ""
    assert result[2]["page_number"] == 3


# ==========================================
# TEST 3: NONE TEXT
# ==========================================

def test_none_text_is_converted_to_empty_string(
    mock_pdf,
):

    db_file = mock_pdf([None])

    result = main.read_pdf_pages(db_file)

    assert result == [
        {
            "page_number": 1,
            "text": "",
        }
    ]


# ==========================================
# TEST 4: BACKWARD COMPATIBILITY
# ==========================================

def test_read_pdf_text_remains_compatible(
    mock_pdf,
):

    db_file = mock_pdf(
        ["First page", "", None, "Last page"]
    )

    result = main.read_pdf_text(db_file)

    assert result == "First page\nLast page"


# ==========================================
# TEST 5: UNSUPPORTED FILE
# ==========================================

def test_non_pdf_file_is_rejected(monkeypatch):

    db_file = SimpleNamespace(
        filename="assignment.txt"
    )

    download = MagicMock()

    monkeypatch.setattr(
        main,
        "get_file_bytes",
        download,
    )

    with pytest.raises(HTTPException) as error:
        main.read_pdf_pages(db_file)

    assert error.value.status_code == 400

    download.assert_not_called()


# ==========================================
# TEST 6: INVALID PDF
# ==========================================

def test_invalid_pdf_returns_422(monkeypatch):

    db_file = SimpleNamespace(
        filename="invalid.pdf"
    )

    monkeypatch.setattr(
        main,
        "get_file_bytes",
        lambda db_file: b"invalid-pdf",
    )

    def invalid_reader(stream):
        raise ValueError("Invalid PDF")

    monkeypatch.setattr(
        main,
        "PdfReader",
        invalid_reader,
    )

    with pytest.raises(HTTPException) as error:
        main.read_pdf_pages(db_file)

    assert error.value.status_code == 422


# ==========================================
# TEST 7: EMPTY DOCUMENT
# ==========================================

def test_document_without_pages(mock_pdf):

    db_file = mock_pdf([])

    assert main.read_pdf_pages(db_file) == []
    assert main.read_pdf_text(db_file) == ""


# ==========================================
# TEST 8: PAGE EXTRACTION FAILURE
# ==========================================

def test_page_extraction_failure_returns_422(
    monkeypatch,
):

    db_file = SimpleNamespace(
        filename="assignment.pdf"
    )

    first_page = MagicMock()
    first_page.extract_text.return_value = "Page one"

    second_page = MagicMock()
    second_page.extract_text.side_effect = ValueError(
        "Extraction failed"
    )

    reader = MagicMock()
    reader.pages = [first_page, second_page]

    monkeypatch.setattr(
        main,
        "get_file_bytes",
        lambda db_file: b"mock-pdf",
    )

    monkeypatch.setattr(
        main,
        "PdfReader",
        lambda stream: reader,
    )

    with pytest.raises(HTTPException) as error:
        main.read_pdf_pages(db_file)

    assert error.value.status_code == 422