"""Real PDF text extraction via the `pdftotext` CLI (poppler-utils).

Chosen over pypdf (see README) because it produces cleaner, more consistent
running-text layout across two structurally-identical PDFs, which keeps the
downstream diff free of extraction-artifact noise.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class ExtractionError(RuntimeError):
    """Raised when pdftotext fails or produces no usable text."""


def _normalize(text: str) -> str:
    """Normalize extracted text before diffing.

    This is load-bearing: applying the exact same normalization to both
    documents before diffing is what keeps the diff limited to real content
    changes instead of incidental whitespace/page-break noise.

    - split on \\n
    - rstrip() each line (trailing whitespace is not a real content change)
    - collapse runs of 2+ blank lines down to exactly 1
    """
    lines = [line.rstrip() for line in text.split("\n")]

    collapsed: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line == ""
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank

    # Drop leading/trailing blank lines produced by page breaks etc.
    while collapsed and collapsed[0] == "":
        collapsed.pop(0)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()

    return "\n".join(collapsed)


def extract_text(pdf_path: str | Path) -> str:
    """Extract normalized text from a PDF using `pdftotext -layout`.

    Raises ExtractionError if the file doesn't exist, pdftotext is missing,
    or the command fails. Deterministic: running this twice on the same file
    produces byte-identical output (no timestamps, no randomness involved).
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise ExtractionError(f"PDF not found: {pdf_path}")

    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-nopgbrk", "-enc", "UTF-8", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise ExtractionError(
            "pdftotext not found -- install poppler-utils (e.g. `apt-get install poppler-utils`)"
        ) from exc

    if result.returncode != 0:
        raise ExtractionError(
            f"pdftotext failed on {pdf_path} (exit {result.returncode}): {result.stderr.strip()}"
        )

    text = _normalize(result.stdout)
    if not text.strip():
        raise ExtractionError(
            f"No extractable text found in {pdf_path} -- this looks like a scanned/image-only "
            "PDF, which this tool doesn't OCR."
        )
    return text
