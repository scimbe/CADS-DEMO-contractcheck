"""Best-effort VISUAL comparison of two rendered PDF pages, via an OpenAI-compatible
vision model (image_url message parts) on the same litellm-proxy endpoint as the
text summarizer.

Discipline, mirroring the text pipeline:
  * The *tool* (`render.py`) decides which pages exist and pairs them by page index.
  * The *model* only ever receives the page IMAGES and is asked to report the visual
    differences it can actually see -- layout, embedded images/figures, tables,
    stamps/signatures, colors, headings. It is explicitly told not to invent content.

This complements, and does not replace, the text diff: text catches the wording
changes; vision catches things a text diff is blind to (a swapped logo, a moved
figure, a signature block, a scanned stamp).
"""

from __future__ import annotations

import base64
from pathlib import Path

from llmconfig import LLMConfig, LLMError, chat_completion

# The literal sentinel the model is told to emit when the pages look the same.
NO_DIFF_SENTINEL = "NO VISIBLE DIFFERENCES"

VISION_SYSTEM_PROMPT = f"""You compare two rendered pages from two versions of the same
document. You are given two images: Image 1 is the OLD version's page, Image 2 is the
NEW version's page.

Report ONLY the concrete visual differences you can actually see between the two images
-- for example: changed or moved text blocks, added/removed/replaced images or logos,
table/layout changes, stamps or signatures, headings, or clear color/formatting changes.

Rules:
- Ground every point in what is visible. Do NOT invent text, numbers, or figures that
  are not present in the images.
- If you are unsure about something, say you are unsure rather than guessing.
- If the two pages look visually the same, respond with EXACTLY this line and nothing
  else: {NO_DIFF_SENTINEL}
- Otherwise respond with at most 5 short bullet points, one difference per bullet."""


class VisionError(RuntimeError):
    pass


def _data_uri(image_path: str | Path) -> str:
    image_path = Path(image_path)
    if not image_path.is_file():
        raise VisionError(f"image not found: {image_path}")
    encoded = base64.b64encode(image_path.read_bytes()).decode()
    return f"data:image/png;base64,{encoded}"


def compare_pages(
    img_old: str | Path,
    img_new: str | Path,
    *,
    page_label: str = "page",
    model: str | None = None,
) -> dict:
    """Compare one OLD page image against one NEW page image.

    Returns:
        {"page_label": str, "differences": str, "identical": bool, "model": str}

    `identical` is True when the model reports the NO_VISIBLE_DIFFERENCES sentinel.
    Raises VisionError on an LLM transport/response error.
    """
    old_bytes = Path(img_old).read_bytes()
    new_bytes = Path(img_new).read_bytes()

    # Deterministic pre-check: if the two rendered pages are byte-identical there is
    # nothing to compare, and -- crucially -- we do NOT ask the model, because a local
    # vision model can over-report and "find" a difference between two identical images.
    # When the tool can prove the pages match, the tool decides, not the model.
    if old_bytes == new_bytes:
        return {
            "page_label": page_label,
            "differences": "Pages are byte-identical after rendering -- no visual difference.",
            "identical": True,
            "tool_verified": True,
            "model": None,
        }

    LLMConfig.validate()
    used_model = model or LLMConfig.vision_model

    user_content = [
        {
            "type": "text",
            "text": (
                f"These two images are the same {page_label} in two document versions. "
                "Image 1 = OLD, Image 2 = NEW. List the concrete visual differences you can see."
            ),
        },
        {"type": "image_url", "image_url": {"url": _data_uri(img_old)}},
        {"type": "image_url", "image_url": {"url": _data_uri(img_new)}},
    ]
    messages = [
        {"role": "system", "content": VISION_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        text = chat_completion(messages, model=used_model, max_tokens=400)
    except LLMError as exc:
        raise VisionError(str(exc)) from exc

    identical = NO_DIFF_SENTINEL in text.upper()
    return {
        "page_label": page_label,
        "differences": text.strip(),
        "identical": identical,
        "tool_verified": False,
        "model": used_model,
    }


def describe_page(img: str | Path, *, model: str | None = None) -> str:
    """Describe a single page image (used for pages that only exist in one document)."""
    LLMConfig.validate()
    used_model = model or LLMConfig.vision_model
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Describe what is visible on this document page in at most 3 short "
                    "bullet points. Ground it in what you see; do not invent content.",
                },
                {"type": "image_url", "image_url": {"url": _data_uri(img)}},
            ],
        }
    ]
    try:
        return chat_completion(messages, model=used_model, max_tokens=250).strip()
    except LLMError as exc:
        raise VisionError(str(exc)) from exc
