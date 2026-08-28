"""THE acceptance test.

Proves the LLM summary is grounded in the specific diff payload it is given,
not generic contract-boilerplate memorized by the model, by swapping in a
hand-written DECOY diff (fixtures/decoy_diff.txt) describing a termination-
notice change that never actually happened, and showing the summary changes
accordingly. If the model ignored the diff and just free-associated about
"a contract", both runs would read alike -- they don't.

Skipped automatically if LLM_API_KEY is not configured (e.g. budget
exhausted / no key available in this environment).
"""

from pathlib import Path

import pytest
from conftest import FIXTURES
from difftool import compute_diff
from extract import extract_text

import summarize
from summarize import summarize_diff

pytestmark = pytest.mark.skipif(
    not summarize.Config.api_key,
    reason="LLM_API_KEY not configured -- skipping live LLM grounding acceptance test",
)

OUTPUT_DIR = Path(__file__).resolve().parent / ".output"
OUTPUT_FILE = OUTPUT_DIR / "acceptance_report.md"


def _real_diff() -> str:
    text_a = extract_text(FIXTURES / "contract_v1.pdf")
    text_b = extract_text(FIXTURES / "contract_v2.pdf")
    return compute_diff(text_a, text_b, label_a="contract_v1.pdf", label_b="contract_v2.pdf")


def test_summary_is_grounded_in_the_actual_diff(capsys):
    real_diff = _real_diff()
    decoy_diff = (FIXTURES / "decoy_diff.txt").read_text()
    assert real_diff != decoy_diff  # sanity: these must be genuinely different payloads

    real_result = summarize_diff(real_diff)
    decoy_result = summarize_diff(decoy_diff)

    real_text = (real_result["summary"] + " " + " ".join(real_result["ambiguities"])).lower()
    decoy_text = (decoy_result["summary"] + " " + " ".join(decoy_result["ambiguities"])).lower()

    # --- Step 1: real-diff summary must reference the real change (30 -> 45 days payment term)
    assert "45" in real_text, f"real-diff summary did not mention the new value '45': {real_text!r}"

    # --- Step 2: decoy-diff summary must reference the decoy's change (30 -> 60 days notice)
    #     and must NOT invent the real payment-term change it was never shown.
    assert "60" in decoy_text, f"decoy-diff summary did not mention the decoy value '60': {decoy_text!r}"
    assert "45" not in decoy_text, f"decoy-diff summary hallucinated the real value '45': {decoy_text!r}"
    assert "payment" not in decoy_text, f"decoy-diff summary hallucinated 'payment' terminology: {decoy_text!r}"

    # --- Step 3: real-diff summary must NOT invent the decoy's termination-notice change.
    assert "60" not in real_text, f"real-diff summary hallucinated the decoy value '60': {real_text!r}"

    # --- Step 3b: the two summaries must genuinely diverge (falsifiable proof of grounding).
    assert real_result["summary"] != decoy_result["summary"]

    # --- Write the full proof artifact: both full diffs + both full summaries, unabridged.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = f"""# Acceptance report: LLM summary grounding

## Run 1: real tool-computed diff

### Diff (from extract_text -> compute_diff on the committed PDF fixtures)

```diff
{real_diff}
```

### LLM summary (raw response)

```
{real_result['raw_response']}
```

## Run 2: decoy diff (fixtures/decoy_diff.txt -- never produced by the tool)

### Diff

```diff
{decoy_diff}
```

### LLM summary (raw response)

```
{decoy_result['raw_response']}
```

## Verdict

- Real-diff summary mentions "45" (new payment term): {"45" in real_text}
- Real-diff summary does NOT mention "60" (decoy term): {"60" not in real_text}
- Decoy-diff summary mentions "60" (decoy term): {"60" in decoy_text}
- Decoy-diff summary does NOT mention "45" (real term): {"45" not in decoy_text}
- Decoy-diff summary does NOT mention "payment": {"payment" not in decoy_text}
- Summaries diverge: {real_result['summary'] != decoy_result['summary']}
"""
    OUTPUT_FILE.write_text(report)

    with capsys.disabled():
        print("\n" + report)
