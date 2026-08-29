# CADS-DEMO-contractcheck -- Vertrags-/Dokumenten-Checker

A document/contract-diff demo for freelancers and small businesses. It answers one question
honestly: **"what actually changed between these two versions of a contract, and does anything
in the change need a human's attention?"**

The core design principle: **the diff is always tool-computed, never LLM-eyeballed.** A
deterministic pipeline (`pdftotext` -> Python `difflib`) finds the changes. The LLM's only job is
to explain a diff it is handed after the fact -- it never sees the raw documents and never gets to
decide what changed. See "Proof of grounding" below for how this is verified, not just claimed.

Tracking issue: [CADS-agent-marketplace#29](https://github.com/scimbe/CADS-agent-marketplace/issues/29).

## Marketplace status

This demo is published to the live **bunsenbrenner.org** registry
(`registry.bunsenbrenner.org`) as a signed manifest. Verified present on 2026-08-29:

- name `contractcheck`, latest version `0.1.1`, `installer_kind: binary`
- publisher pubkey `1292c0cc…ce69b` (shared across the whole demo portfolio)
- manifest id `4b4e7ade…171a`

Reproduce the check yourself:

```bash
curl -s https://registry.bunsenbrenner.org/manifests | grep '"name":"contractcheck"'
```

**Measured vs. claimed:** what is *measured* here is that the manifest — signed metadata
plus a publisher-signed bundle reference — is listed on the registry. The registry's own
guardrail verdict for a binary-kind manifest explicitly notes it is **not** a static bundle
scan; trust rests on the publisher-pubkey allowlist checked at activation time. It is **not**
a claim that an always-on hosted `*.bunsenbrenner.org` service exists — this is a CLI-only
tool, and live tunnel/service deployment remains a separate, later step.

## What's real here

- **Real PDF text extraction** via the `pdftotext` CLI (poppler-utils), not a stub.
- **Real, deterministic diffing** via Python stdlib `difflib.unified_diff` on the extracted text.
- **Real synthetic PDF fixtures**: `fixtures/contract_v1.pdf` / `contract_v2.pdf`, generated from
  hand-written HTML via headless Chrome (`fixtures/generate_fixtures.py`), with exactly one clause
  changed (Clause 4's payment term: "30 days" -> "45 days"). These are committed binaries so the
  test suite runs offline/hermetically.
- **Real LLM calls** against a live litellm-proxy endpoint (OpenAI-compatible
  `/chat/completions`), `temperature=0`, to a local model (`local-devstral-small2`).
- **A real acceptance test that proves grounding, not just plausibility** -- see below.

## How to run it

```bash
./install.sh                      # creates venv/, installs deps, writes .env (interactive)
source venv/bin/activate

# CLI: diff two PDFs and get an LLM summary
python src/pipeline.py diff --old fixtures/contract_v1.pdf --new fixtures/contract_v2.pdf

# ... or skip the LLM call (diff only, no API key needed)
python src/pipeline.py diff --old fixtures/contract_v1.pdf --new fixtures/contract_v2.pdf --no-llm

# ... or write a Markdown report
python src/pipeline.py diff --old fixtures/contract_v1.pdf --new fixtures/contract_v2.pdf --report report.md

# Run the test suite (the summarize-grounding test needs LLM_API_KEY; auto-skips if unset)
pytest -s tests/
```

`.env` (gitignored) needs `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` -- see `.env.example`.

## Architecture

```
src/extract.py    extract_text(pdf_path) -> str          # pdftotext subprocess + normalization
src/difftool.py   compute_diff(text_a, text_b) -> str     # difflib.unified_diff, deterministic
src/summarize.py  summarize_diff(diff_text) -> dict       # LLM call, explains the diff it's given
src/report.py     render_report(diff_text, summary) -> str  # Markdown, never paraphrases the diff
src/pipeline.py   CLI: extract -> diff -> summarize -> report
```

Normalization (`extract.py`) is applied identically to both documents before diffing: rstrip each
line, collapse blank-line runs, drop leading/trailing blanks. This keeps the diff limited to real
content changes instead of incidental whitespace/page-break noise from PDF extraction.

## Proof of grounding: the decoy-diff test

The risk with "LLM summarizes a contract diff" demos is that the model just free-associates about
contracts in general, ignoring the actual diff -- which would look identical for any change and
would be undetectable from a single successful-looking run. `tests/test_summarize_grounding.py`
makes this falsifiable:

1. Run the **real** pipeline (extract -> diff) on the committed PDF fixtures. Feed the real diff to
   the LLM. Assert the summary mentions "45" (the real new payment-term value).
2. Feed the **exact same LLM** a hand-written **decoy diff**
   (`fixtures/decoy_diff.txt`) describing a *different, fabricated* change (a termination-notice
   period extended from 30 to 60 days) that never happened to these documents and was never
   produced by the tool. Assert the summary mentions "60" (the decoy value), and critically,
   does **not** mention "45" or "payment" -- terms it would only produce by inventing content
   instead of reading the diff it was given.
3. Assert the two summaries genuinely diverge.
4. Both full diffs and both full LLM responses are written to `tests/.output/acceptance_report.md`
   (gitignored, regenerated per run) as the literal artifact of the run.

If the model ignored the diff payload, both runs would read alike. They don't -- see the real
output pasted in the report this repo's implementer filed against the tracking issue.

## Test coverage

| File | What it checks |
|---|---|
| `test_extract.py` | Known literal strings extracted; extraction is deterministic (byte-identical on repeat runs); missing file raises. |
| `test_difftool.py` | Unified-diff format; identical texts diff to empty (no false positives); changed-line counting. |
| `test_pipeline_diff_fixture.py` | Real pipeline on the real committed PDFs: diff contains the expected fragment, and has **exactly 2** changed lines -- proving the tool caught precisely the one real change and nothing else. |
| `test_summarize_grounding.py` | The acceptance test described above. Skips automatically if `LLM_API_KEY` is unset. |
| `test_report.py` | Report contains the literal diff block and literal summary text (no paraphrasing/dropping). |

## Known limitations / honest gaps

- **Single-clause fixture only.** The acceptance bar is proven on one clean, isolated change
  (a two-digit number in one clause). Multi-paragraph rewrites, reordered clauses, or heavier
  table/column layouts have not been tested and would likely produce noisier diffs (pdftotext's
  `-layout` mode reproduces visual line-wrapping, so a reflowed paragraph can show as many changed
  lines even when the actual textual edit is small). A real product would want word-level or
  sentence-level diffing on top of the line-level diff for that case.
- **No OCR.** Scanned/image-only PDFs raise `ExtractionError` rather than silently producing
  nothing -- this tool only handles PDFs with a real text layer.
- **`pdftotext` chosen over `pypdf`** specifically because it was already installed system-wide in
  this environment and gave more consistent running-text layout in a smoke test, which reduces diff
  noise between structurally-identical documents. This is an environment-dependent choice: a
  container image would need `poppler-utils` installed (`apt-get install poppler-utils`).
- **Signed manifest now published; live hosted service still out of scope.** A signed
  marketplace manifest for this demo is now on the live registry (see "Marketplace status"
  above) — this supersedes an earlier note in this README that said no manifest existed yet.
  What remains out of scope for this round is a hosted, always-on public subdomain/tunnel:
  this repo's acceptance bar is still a provable local/CI pipeline, not a running service.
- **JSON-parsing robustness:** the LLM is asked to return strict JSON and this generally works with
  `local-devstral-small2` at `temperature=0` (verified across multiple real runs during
  development), but local models occasionally wrap JSON in a markdown code fence or add stray text.
  `summarize_diff()` strips code fences and does one automatic retry (asking the model to re-emit
  valid JSON) before raising `SummarizeError` -- this is a real, tested fallback, not a hope.
- **No CI workflow yet** (e.g. GitHub Actions running `pytest` on push). The tests are hermetic
  (fixtures are committed binaries, LLM test auto-skips without a key) so this would be a small
  addition, just not done in this first slice.

## Fixture regeneration

`fixtures/contract_v1.pdf` / `contract_v2.pdf` are committed and should normally not need
regenerating. If you edit the source HTML (`fixtures/contract_v1.html` / `contract_v2.html`),
regenerate with:

```bash
python3 fixtures/generate_fixtures.py   # requires google-chrome; not run in CI
```

and commit the resulting PDFs alongside the HTML change.
