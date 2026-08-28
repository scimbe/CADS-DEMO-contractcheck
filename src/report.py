"""Render a Markdown report combining the tool-computed diff and the LLM summary.

Deliberately dumb: it must not paraphrase or drop the underlying diff --
the whole point of the demo is that the diff shown in the report is the
literal, verifiable output of compute_diff(), not something reconstructed
from the LLM's account of it.
"""

from __future__ import annotations

from pathlib import Path


def render_report(diff_text: str, summary_result: dict, out_path: str | Path | None = None) -> str:
    """Build the Markdown report. Optionally write it to out_path.

    summary_result is the dict returned by summarize.summarize_diff():
    {"summary": str, "ambiguities": list[str], "raw_response": str}
    """
    summary = summary_result.get("summary", "")
    ambiguities = summary_result.get("ambiguities", [])

    ambiguity_block = (
        "\n".join(f"- {a}" for a in ambiguities) if ambiguities else "- (none flagged)"
    )
    diff_block = diff_text if diff_text.strip() else "(no changes -- documents are identical after normalization)"

    report = f"""# Contract Diff Report

## Tool-computed diff

```diff
{diff_block}
```

## LLM summary

{summary}

## Flagged ambiguities

{ambiguity_block}
"""

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)

    return report
