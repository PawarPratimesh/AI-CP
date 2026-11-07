"""Gemini provider smoke test.

Sends ONE minimal structured-JSON request to verify:
  - GEMINI_API_KEY is present and accepted
  - The OpenAI-compat endpoint is reachable
  - response_format={"type":"json_object"} works
  - The response is valid JSON with the expected key

Run manually (not part of the normal pytest suite):
    python tests/smoke_test_gemini.py

Requires GEMINI_API_KEY in .env (LLM_PROVIDER=gemini).
Does NOT test commitment extraction or policy comparison prompts.
Does NOT consume unnecessary tokens — prompt is ~10 tokens.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow running from project root or tests/ directory.
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def main() -> None:
    print("── Gemini smoke test ──────────────────────────────────────────")
    print(f"  LLM_PROVIDER : {LLM_PROVIDER}")
    print(f"  GEMINI_MODEL : {GEMINI_MODEL}")
    key_display = (GEMINI_API_KEY[:8] + "…") if len(GEMINI_API_KEY) > 8 else "(empty)"
    print(f"  GEMINI_API_KEY : {key_display}")
    print()

    if not GEMINI_API_KEY:
        print("SKIP  GEMINI_API_KEY is not set in .env.")
        print("      Add your key from https://aistudio.google.com/apikey")
        print("      then re-run:  python tests/smoke_test_gemini.py")
        sys.exit(0)

    if LLM_PROVIDER != "gemini":
        print(f"SKIP  LLM_PROVIDER is '{LLM_PROVIDER}', not 'gemini'.")
        print("      Set LLM_PROVIDER=gemini in .env to run this test.")
        sys.exit(0)

    # Import here so the path insertion above takes effect first.
    from openai import OpenAI

    client = OpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL)

    prompt = 'Return exactly this JSON and nothing else: {"smoke_test": "ok"}'

    print(f"Sending 1 request to {GEMINI_BASE_URL} …")
    try:
        response = client.chat.completions.create(
            model=GEMINI_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        print(f"FAIL  API call raised an exception:\n      {exc}")
        sys.exit(1)

    content = (response.choices[0].message.content or "").strip()
    print(f"Raw response content: {content!r}")

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        print(f"FAIL  Response is not valid JSON: {exc}")
        sys.exit(1)

    if not isinstance(payload, dict):
        print(f"FAIL  Expected a JSON object, got: {type(payload).__name__}")
        sys.exit(1)

    if "smoke_test" not in payload:
        print(f"FAIL  Expected key 'smoke_test' not found in: {payload}")
        sys.exit(1)

    print()
    print(f"PASS  Gemini returned valid structured JSON: {payload}")
    print(f"      Model  : {GEMINI_MODEL}")
    print(f"      Endpoint: {GEMINI_BASE_URL}")
    print()
    print("Gemini provider is working correctly.")
    print("You can now use LLM_PROVIDER=gemini for commitment extraction and policy comparison.")


if __name__ == "__main__":
    main()
