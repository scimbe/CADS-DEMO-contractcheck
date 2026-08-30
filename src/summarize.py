"""LLM summarization of a tool-computed diff.

The LLM's ONLY job here is to explain a diff it is handed -- it never sees
the two full documents and never computes the diff itself. This module is
what the acceptance test (tests/test_summarize_grounding.py) uses to prove
the summary is grounded in the actual diff payload, not generic contract
boilerplate memorized by the model.
"""

from __future__ import annotations

import json

from llmconfig import LLMConfig as Config  # noqa: F401  (re-exported: tests use summarize.Config)
from llmconfig import LLMError, chat_completion

SYSTEM_PROMPT = """You are a contract-review assistant. You will be given a unified diff
(the "@@ / -old / +new" format produced by a real text-diff tool) between two
versions of a legal/business document. The diff was computed mechanically --
it is the ground truth of exactly what changed, and you have not seen the
rest of the document.

Your job:
1. Summarize in plain language what changed, in at most 3 sentences.
2. List any genuine ambiguities a reader should double-check (e.g. unclear
   scope of a changed term, missing context, a change that could be read two
   ways). If there are none, return an empty list.

Base your answer ONLY on the diff you are given. Do not invent changes that
are not in the diff, and do not describe the document's unchanged content.

Respond with ONLY a JSON object, no markdown fences, no other text, in
exactly this shape:
{"summary": "...", "ambiguities": ["...", "..."]}
"""


class SummarizeError(RuntimeError):
    pass


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _call_llm(messages: list[dict], model: str | None) -> str:
    try:
        return chat_completion(messages, model=model or Config.text_model, max_tokens=800)
    except LLMError as exc:
        raise SummarizeError(str(exc)) from exc


def summarize_diff(diff_text: str, model: str | None = None, retries: int = 1) -> dict:
    """Call the LLM to summarize a unified diff. Returns:

        {"summary": str, "ambiguities": list[str], "raw_response": str}

    raw_response is the model's unparsed text -- kept so callers/tests can
    show exactly what came back, for auditability.

    Local models don't always emit strictly valid JSON on the first try --
    on a parse failure this asks the model once (by default) to fix its own
    output before giving up, same pattern as the sibling CADS-Demo-local-pdf-tools.
    """
    Config.validate()

    if not diff_text.strip():
        return {"summary": "No changes detected between the two documents.", "ambiguities": [], "raw_response": ""}

    user_prompt = f"Here is the diff to summarize:\n\n```diff\n{diff_text}\n```"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw_text = _call_llm(messages, model)

    for attempt in range(retries + 1):
        cleaned = _strip_code_fence(raw_text)
        try:
            parsed = json.loads(cleaned)
            return {
                "summary": parsed.get("summary", ""),
                "ambiguities": parsed.get("ambiguities", []),
                "raw_response": raw_text,
            }
        except json.JSONDecodeError:
            if attempt >= retries:
                raise SummarizeError(f"LLM did not return valid JSON after {retries + 1} attempt(s): {raw_text!r}")
            messages = messages + [
                {"role": "assistant", "content": raw_text},
                {
                    "role": "user",
                    "content": "Your previous response was not valid JSON. Return ONLY the JSON object, "
                    "no markdown fences, no other text.",
                },
            ]
            raw_text = _call_llm(messages, model)

    raise AssertionError("unreachable")
