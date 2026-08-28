#!/usr/bin/env python3
"""Regenerate contract_v1.pdf / contract_v2.pdf from the .html sources.

Run manually (not part of the test suite / CI) whenever a maintainer edits
the fixture HTML. The generated PDFs are committed to the repo so the test
suite runs hermetically and offline, without depending on Chrome or fonts
being present in CI.

Usage:
    python3 fixtures/generate_fixtures.py
"""

import subprocess
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent

PAIRS = [
    ("contract_v1.html", "contract_v1.pdf"),
    ("contract_v2.html", "contract_v2.pdf"),
]


def render(html_name: str, pdf_name: str) -> None:
    html_path = FIXTURES_DIR / html_name
    pdf_path = FIXTURES_DIR / pdf_name
    cmd = [
        "google-chrome",
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        str(html_path),
    ]
    print(f"Rendering {html_name} -> {pdf_name} ...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(f"chrome failed on {html_name} (exit {result.returncode})")
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        sys.exit(f"chrome produced no output for {html_name}")
    print(f"  wrote {pdf_path} ({pdf_path.stat().st_size} bytes)")


def main() -> None:
    for html_name, pdf_name in PAIRS:
        render(html_name, pdf_name)
    print("Done. Remember to commit the regenerated PDFs.")


if __name__ == "__main__":
    main()
