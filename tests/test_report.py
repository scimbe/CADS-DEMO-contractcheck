from report import render_report


def test_report_contains_literal_diff_block():
    diff_text = "--- a\n+++ b\n@@ -1 +1 @@\n-old line\n+new line"
    summary_result = {"summary": "The clause changed.", "ambiguities": []}
    report = render_report(diff_text, summary_result)
    assert diff_text in report


def test_report_contains_literal_summary():
    diff_text = "--- a\n+++ b"
    summary_result = {"summary": "A very specific summary sentence.", "ambiguities": ["one ambiguity"]}
    report = render_report(diff_text, summary_result)
    assert "A very specific summary sentence." in report
    assert "one ambiguity" in report


def test_report_handles_no_ambiguities():
    report = render_report("diff", {"summary": "ok", "ambiguities": []})
    assert "(none flagged)" in report


def test_report_writes_to_file(tmp_path):
    out_path = tmp_path / "report.md"
    render_report("diff content", {"summary": "s", "ambiguities": []}, out_path=out_path)
    assert out_path.is_file()
    assert "diff content" in out_path.read_text()
