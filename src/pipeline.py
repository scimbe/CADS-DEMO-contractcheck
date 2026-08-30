#!/usr/bin/env python3
"""CLI entrypoint.

Usage:
    # text-only diff of two PDFs (original behaviour)
    python src/pipeline.py diff --old v1.pdf --new v2.pdf [--report out.md] [--no-llm]

    # full document comparison: text diff + visual (image) comparison
    python src/pipeline.py compare --old v1.pdf --new v2.pdf [--report out.md]
                                   [--no-llm] [--no-vision] [--max-pages N] [--dpi N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from difftool import compute_diff  # noqa: E402
from extract import extract_text  # noqa: E402
from report import render_report  # noqa: E402


def run_diff(old_pdf: Path, new_pdf: Path, use_llm: bool = True) -> tuple[str, dict | None]:
    """Runs the real extract -> diff pipeline, and optionally the LLM summary.

    Returns (diff_text, summary_result_or_None).
    """
    text_a = extract_text(old_pdf)
    text_b = extract_text(new_pdf)
    diff_text = compute_diff(text_a, text_b, label_a=old_pdf.name, label_b=new_pdf.name)

    summary_result = None
    if use_llm:
        from summarize import summarize_diff  # imported lazily so --no-llm needs no LLM config

        summary_result = summarize_diff(diff_text)

    return diff_text, summary_result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    diff_cmd = sub.add_parser("diff", help="Diff two PDF versions of a document (text only)")
    diff_cmd.add_argument("--old", required=True, type=Path, help="Path to the older PDF version")
    diff_cmd.add_argument("--new", required=True, type=Path, help="Path to the newer PDF version")
    diff_cmd.add_argument("--report", type=Path, help="Write a Markdown report here")
    diff_cmd.add_argument("--no-llm", action="store_true", help="Skip the LLM summarization step")

    cmp_cmd = sub.add_parser("compare", help="Compare two PDFs on both text and images")
    cmp_cmd.add_argument("--old", required=True, type=Path, help="Path to the older/first PDF")
    cmp_cmd.add_argument("--new", required=True, type=Path, help="Path to the newer/second PDF")
    cmp_cmd.add_argument("--report", type=Path, help="Write the combined Markdown report here")
    cmp_cmd.add_argument("--no-llm", action="store_true", help="Skip the LLM text-summary step")
    cmp_cmd.add_argument("--no-vision", action="store_true", help="Skip the visual (image) comparison step")
    cmp_cmd.add_argument("--max-pages", type=int, default=3, help="Max leading pages to compare visually (default 3)")
    cmp_cmd.add_argument("--dpi", type=int, default=100, help="Render DPI for the visual comparison (default 100)")
    cmp_cmd.add_argument("--concurrency", type=int, default=3, help="Max parallel per-page vision calls (default 3)")

    args = parser.parse_args()

    if args.command == "compare":
        from compare import compare  # lazy: keeps `diff` working without render/vision imports

        result = compare(
            args.old,
            args.new,
            use_llm=not args.no_llm,
            use_vision=not args.no_vision,
            max_pages=args.max_pages,
            dpi=args.dpi,
            max_concurrency=args.concurrency,
        )
        print(result["report"])
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(result["report"])
            print(f"\nWrote report to {args.report}")
        return

    if args.command == "diff":
        diff_text, summary_result = run_diff(args.old, args.new, use_llm=not args.no_llm)

        print("=== Tool-computed diff ===")
        print(diff_text if diff_text.strip() else "(no changes)")

        if summary_result is not None:
            print("\n=== LLM summary ===")
            print(summary_result["summary"])
            if summary_result["ambiguities"]:
                print("\nFlagged ambiguities:")
                for a in summary_result["ambiguities"]:
                    print(f"  - {a}")

        if args.report:
            render_report(diff_text, summary_result or {"summary": "", "ambiguities": []}, out_path=args.report)
            print(f"\nWrote report to {args.report}")


if __name__ == "__main__":
    main()
