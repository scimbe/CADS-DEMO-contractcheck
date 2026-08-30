#!/usr/bin/env python3
"""Regenerate the VISUAL fixture pair: report_v1.pdf / report_v2.pdf.

These two PDFs have an IDENTICAL text layer but a DIFFERENT embedded graphic:
report_v1 carries a green square "stamp", report_v2 a red circle. This is the
point of the visual half of the demo -- a pure text diff of these two documents
is empty (`pdftotext` yields the same text for both), yet the documents clearly
differ, and the vision comparison catches exactly what the text diff is blind to.

Run manually (not part of the test suite / CI), like generate_fixtures.py. The
generated PDFs are committed so the suite stays hermetic. Requires reportlab
(a manual, fixture-only dependency -- NOT a runtime dependency of the tool):

    pip install reportlab
    python3 fixtures/generate_visual_fixtures.py

reportlab is BSD-licensed (open source).
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

FIXTURES_DIR = Path(__file__).resolve().parent

# Identical on both pages -> the text layer, and therefore the text diff, is the same.
TITLE = "Quarterly Compliance Report"
PARAGRAPH = [
    "This document certifies the review status of the attached record.",
    "All figures were verified against the source system on the review date.",
    "The status stamp below indicates the outcome of the review.",
]
FOOTER = "Reference: QCR-2026-Q3    Reviewer: J. Doe"


def _draw_text_layer(c: canvas.Canvas) -> None:
    c.setFont("Helvetica-Bold", 18)
    c.drawString(1 * inch, 10 * inch, TITLE)
    c.setFont("Helvetica", 12)
    y = 9.3 * inch
    for line in PARAGRAPH:
        c.drawString(1 * inch, y, line)
        y -= 0.3 * inch
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(1 * inch, 1 * inch, FOOTER)


def build_v1(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    _draw_text_layer(c)
    # Green SQUARE stamp (no text inside it -> stays out of the text layer).
    c.setFillColorRGB(0.13, 0.60, 0.20)
    c.rect(3 * inch, 4.5 * inch, 2.2 * inch, 2.2 * inch, fill=1, stroke=0)
    c.save()


def build_v2(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    _draw_text_layer(c)
    # Red CIRCLE stamp in the same region -> only the graphic differs.
    c.setFillColorRGB(0.80, 0.13, 0.13)
    c.circle(4.1 * inch, 5.6 * inch, 1.15 * inch, fill=1, stroke=0)
    c.save()


def main() -> None:
    build_v1(FIXTURES_DIR / "report_v1.pdf")
    build_v2(FIXTURES_DIR / "report_v2.pdf")
    print("Wrote report_v1.pdf and report_v2.pdf. Remember to commit them.")


if __name__ == "__main__":
    main()
