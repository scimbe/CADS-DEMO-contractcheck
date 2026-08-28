from difftool import compute_diff, count_changed_lines


def test_diff_of_identical_texts_is_empty():
    text = "line one\nline two\nline three"
    assert compute_diff(text, text) == ""


def test_diff_format_has_unified_headers():
    a = "Clause 4\nEach invoice is due within 30 days.\nEnd."
    b = "Clause 4\nEach invoice is due within 45 days.\nEnd."
    diff = compute_diff(a, b, label_a="v1.pdf", label_b="v2.pdf")
    assert diff.startswith("--- v1.pdf")
    assert "+++ v2.pdf" in diff
    assert "@@" in diff
    assert "-Each invoice is due within 30 days." in diff
    assert "+Each invoice is due within 45 days." in diff


def test_count_changed_lines_excludes_headers():
    a = "one\ntwo\nthree"
    b = "one\nTWO\nthree"
    diff = compute_diff(a, b, label_a="a", label_b="b")
    # exactly one removed + one added content line
    assert count_changed_lines(diff) == 2


def test_count_changed_lines_zero_for_no_diff():
    assert count_changed_lines("") == 0
