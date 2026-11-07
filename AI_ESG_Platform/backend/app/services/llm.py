import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Try these models in order until one works
MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]


def _call_with_retry(prompt: str, retries: int = 3, delay: int = 5) -> str:
    """
    Try each model in MODELS. For each model retry up to `retries`
    times on 503 UNAVAILABLE before moving to the next model.
    """
    last_error = None

    for model in MODELS:
        for attempt in range(retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                return response.text
            except genai_errors.ServerError as e:
                # 503 — model overloaded, wait and retry
                last_error = e
                if attempt < retries - 1:
                    time.sleep(delay)
            except genai_errors.ClientError as e:
                # 404 — model not available, try next model immediately
                last_error = e
                break
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(delay)

    raise RuntimeError(
        f"All Gemini models failed. Last error: {last_error}"
    )


def generate_answer(question: str, context: str) -> str:
    """
    Generate an answer using Gemini based only on the provided context.
    """
    prompt = f"""
You are an ESG document assistant.

Answer the user's question using ONLY the information
provided in the context below.

If the answer cannot be found in the context,
say that the information was not found in the provided document.

Context:
{context}

Question:
{question}
"""
    return _call_with_retry(prompt)


def generate_green_code_analysis(findings_json: str) -> str:
    """
    Enrich green-code findings with developer-friendly explanations,
    actionable recommendations, and ESG impact descriptions.

    Expects a JSON array of finding objects and returns a JSON array
    with index, explanation, recommendation, and esg_impact for each.
    """
    prompt = f"""
You are a green software engineering advisor.

For each code finding below, provide three fields:

1. "explanation" — a clear, developer-friendly explanation of WHY this
   pattern is inefficient and how it wastes compute, network, or energy
   resources. Keep it to 2-3 sentences.

2. "recommendation" — a concrete, actionable fix the developer can apply.
   Reference the specific code pattern. Keep it to 2-3 sentences.

3. "esg_impact" — how this inefficiency relates to ESG (Environmental,
   Social, Governance) metrics. For example, wasted compute → higher
   energy use → Scope 2 carbon emissions; unnecessary API calls →
   increased infrastructure cost and carbon footprint. Keep it to 1-2
   sentences and be specific about the ESG category (Environmental,
   Social, or Governance).

Return ONLY valid JSON (no markdown fences) in this exact format:

[
    {{
        "index": 0,
        "explanation": "...",
        "recommendation": "...",
        "esg_impact": "..."
    }}
]

The "index" must match the position of the finding in the input array (0-based).

CODE FINDINGS:

{findings_json}
"""
    return _call_with_retry(prompt)
