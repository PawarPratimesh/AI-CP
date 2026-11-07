"""Server-side LLM client for structured commitment extraction and comparison.

Supported providers (set LLM_PROVIDER in .env):
  openai  — OpenAI API (default)
  gemini  — Google Gemini via the officially supported OpenAI-compatible endpoint
             https://generativelanguage.googleapis.com/v1beta/openai/
             No additional SDK is required; the existing openai package is reused.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")

# ---------------------------------------------------------------------------
# Prompts — unchanged from Step 2/3; provider-agnostic plain text
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You extract explicit ESG policy commitments from a document chunk.

Return JSON only, with this shape:
{
  "commitments": [
    {
      "commitment_id": string or null,
      "category": string or null,
      "policy_statement": string or null,
      "metric": string or null,
      "baseline": string or null,
      "target": string or null,
      "deadline": string or null,
      "responsible_owner": string or null,
      "scope": string or null,
      "evidence_requirement": string or null,
      "monitoring_frequency": string or null,
      "escalation": string or null,
      "source": {
        "page_numbers": [integers from the chunk],
        "evidence": "short exact quote from the chunk"
      },
      "confidence": number between 0 and 1
    }
  ]
}

What counts as a commitment:
- Explicit language such as shall, will, commits to, committed to, target, objective, aims to, must, required to.
- Structured records that include fields such as COMMITMENT ID, CATEGORY, POLICY STATEMENT, METRIC, BASELINE, TARGET, DEADLINE, RESPONSIBLE OWNER, SCOPE, EVIDENCE REQUIREMENT, MONITORING FREQUENCY, ESCALATION.
- A structured record is ONE commitment even if it has many fields.

Rules:
1. Extract facts only. Do not invent missing values. Use null when a field is not explicitly stated.
2. Preserve exact numbers, percentages, dates, units, targets, and commitment IDs.
3. Do not infer missing targets, deadlines, or owners.
4. Do not turn vague statements into numerical commitments.
5. Do not create commitments from titles, headers, footers, or table-of-contents entries unless they contain an actual commitment.
6. Ignore repeated page headers and footers.
7. Keep policy_statement faithful to the source. Do not rewrite meaning.
8. Include source page number(s) from the chunk metadata.
9. Include a short exact evidence passage.
10. If you are uncertain it is a real commitment, omit it.
11. If no commitment ID is present, set commitment_id to null. Do not invent IDs.
12. confidence is extraction confidence only, not risk or importance.
"""

COMPARISON_PROMPT = """You compare ONE old ESG commitment with ONE new ESG commitment.

Return JSON only:
{
  "classification": "STRENGTHENED" | "WEAKENED" | "UNCHANGED" | "MODIFIED",
  "reason": "Short factual explanation of what changed.",
  "changed_fields": ["target"],
  "confidence": 0.0
}

Rules:
- Use only the supplied old/new fields. Do not invent facts.
- Do not calculate risk or ESG scores. Do not give recommendations.
- Formatting or equivalent wording is UNCHANGED.
- STRENGTHENED: more ambitious target, earlier deadline, wider scope, stronger evidence, more frequent monitoring, more binding language.
- WEAKENED: less ambitious target, later deadline, narrower scope, weaker evidence, less frequent monitoring, less binding language.
- MODIFIED: the commitment changed materially but the supplied fields do not support a defensible stronger/weaker conclusion.
- Confidence is between 0 and 1.
"""


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class LLMClientError(Exception):
    """Raised when the LLM cannot be used or returns unusable output."""


# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

# Gemini's officially documented OpenAI-compatible base URL.
# Source: https://ai.google.dev/gemini-api/docs/openai
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

_VALID_PROVIDERS = {"openai", "gemini"}


def get_llm_settings() -> tuple[str, str, str | None]:
    """Return (api_key, model, base_url).

    base_url is None for OpenAI (uses the SDK default).
    base_url is the Gemini compat endpoint for Gemini.

    Reads from environment:
      LLM_PROVIDER   — "openai" (default) or "gemini"
      OPENAI_API_KEY / OPENAI_MODEL
      GEMINI_API_KEY / GEMINI_MODEL
    """
    provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()

    if provider not in _VALID_PROVIDERS:
        raise LLMClientError(
            f"Unknown LLM_PROVIDER '{provider}'. Valid values: {', '.join(sorted(_VALID_PROVIDERS))}."
        )

    if provider == "gemini":
        api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not api_key:
            raise LLMClientError(
                "GEMINI_API_KEY is missing. Add it to the .env file in the project root. "
                "Get a free key at https://aistudio.google.com/apikey"
            )
        model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
        return api_key, model, _GEMINI_BASE_URL

    # Default: openai
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise LLMClientError(
            "OPENAI_API_KEY is missing. Add it to a .env file in the project root."
        )
    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    return api_key, model, None


