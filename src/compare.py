"""High-level document comparison: text diff + visual (image) comparison in one call.

`compare(pdf_a, pdf_b)` is the single entrypoint the frontend/wrapper should call for
"the user uploaded two PDFs, compare them". It returns a structured dict with:

    {
      "doc_a", "doc_b":  filenames,
      "text":  {"diff", "changed_lines", "summary"},   # summary None if use_llm=False
      "images": {"pages_compared", "page_results":[...], "extra_pages", "note", "rendered"},
      "report": "<markdown>",                            # combined human-readable report
    }

The two halves are independent and each is individually skippable (`use_llm`,
`use_vision`), so the tool still works with no API key (text diff only) and degrades
gracefully if page rendering is unavailable.

Concurrency: the text half (pdftotext -> difflib -> LLM summary) and the image half
(render -> vision) touch different tools/models over the same two inputs, so they run
as concurrent branches. Inside the image half the two page renders run in parallel and
the per-page vision comparisons run with bounded concurrency. This is purely a
scheduling change -- the diff, the page pairing (by index), the byte-identical
short-circuit, and the result ordering are all unchanged, so output is deterministic.
"""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from difftool import compute_diff, count_changed_lines
from extract import extract_text
from render import RenderError, page_count, render_pages
from report import render_compare_report

# Bounded concurrency for the per-page vision calls. The vision endpoint is typically a
# single local model, so this stays small on purpose (it may still serialize server-side).
DEFAULT_VISION_CONCURRENCY = 3


def _parallel_ordered(fn: Callable, items: list, max_workers: int) -> list:
    """Run fn(item) over items concurrently, returning results in the INPUT order.

    `fn` is expected to handle its own per-item errors; unexpected exceptions propagate.
    Falls back to a plain serial map when there is nothing to gain from threads.
    """
    if not items:
        return []
    workers = max(1, min(max_workers, len(items)))
    if workers == 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))  # ex.map preserves input order


def _compare_text(pdf_a: Path, pdf_b: Path, use_llm: bool) -> dict:
    """The text half: deterministic diff + optional LLM summary."""
    text_a = extract_text(pdf_a)
    text_b = extract_text(pdf_b)
    diff_text = compute_diff(text_a, text_b, label_a=pdf_a.name, label_b=pdf_b.name)
    section: dict = {
        "diff": diff_text,
        "changed_lines": count_changed_lines(diff_text),
        "summary": None,
    }
    if use_llm:
        from summarize import summarize_diff

        section["summary"] = summarize_diff(diff_text)
    return section


