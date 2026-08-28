"""Deterministic, tool-computed text diffing via Python stdlib difflib.

This is the ground truth of the whole demo: the diff is computed here, by
code, never by an LLM "eyeballing" two texts. The LLM only ever sees the
output of compute_diff() and is asked to explain it -- it never gets to
decide what changed.
"""

from __future__ import annotations

import difflib


def compute_diff(text_a: str, text_b: str, label_a: str = "old", label_b: str = "new") -> str:
    """Unified diff between two texts, computed by difflib (not an LLM).

    Returns "" (empty string) if the two texts are identical -- callers can
    use that as a reliable "no changes" signal.
    """
    lines_a = text_a.split("\n")
    lines_b = text_b.split("\n")
    diff_lines = difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b, lineterm="")
    return "\n".join(diff_lines)


def count_changed_lines(diff_text: str) -> int:
    """Count content changed lines (+/-) in a unified diff, excluding the
    ---/+++ file headers and @@ hunk headers."""
    count = 0
    for line in diff_text.split("\n"):
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+") or line.startswith("-"):
            count += 1
    return count
