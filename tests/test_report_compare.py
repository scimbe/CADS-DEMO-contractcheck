"""The combined text+visual report must show the literal diff and the literal
visual findings, and must distinguish tool-verified identity from a model claim.
No LLM key needed.
"""

from report import render_compare_report


def _result(**overrides):
    base = {
        "doc_a": "a.pdf",
        "doc_b": "b.pdf",
        "text": {"diff": "--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new", "changed_lines": 2,
                 "summary": {"summary": "The clause changed.", "ambiguities": ["check scope"]}},
        "images": {"pages_compared": 1, "page_results": [], "extra_pages": [], "note": None},
    }
    base.update(overrides)
    return base


def test_report_contains_literal_diff_and_summary():
    report = render_compare_report(_result())
    assert "-old" in report and "+new" in report
    assert "The clause changed." in report
    assert "check scope" in report
    assert "changed lines: **2**" in report.lower()


def test_report_shows_visual_difference_verbatim():
    r = _result(images={"pages_compared": 1, "extra_pages": [], "note": None,
                        "page_results": [{"page_label": "page 1",
                                          "differences": "- logo changed from green to red",
                                          "identical": False, "tool_verified": False, "model": "m"}]})
    report = render_compare_report(r)
    assert "logo changed from green to red" in report


def test_report_marks_tool_verified_identity():
    r = _result(images={"pages_compared": 1, "extra_pages": [], "note": None,
                        "page_results": [{"page_label": "page 1", "differences": "",
                                          "identical": True, "tool_verified": True, "model": None}]})
    report = render_compare_report(r)
    assert "tool-verified" in report


def test_report_handles_llm_skipped():
    r = _result(text={"diff": "", "changed_lines": 0, "summary": None})
    report = render_compare_report(r)
    assert "LLM text summary skipped" in report


def test_report_writes_file(tmp_path):
    out = tmp_path / "r.md"
    render_compare_report(_result(), out_path=out)
    assert out.is_file()
    assert "Document Comparison Report" in out.read_text()
