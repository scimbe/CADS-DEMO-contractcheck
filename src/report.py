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


def render_compare_report(result: dict, out_path: str | Path | None = None) -> str:
    """Render the combined text + visual comparison report from a compare() result.

    Like render_report(), this is deliberately dumb: it shows the literal tool-computed
    diff and the model's literal visual findings, it does not paraphrase or drop them.
    """
    doc_a = result.get("doc_a", "A")
    doc_b = result.get("doc_b", "B")
    text = result.get("text", {})
    images = result.get("images", {})

    diff_text = text.get("diff", "") or ""
    diff_block = diff_text if diff_text.strip() else "(no changes -- documents are identical after normalization)"
    changed_lines = text.get("changed_lines", 0)

    summary_result = text.get("summary")
    if summary_result:
        summary = summary_result.get("summary", "")
        ambiguities = summary_result.get("ambiguities", [])
        ambiguity_block = "\n".join(f"- {a}" for a in ambiguities) if ambiguities else "- (none flagged)"
        summary_block = f"{summary}\n\n**Flagged ambiguities**\n\n{ambiguity_block}"
    else:
        summary_block = "_(LLM text summary skipped)_"

    # --- visual section ---
    page_results = images.get("page_results", [])
    extra_pages = images.get("extra_pages", [])
    note = images.get("note")

    visual_lines: list[str] = []
    if note:
        visual_lines.append(f"> {note}\n")
    if page_results:
        for pr in page_results:
            label = pr.get("page_label", "page")
            if pr.get("identical"):
                how = "byte-identical render, tool-verified" if pr.get("tool_verified") else "per vision model"
                visual_lines.append(f"### {label}\n\n- No visible differences ({how}).\n")
            else:
                visual_lines.append(f"### {label}\n\n{pr.get('differences', '').strip()}\n")
    for ep in extra_pages:
        visual_lines.append(
            f"### {ep.get('page_label', 'page')} (only in document {ep.get('document', '?')})\n\n"
            f"{ep.get('description', '').strip()}\n"
        )
    if not page_results and not extra_pages:
        visual_lines.append("_(no visual comparison performed)_")
    visual_block = "\n".join(visual_lines).strip()

    report = f"""# Document Comparison Report

**Old:** `{doc_a}`  **New:** `{doc_b}`

## Text comparison

Tool-computed changed lines: **{changed_lines}**

### Summary

{summary_block}

### Tool-computed diff

```diff
{diff_block}
```

## Visual comparison

{visual_block}
"""

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)

    return report
