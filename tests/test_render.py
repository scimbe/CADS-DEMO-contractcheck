"""Rendering is the deterministic, tool-computed half of the visual comparison --
these tests need no LLM key.
"""

import pytest
from conftest import FIXTURES
from render import RenderError, page_count, render_pages


def test_page_count_of_fixture():
    assert page_count(FIXTURES / "contract_v1.pdf") == 1
    assert page_count(FIXTURES / "report_v1.pdf") == 1


def test_page_count_missing_file_raises():
    with pytest.raises(RenderError):
        page_count(FIXTURES / "does_not_exist.pdf")


def test_render_pages_produces_one_png_per_page(tmp_path):
    pages = render_pages(FIXTURES / "contract_v1.pdf", tmp_path, dpi=80)
    assert len(pages) == 1
    assert pages[0].suffix == ".png"
    assert pages[0].is_file()
    assert pages[0].stat().st_size > 0


def test_render_is_deterministic(tmp_path):
    """Same PDF at the same DPI -> byte-identical pixels (the property the
    vision byte-identical pre-check relies on)."""
    a = render_pages(FIXTURES / "report_v1.pdf", tmp_path / "a", dpi=100)
    b = render_pages(FIXTURES / "report_v1.pdf", tmp_path / "b", dpi=100)
    assert a[0].read_bytes() == b[0].read_bytes()


def test_render_missing_file_raises(tmp_path):
    with pytest.raises(RenderError):
        render_pages(FIXTURES / "does_not_exist.pdf", tmp_path)
