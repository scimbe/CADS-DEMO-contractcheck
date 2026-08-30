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
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from difftool import compute_diff, count_changed_lines
from extract import extract_text
from render import RenderError, page_count, render_pages
from report import render_compare_report


def _compare_images(pdf_a: Path, pdf_b: Path, work_dir: Path, max_pages: int, dpi: int) -> dict:
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

    try:
        n_a = page_count(pdf_a)
        n_b = page_count(pdf_b)
        pages_a = render_pages(pdf_a, work_dir / "a", dpi=dpi, max_pages=max_pages)
        pages_b = render_pages(pdf_b, work_dir / "b", dpi=dpi, max_pages=max_pages)
    except RenderError as exc:
        section["note"] = f"Visual comparison skipped -- page rendering failed: {exc}"
        return section

    section["rendered"] = {"a": [str(p) for p in pages_a], "b": [str(p) for p in pages_b]}

    common = min(len(pages_a), len(pages_b))
    for i in range(common):
        label = f"page {i + 1}"
        try:
            section["page_results"].append(compare_pages(pages_a[i], pages_b[i], page_label=label))
        except VisionError as exc:
            section["page_results"].append(
                {"page_label": label, "differences": f"(visual comparison failed: {exc})",
                 "identical": False, "model": None}
            )
    section["pages_compared"] = common

    # Pages that exist in only one document (different page counts).
    if n_a != n_b:
        longer, longer_pages, which = (
            (n_a, pages_a, "A") if n_a > n_b else (n_b, pages_b, "B")
        )
        for i in range(common, len(longer_pages)):
            label = f"page {i + 1}"
            try:
                desc = describe_page(longer_pages[i])
            except VisionError as exc:
                desc = f"(description failed: {exc})"
            section["extra_pages"].append({"document": which, "page_label": label, "description": desc})
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
    work_dir: str | Path | None = None,
) -> dict:
    """Compare two PDFs on both text and images. See module docstring for the shape.

    - `use_llm`   : run the LLM text-summary step (needs an API key).
    - `use_vision`: render pages and run the vision page-comparison step (needs an API key).
    - `max_pages` : cap on how many leading pages are visually compared (rendering is the
                    slow/expensive part; text diff always covers the whole document).
    """
    pdf_a = Path(pdf_a)
    pdf_b = Path(pdf_b)

    # ---- text half (deterministic diff, optional LLM summary) ----
    text_a = extract_text(pdf_a)
    text_b = extract_text(pdf_b)
    diff_text = compute_diff(text_a, text_b, label_a=pdf_a.name, label_b=pdf_b.name)
    text_section: dict = {
        "diff": diff_text,
        "changed_lines": count_changed_lines(diff_text),
        "summary": None,
    }
    if use_llm:
        from summarize import summarize_diff

        text_section["summary"] = summarize_diff(diff_text)

    # ---- image half (deterministic render, vision-model comparison) ----
    image_section: dict = {
        "pages_compared": 0,
        "page_results": [],
        "extra_pages": [],
        "note": "Visual comparison disabled (use_vision=False)." if not use_vision else None,
        "rendered": {"a": [], "b": []},
    }
    if use_vision:
        if work_dir is not None:
            image_section = _compare_images(pdf_a, pdf_b, Path(work_dir), max_pages, dpi)
        else:
            with tempfile.TemporaryDirectory(prefix="contractcheck-render-") as tmp:
                image_section = _compare_images(pdf_a, pdf_b, Path(tmp), max_pages, dpi)
                # Rendered images live in a temp dir that is about to vanish; callers that
                # need the pixels should pass an explicit work_dir. Drop the dead paths.
                image_section["rendered"] = {"a": [], "b": []}

    result = {
        "doc_a": pdf_a.name,
        "doc_b": pdf_b.name,
        "text": text_section,
        "images": image_section,
    }
    result["report"] = render_compare_report(result)
    return result
