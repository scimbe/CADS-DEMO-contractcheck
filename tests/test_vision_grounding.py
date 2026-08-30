"""Visual-comparison acceptance test.

The compelling claim of the visual half: it catches a change a pure text diff is
BLIND to. The committed fixtures report_v1.pdf / report_v2.pdf have an IDENTICAL
text layer (so the text diff is empty) but a DIFFERENT embedded graphic (a green
square vs. a red circle). This test proves:

  1. the text diff really is empty (tool-computed, no key needed), and
  2. the vision comparison really does report the graphic change (needs an LLM key;
     skips automatically if none is configured).

It also checks the deterministic byte-identical pre-check, which needs no key.
"""

import shutil
from pathlib import Path

import pytest
from conftest import FIXTURES
from difftool import compute_diff, count_changed_lines
from extract import extract_text
from render import render_pages

import llmconfig
from vision import compare_pages

OUTPUT_DIR = Path(__file__).resolve().parent / ".output"


def test_text_diff_of_visual_fixtures_is_empty():
    """No key needed: the two visual fixtures are textually identical by construction."""
    a = extract_text(FIXTURES / "report_v1.pdf")
    b = extract_text(FIXTURES / "report_v2.pdf")
    assert count_changed_lines(compute_diff(a, b)) == 0


def test_byte_identical_pages_shortcircuit_without_llm(tmp_path):
    """No key needed: identical renders are resolved by the tool, never the model."""
    original = FIXTURES / "report_v1.pdf"
    copy = tmp_path / "copy.pdf"
    shutil.copyfile(original, copy)
    a = render_pages(original, tmp_path / "a", dpi=100)
    b = render_pages(copy, tmp_path / "b", dpi=100)
    result = compare_pages(a[0], b[0], page_label="page 1")
    assert result["identical"] is True
    assert result["tool_verified"] is True
    assert result["model"] is None


@pytest.mark.skipif(
    not llmconfig.LLMConfig.api_key,
    reason="LLM_API_KEY not configured -- skipping live vision grounding acceptance test",
)
def test_vision_catches_change_text_diff_is_blind_to(tmp_path, capsys):
    a = render_pages(FIXTURES / "report_v1.pdf", tmp_path / "a", dpi=100, max_pages=1)
    b = render_pages(FIXTURES / "report_v2.pdf", tmp_path / "b", dpi=100, max_pages=1)
    assert a[0].read_bytes() != b[0].read_bytes()  # the pages genuinely differ visually

    result = compare_pages(a[0], b[0], page_label="page 1")
    findings = result["differences"].lower()

    # The model must actually report a difference (not the identical sentinel) and
    # ground it in the real change: a red/circle appearing and/or a green/square leaving.
    assert result["identical"] is False, f"vision missed the visual change: {findings!r}"
    assert "red" in findings or "circle" in findings, f"vision did not describe the new graphic: {findings!r}"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "visual_acceptance.md").write_text(
        f"# Visual acceptance\n\nText diff changed lines: 0 (identical text layer)\n\n"
        f"Vision findings (model: {result['model']}):\n\n{result['differences']}\n"
    )
    with capsys.disabled():
        print("\n[vision] " + result["differences"])
