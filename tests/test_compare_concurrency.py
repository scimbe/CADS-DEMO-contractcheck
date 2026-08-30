"""The text and image halves run concurrently, and the per-page vision calls run with
bounded concurrency -- WITHOUT changing the output (page order, content) or the
byte-identical short-circuit. These tests fully mock the leaf calls, so no key/network
and no real rendering is needed.
"""

import time
from pathlib import Path

import compare as compare_mod
import summarize
import vision
from compare import _parallel_ordered, compare


# ---- ordering / correctness ---------------------------------------------------------

def _fake_pages(prefix, n):
    return [Path(f"{prefix}-{i + 1}.png") for i in range(n)]


def test_parallel_ordered_preserves_input_order():
    # Even with staggered sleeps, results must come back in input order.
    def fn(i):
        time.sleep((5 - i) * 0.02)  # later items finish sooner
        return i
    assert _parallel_ordered(fn, list(range(5)), max_workers=5) == [0, 1, 2, 3, 4]


def test_parallel_ordered_empty_and_single():
    assert _parallel_ordered(lambda x: x, [], max_workers=4) == []
    assert _parallel_ordered(lambda x: x * 2, [3], max_workers=4) == [6]


def test_page_results_stay_in_page_order(monkeypatch):
    monkeypatch.setattr(compare_mod, "page_count", lambda p: 3)
    monkeypatch.setattr(compare_mod, "render_pages",
                        lambda pdf, out, **kw: _fake_pages(Path(out) / Path(pdf).stem, 3))

    def fake_compare_pages(a, b, *, page_label="page", model=None):
        return {"page_label": page_label, "differences": f"diff {page_label}",
                "identical": False, "tool_verified": False, "model": "m"}
    monkeypatch.setattr(vision, "compare_pages", fake_compare_pages)
    monkeypatch.setattr(summarize, "summarize_diff",
                        lambda diff: {"summary": "s", "ambiguities": [], "raw_response": ""})
    monkeypatch.setattr(compare_mod, "extract_text", lambda p: "same text")

    result = compare("fixtures/report_v1.pdf", "fixtures/report_v2.pdf", max_pages=3)
    labels = [pr["page_label"] for pr in result["images"]["page_results"]]
    assert labels == ["page 1", "page 2", "page 3"]
    assert result["images"]["pages_compared"] == 3


# ---- concurrency actually overlaps --------------------------------------------------

def test_text_and_image_halves_run_concurrently(monkeypatch):
    """Text half and image half each sleep ~0.3s; concurrently the whole call should
    finish well under the ~0.6s a sequential run would take."""
    monkeypatch.setattr(compare_mod, "extract_text", lambda p: "text")
    monkeypatch.setattr(compare_mod, "page_count", lambda p: 1)
    monkeypatch.setattr(compare_mod, "render_pages",
                        lambda pdf, out, **kw: _fake_pages(Path(out) / "p", 1))

    def slow_summarize(diff):
        time.sleep(0.3)
        return {"summary": "s", "ambiguities": [], "raw_response": ""}

    def slow_compare_pages(a, b, *, page_label="page", model=None):
        time.sleep(0.3)
        return {"page_label": page_label, "differences": "d", "identical": False,
                "tool_verified": False, "model": "m"}

    monkeypatch.setattr(summarize, "summarize_diff", slow_summarize)
    monkeypatch.setattr(vision, "compare_pages", slow_compare_pages)

    start = time.perf_counter()
    result = compare("a.pdf", "b.pdf", max_pages=1)
    elapsed = time.perf_counter() - start

    # Sequential would be ~0.6s; concurrent ~0.3s. Generous bound to avoid flakiness.
    assert elapsed < 0.5, f"halves did not overlap (elapsed {elapsed:.2f}s)"
    assert result["text"]["summary"]["summary"] == "s"
    assert result["images"]["page_results"][0]["differences"] == "d"


def test_per_page_vision_calls_run_concurrently(monkeypatch):
    """Three page comparisons at ~0.3s each should overlap under concurrency 3."""
    monkeypatch.setattr(compare_mod, "extract_text", lambda p: "text")
    monkeypatch.setattr(compare_mod, "page_count", lambda p: 3)
    monkeypatch.setattr(compare_mod, "render_pages",
                        lambda pdf, out, **kw: _fake_pages(Path(out) / "p", 3))
    monkeypatch.setattr(summarize, "summarize_diff",
                        lambda diff: {"summary": "s", "ambiguities": [], "raw_response": ""})

    def slow_compare_pages(a, b, *, page_label="page", model=None):
        time.sleep(0.3)
        return {"page_label": page_label, "differences": "d", "identical": False,
                "tool_verified": False, "model": "m"}
    monkeypatch.setattr(vision, "compare_pages", slow_compare_pages)

    start = time.perf_counter()
    result = compare("a.pdf", "b.pdf", max_pages=3, max_concurrency=3)
    elapsed = time.perf_counter() - start

    # Serial would be ~0.9s (3 x 0.3); concurrent ~0.3s.
    assert elapsed < 0.6, f"per-page vision calls did not overlap (elapsed {elapsed:.2f}s)"
    assert len(result["images"]["page_results"]) == 3