# ---------------------------------------------------------------------------
# Internal: shared HTTP call
# ---------------------------------------------------------------------------

def _is_quota_error(message: str) -> bool:
    """Detect rate-limit / quota errors from either provider."""
    lower = message.lower()
    # OpenAI quota strings
    if "429" in lower or "insufficient_quota" in lower or "credit_balance" in lower:
        return True
    # Gemini quota strings (RESOURCE_EXHAUSTED maps to HTTP 429 on the compat layer)
    if "resource_exhausted" in lower or "quota" in lower:
        return True
    return False


def _chat_json(messages: list[dict]) -> dict:
    """Send a chat request and return a parsed JSON dict.

    Uses whichever provider is configured in .env.
    Raises LLMClientError for API errors, quota issues, or bad JSON.
    Never returns fabricated data on error.
    """
    api_key, model, base_url = get_llm_settings()

    try:
        # base_url=None → OpenAI SDK uses its own default endpoint (unchanged behaviour).
        # base_url=_GEMINI_BASE_URL → routes the same call to Gemini's compat layer.
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = response.choices[0].message.content or ""
    except LLMClientError:
        raise
    except Exception as exc:
        message = str(exc)
        if _is_quota_error(message):
            provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
            raise LLMClientError(
                f"The {provider} API has no remaining quota or credits. "
                "Comparison used deterministic rules where possible. "
                "Add billing credits or switch LLM_PROVIDER in .env."
            ) from exc
        raise LLMClientError(f"The LLM API request failed: {exc}") from exc

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMClientError(
            f"The LLM returned invalid JSON (provider={os.getenv('LLM_PROVIDER', 'openai')}). "
            "Raw content was discarded to avoid fabricated data."
        ) from exc

    if not isinstance(payload, dict):
        raise LLMClientError("The LLM returned invalid structured output.")

    return payload


# ---------------------------------------------------------------------------
# Public API — interfaces unchanged; called by commitment_extractor and
# policy_comparator exactly as before
# ---------------------------------------------------------------------------

def extract_commitments_from_chunk(chunk: dict) -> list[dict]:
    """Send one page-aware chunk to the configured LLM and return parsed commitment dicts."""
    api_key, model, base_url = get_llm_settings()
    page_numbers = chunk.get("page_numbers", [])
    text = chunk.get("text", "")

    user_prompt = (
        "Extract explicit ESG policy commitments from this chunk.\n"
        f"page_numbers: {page_numbers}\n\n"
        f"{text}"
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ""
    except LLMClientError:
        raise
    except Exception as exc:
        message = str(exc)
        if _is_quota_error(message):
            provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
            raise LLMClientError(
                f"The {provider} API has no remaining quota or credits. "
                "This app does not need an LLM for structured COMMITMENT ID registers. "
                "For narrative PDFs, ensure your API key has available quota."
            ) from exc
        raise LLMClientError(f"The LLM API request failed: {exc}") from exc

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMClientError(
            "The LLM returned invalid JSON. Raw content was discarded to avoid fabricated data."
        ) from exc

    if not isinstance(payload, dict):
        raise LLMClientError("The LLM returned invalid structured output.")

    commitments = payload.get("commitments", [])
    if commitments is None:
        commitments = []
    if not isinstance(commitments, list):
        raise LLMClientError("The LLM returned invalid structured output.")

    return commitments


def compare_commitments_with_llm(old_fields: dict, new_fields: dict) -> dict:
    """Compare two structured commitments. Does not send PDF text."""
    payload = _chat_json(
        [
            {"role": "system", "content": COMPARISON_PROMPT},
            {
                "role": "user",
                "content": json.dumps({"old": old_fields, "new": new_fields}, ensure_ascii=True),
            },
        ]
    )
    classification = str(payload.get("classification") or "").upper().strip()
    if classification not in {"STRENGTHENED", "WEAKENED", "UNCHANGED", "MODIFIED"}:
        raise LLMClientError("The LLM returned an invalid comparison classification.")
    changed = payload.get("changed_fields") or []
    if not isinstance(changed, list):
        changed = []
    return {
        "classification": classification,
        "reason": str(payload.get("reason") or "").strip(),
        "changed_fields": [str(item) for item in changed],
        "confidence": payload.get("confidence", 0.5),
    }
