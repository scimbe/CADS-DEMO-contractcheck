"""Rasterize PDF pages to PNG images via `pdftoppm`, and count pages via `pdfinfo`
(both from poppler-utils, the same toolchain `extract.py` already relies on).

This is the deterministic, tool-computed half of the *visual* comparison: the code
decides which pages exist and renders them; the vision model (see `vision.py`) only
ever gets the resulting images and is asked to describe what it sees. Rendering is
reproducible -- the same PDF at the same DPI produces the same pixels.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class RenderError(RuntimeError):
    """Raised when pdfinfo/pdftoppm are missing or fail."""


def page_count(pdf_path: str | Path) -> int:
    """Number of pages in the PDF, via `pdfinfo`."""
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise RenderError(f"PDF not found: {pdf_path}")

    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)], capture_output=True, text=True, timeout=30
        )
    except FileNotFoundError as exc:
        raise RenderError(
            "pdfinfo not found -- install poppler-utils (e.g. `apt-get install poppler-utils`)"
        ) from exc

    if result.returncode != 0:
        raise RenderError(f"pdfinfo failed on {pdf_path} (exit {result.returncode}): {result.stderr.strip()}")

    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RenderError(f"could not determine page count for {pdf_path}")


def _page_number(png_path: Path) -> int:
    """pdftoppm names pages `<prefix>-<n>.png` (zero-padded for 10+ pages)."""
    return int(png_path.stem.rsplit("-", 1)[-1])


def render_pages(
    pdf_path: str | Path,
    out_dir: str | Path,
    *,
    dpi: int = 100,
    max_pages: int | None = None,
) -> list[Path]:
    """Render the PDF's pages to PNGs in `out_dir`, one file per page.

    Returns the PNG paths in page order. `max_pages` limits how many leading
    pages are rendered (None = all). Raises RenderError if pdftoppm is missing,
    fails, or produces no output.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise RenderError(f"PDF not found: {pdf_path}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / pdf_path.stem

    cmd = ["pdftoppm", "-png", "-r", str(dpi)]
    if max_pages is not None:
        cmd += ["-f", "1", "-l", str(max_pages)]
    cmd += [str(pdf_path), str(prefix)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise RenderError(
            "pdftoppm not found -- install poppler-utils (e.g. `apt-get install poppler-utils`)"
        ) from exc

    if result.returncode != 0:
        raise RenderError(f"pdftoppm failed on {pdf_path} (exit {result.returncode}): {result.stderr.strip()}")

    pages = sorted(out_dir.glob(f"{pdf_path.stem}-*.png"), key=_page_number)
    if not pages:
        raise RenderError(f"pdftoppm produced no page images for {pdf_path}")
    return pages
