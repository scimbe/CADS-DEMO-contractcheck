# CADS-DEMO-contractcheck -- Dokumenten-/Vertrags-Vergleich (Text + Bild)

A **document comparison** demo for freelancers and small businesses. You hand it **two PDFs**
(any two versions of the same document) and it answers, honestly: **"what actually changed
between these two versions -- in the wording *and* on the page -- and does anything need a
human's attention?"**

It compares on two independent axes:

- **Text** -- a deterministic `pdftotext -> difflib` diff of the extracted text, with an optional
  LLM summary of what changed.
- **Images / visual** -- each PDF's pages are rendered to images (`pdftoppm`) and compared with a
  **vision model**, which catches things a text diff is blind to: a swapped logo, a moved figure,
  a stamp or signature, a changed chart.

The core design principle holds on both axes: **the change is always tool-computed, never
LLM-eyeballed.** Deterministic code decides *what* to compare (which text lines, which page
images); the model only ever *explains* what it is handed -- it never sees the raw documents and
never gets to decide what changed. See "Proof of grounding" below for how this is verified, not
just claimed.

Single entrypoint for callers/frontends: `compare(pdf_a, pdf_b)` in `src/compare.py` returns a
structured result with a text section, an image section, and a rendered Markdown report.

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
- **Real page rendering** via `pdftoppm` (poppler-utils): each PDF page is rasterized to a PNG,
  deterministically (same PDF + same DPI -> byte-identical pixels).
- **Real vision-model comparison**: the rendered page images are sent to an OpenAI-compatible
  vision endpoint (image_url message parts) and the model reports the visual differences it can
  see. The demo uses `local-devstral-small2` for this too -- via Ollama it is multimodal and does
  genuinely read the images (see "Honest gaps" for why not `local-llava`).
- **Real synthetic PDF fixtures**, committed as binaries so the suite runs offline/hermetically:
  - `fixtures/contract_v1.pdf` / `contract_v2.pdf` -- one clause changed (Clause 4 payment term
    "30 days" -> "45 days"). The **text** fixture pair. (`fixtures/generate_fixtures.py`, Chrome.)
  - `fixtures/report_v1.pdf` / `report_v2.pdf` -- **identical text layer, different embedded
    graphic** (green square vs. red circle). The **visual** fixture pair: the text diff of these
    is empty, so they exist specifically to prove the vision step earns its keep.
    (`fixtures/generate_visual_fixtures.py`, reportlab.)
- **Real acceptance tests that prove grounding, not just plausibility** -- for both the text
  summary and the visual comparison; see below.

## How to run it

```bash
./install.sh                      # creates venv/, installs deps, writes .env (interactive)
source venv/bin/activate

# --- Full document comparison: text diff + visual (image) comparison ---
python src/pipeline.py compare --old fixtures/report_v1.pdf --new fixtures/report_v2.pdf
#   options: --report out.md  --no-llm  --no-vision  --max-pages N  --dpi N

# --- Text-only diff (original behaviour) ---
python src/pipeline.py diff --old fixtures/contract_v1.pdf --new fixtures/contract_v2.pdf
python src/pipeline.py diff --old ... --new ... --no-llm       # diff only, no API key needed
python src/pipeline.py diff --old ... --new ... --report report.md

# Run the test suite (live-LLM tests need LLM_API_KEY; auto-skip if unset)
pytest -s tests/
```

Programmatic entrypoint (what a frontend/wrapper should call):

```python
from compare import compare        # src/ on sys.path
result = compare("a.pdf", "b.pdf") # -> {"doc_a","doc_b","text","images","report"}
print(result["report"])            # combined Markdown (text + visual sections)
# result["text"]  = {"diff", "changed_lines", "summary"}
# result["images"]= {"pages_compared", "page_results":[...], "extra_pages":[...], "note"}
```

`.env` (gitignored) needs `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` (and optionally
`LLM_VISION_MODEL_NAME`) -- see `.env.example`. The `LITELLM_BASE_URL` / `LITELLM_API_KEY` /
`LITELLM_DEFAULT_MODEL` names are accepted as a fallback, and the base URL may be given with or
without a trailing `/v1`.

## Architecture

