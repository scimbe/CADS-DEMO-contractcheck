"""The tool-computed-diff acceptance check: runs the REAL extract -> diff
pipeline on the two committed synthetic PDF fixtures (never on hand-typed
text) and proves it catches exactly the one real change and nothing else.
"""

from conftest import FIXTURES
from difftool import compute_diff, count_changed_lines
from extract import extract_text


def _run_real_pipeline() -> str:
    text_a = extract_text(FIXTURES / "contract_v1.pdf")
    text_b = extract_text(FIXTURES / "contract_v2.pdf")
    return compute_diff(text_a, text_b, label_a="contract_v1.pdf", label_b="contract_v2.pdf")


def test_diff_contains_expected_fragment():
    diff = _run_real_pipeline()
    expected_fragment = (FIXTURES / "expected_diff_fragment.txt").read_text().strip("\n")
    assert expected_fragment in diff


def test_diff_touches_exactly_one_change():
    """Exactly 2 changed (+/-) lines -- proving the tool caught precisely the
    one real clause change (30 days -> 45 days) and flagged nothing else."""
    diff = _run_real_pipeline()
    assert count_changed_lines(diff) == 2


def test_diff_is_not_the_decoy():
    """Sanity check that the real diff and the decoy diff fixture are
    genuinely different documents -- guards against the decoy accidentally
    matching reality."""
    diff = _run_real_pipeline()
    decoy = (FIXTURES / "decoy_diff.txt").read_text()
    assert "60 days" not in diff
    assert "sixty (60) days after written notice" not in diff
    assert diff != decoy