def _compare_images(
    pdf_a: Path,
    pdf_b: Path,
    work_dir: Path,
    max_pages: int,
    dpi: int,
    max_concurrency: int = DEFAULT_VISION_CONCURRENCY,
) -> dict:
    """Render both PDFs' pages and visually compare them page-by-page.

    Imported lazily inside compare() only when use_vision is True, so text-only runs
    need neither the vision model nor rendered images.
    """
    from vision import VisionError, compare_pages, describe_page

    section: dict = {
        "pages_compared": 0,
        "page_results": [],
        "extra_pages": [],
        "note": None,
        "rendered": {"a": [], "b": []},
    }

    # Count + render both documents concurrently -- four independent poppler subprocesses.
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_n_a = ex.submit(page_count, pdf_a)
        f_n_b = ex.submit(page_count, pdf_b)
        f_pages_a = ex.submit(render_pages, pdf_a, work_dir / "a", dpi=dpi, max_pages=max_pages)
        f_pages_b = ex.submit(render_pages, pdf_b, work_dir / "b", dpi=dpi, max_pages=max_pages)
        try:
            n_a = f_n_a.result()
            n_b = f_n_b.result()
            pages_a = f_pages_a.result()
            pages_b = f_pages_b.result()
        except RenderError as exc:
            section["note"] = f"Visual comparison skipped -- page rendering failed: {exc}"
            return section

    section["rendered"] = {"a": [str(p) for p in pages_a], "b": [str(p) for p in pages_b]}
    common = min(len(pages_a), len(pages_b))

    def _one_page(i: int) -> dict:
        label = f"page {i + 1}"
        try:
            return compare_pages(pages_a[i], pages_b[i], page_label=label)
        except VisionError as exc:
            return {
                "page_label": label,
                "differences": f"(visual comparison failed: {exc})",
                "identical": False,
                "tool_verified": False,
                "model": None,
            }

    section["page_results"] = _parallel_ordered(_one_page, list(range(common)), max_concurrency)
    section["pages_compared"] = common

    # Pages that exist in only one document (different page counts).
    if n_a != n_b:
        _n_longer, longer_pages, which = (n_a, pages_a, "A") if n_a > n_b else (n_b, pages_b, "B")

        def _one_extra(i: int) -> dict:
            label = f"page {i + 1}"
            try:
                desc = describe_page(longer_pages[i])
            except VisionError as exc:
                desc = f"(description failed: {exc})"
            return {"document": which, "page_label": label, "description": desc}

        section["extra_pages"] = _parallel_ordered(
            _one_extra, list(range(common, len(longer_pages))), max_concurrency
        )
        section["note"] = (
            f"Documents have different page counts (A={n_a}, B={n_b}); "
            f"{len(section['extra_pages'])} extra page(s) in document {which} described individually."
        )

    return section


def compare(
    pdf_a: str | Path,
    pdf_b: str | Path,
    *,
    use_llm: bool = True,
    use_vision: bool = True,
    max_pages: int = 3,
    dpi: int = 100,
    max_concurrency: int = DEFAULT_VISION_CONCURRENCY,
    work_dir: str | Path | None = None,
) -> dict:
    """Compare two PDFs on both text and images. See module docstring for the shape.

    - `use_llm`        : run the LLM text-summary step (needs an API key).
    - `use_vision`     : render pages and run the vision page-comparison step (needs an API key).
    - `max_pages`      : cap on how many leading pages are visually compared (rendering is the
                         slow/expensive part; text diff always covers the whole document).
    - `max_concurrency`: bound on parallel per-page vision calls (small by default; the vision
                         endpoint is usually a single local model).

    The text and image halves run concurrently; the text result is resolved first so a
    text-extraction failure surfaces with the same priority as the original serial pipeline.
    """
    pdf_a = Path(pdf_a)
    pdf_b = Path(pdf_b)

    def _text_task() -> dict:
        return _compare_text(pdf_a, pdf_b, use_llm)

    def _image_task() -> dict:
        if not use_vision:
            return {
                "pages_compared": 0,
                "page_results": [],
                "extra_pages": [],
                "note": "Visual comparison disabled (use_vision=False).",
                "rendered": {"a": [], "b": []},
            }
        if work_dir is not None:
            return _compare_images(pdf_a, pdf_b, Path(work_dir), max_pages, dpi, max_concurrency)
        with tempfile.TemporaryDirectory(prefix="contractcheck-render-") as tmp:
            section = _compare_images(pdf_a, pdf_b, Path(tmp), max_pages, dpi, max_concurrency)
            # Rendered images live in a temp dir that is about to vanish; callers that
            # need the pixels should pass an explicit work_dir. Drop the dead paths.
            section["rendered"] = {"a": [], "b": []}
            return section

    # Two independent branches over the same inputs -> run them concurrently.
    with ThreadPoolExecutor(max_workers=2) as ex:
        text_future = ex.submit(_text_task)
        image_future = ex.submit(_image_task)
        # Resolve text first: a text-extraction error should surface with the same
        # priority it had in the original sequential pipeline.
        text_section = text_future.result()
        image_section = image_future.result()

    result = {
        "doc_a": pdf_a.name,
        "doc_b": pdf_b.name,
        "text": text_section,
        "images": image_section,
    }
    result["report"] = render_compare_report(result)
    return result