```
src/extract.py    extract_text(pdf_path) -> str            # pdftotext subprocess + normalization
src/difftool.py   compute_diff(text_a, text_b) -> str       # difflib.unified_diff, deterministic
src/render.py     render_pages / page_count                 # pdftoppm/pdfinfo, deterministic rasterize
src/vision.py     compare_pages(img_old, img_new) -> dict   # vision model explains two page images
src/summarize.py  summarize_diff(diff_text) -> dict         # LLM call, explains the diff it's given
src/llmconfig.py  LLMConfig + chat_completion()             # shared endpoint config + the one HTTP call
src/compare.py    compare(pdf_a, pdf_b) -> dict             # orchestrates text + visual, one entrypoint
src/report.py     render_report / render_compare_report     # Markdown, never paraphrases the findings
src/pipeline.py   CLI: `diff` (text) and `compare` (text + visual)
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

## Proof of grounding: the visual comparison earns its keep

The risk with "add a vision model" is that it is decorative -- that it never catches anything the
text diff didn't already have. `tests/test_vision_grounding.py` makes that falsifiable using the
`report_v1.pdf` / `report_v2.pdf` fixtures, which have an **identical text layer** but a
**different embedded graphic** (green square vs. red circle):

1. Assert the tool-computed **text diff of the two documents is empty** (0 changed lines) -- a
   text-only tool would report "no changes". (No API key needed.)
2. Feed the two rendered page images to the vision model and assert it **does** report the change
   and grounds it in the real graphic (mentions "red"/"circle"). Real output from a live run:

   > - The green square in the OLD version has been replaced with a red circle in the NEW version.

3. A **deterministic byte-identical pre-check**: when two rendered pages are byte-for-byte equal,
   `compare_pages()` returns `identical=True` **without calling the model at all** (`tool_verified:
   true`). This is what stops a local vision model from "finding" a phantom difference between two
   genuinely identical pages -- when the tool can prove the pages match, the tool decides, not the
   model. (No API key needed.)

## Test coverage

| File | What it checks |
|---|---|
| `test_extract.py` | Known literal strings extracted; extraction is deterministic (byte-identical on repeat runs); missing file raises. |
| `test_difftool.py` | Unified-diff format; identical texts diff to empty (no false positives); changed-line counting. |
| `test_render.py` | `pdfinfo` page count; `pdftoppm` renders one PNG per page; rendering is deterministic (byte-identical on repeat); missing file raises. No key needed. |
| `test_pipeline_diff_fixture.py` | Real pipeline on the real committed PDFs: diff contains the expected fragment, and has **exactly 2** changed lines -- proving the tool caught precisely the one real change and nothing else. |
| `test_summarize_grounding.py` | The text-summary acceptance test described above. Skips automatically if `LLM_API_KEY` is unset. |
| `test_vision_grounding.py` | The visual acceptance test: text diff of the visual fixtures is empty; byte-identical pages short-circuit without the model (no key); vision reports the green->red graphic change (live LLM, auto-skips without a key). |
| `test_llmconfig.py` | Env resolution (`LLM_*` / `LITELLM_*` fallback) and `/v1` base-URL normalization. No key needed. |
| `test_report.py` | Text report contains the literal diff block and literal summary text (no paraphrasing/dropping). |
| `test_report_compare.py` | Combined report shows the literal diff, literal summary, and literal visual findings; marks tool-verified identity. No key needed. |

## Known limitations / honest gaps

- **Single-clause fixture only.** The acceptance bar is proven on one clean, isolated change
  (a two-digit number in one clause). Multi-paragraph rewrites, reordered clauses, or heavier
  table/column layouts have not been tested and would likely produce noisier diffs (pdftotext's
  `-layout` mode reproduces visual line-wrapping, so a reflowed paragraph can show as many changed
  lines even when the actual textual edit is small). A real product would want word-level or
  sentence-level diffing on top of the line-level diff for that case.
- **Vision model: `local-llava` was intended but is not reachable with this key.** The endpoint's
  key is scoped to exactly one model (`local-devstral-small2`); a call to `local-llava` returns
  `403 key_model_access_denied`. What is used instead is `local-devstral-small2` itself, which
  (served via Ollama) accepts OpenAI-style `image_url` parts and genuinely reads the images -- it
  correctly reported the green-square -> red-circle change in the visual fixture. The vision model
  is configurable via `LLM_VISION_MODEL_NAME`, so pointing it at a dedicated VLM later is a
  one-line env change, no code change.
- **The visual comparison is best-effort, not authoritative.** A local vision model can get fine
  details (exact shades, small text inside a graphic) wrong, and can *over-report* -- "finding" a
  difference between two near-identical pages. Two guards limit this: the byte-identical
  pre-check resolves provably-equal pages without the model, and the prompt instructs the model to
  ground every point in what is visible and to emit a fixed "no differences" sentinel. Near-identical
  (visually equal but not byte-equal) pages can still draw a spurious bullet -- treat the visual
  section as a descriptive lead for a human, not a verdict.
- **Pages are paired by index (page 1 vs page 1, ...).** Inserted, deleted, or reordered pages
  would misalign the visual comparison; only differing page *counts* are handled (extra pages are
  described individually). Content-based page alignment is out of scope for this slice.
- **Only the first `--max-pages` pages are compared visually** (default 3). Rendering + a vision
  call per page is the slow/expensive part; the *text* diff always covers the whole document.
- **No OCR.** Scanned/image-only PDFs raise `ExtractionError` in the text step rather than silently
  producing nothing -- the text comparison only handles PDFs with a real text layer. (The visual
  comparison itself works on any renderable PDF.)
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

All fixture PDFs are committed and should normally not need regenerating. The two generators are
manual, fixture-only tools (their dependencies are **not** runtime dependencies of the tool):

```bash
# text fixtures (contract_v1/v2.pdf) -- edit contract_v1.html / contract_v2.html first
python3 fixtures/generate_fixtures.py          # requires google-chrome; not run in CI

# visual fixtures (report_v1/v2.pdf) -- identical text, different graphic
python3 fixtures/generate_visual_fixtures.py   # requires reportlab (BSD); not run in CI
```

Commit the regenerated PDFs alongside any source change.
