from pathlib import Path

import pytest
from conftest import FIXTURES
from extract import ExtractionError, extract_text


def test_extract_contains_known_literal_strings():
    text = extract_text(FIXTURES / "contract_v1.pdf")
    assert "Clause 4" in text
    assert "30 days" in text
    assert "Clause 6" in text


def test_extract_v2_has_new_term():
    text = extract_text(FIXTURES / "contract_v2.pdf")
    assert "45 days" in text
    assert "30 days" not in text


def test_extract_is_deterministic():
    """Running extraction twice on the same file must produce byte-identical output."""
    first = extract_text(FIXTURES / "contract_v1.pdf")
    second = extract_text(FIXTURES / "contract_v1.pdf")
    assert first == second


def test_extract_missing_file_raises():
    with pytest.raises(ExtractionError):
        extract_text(FIXTURES / "does_not_exist.pdf")
