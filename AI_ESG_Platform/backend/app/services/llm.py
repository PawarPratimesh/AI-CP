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
            except (OSError, PermissionError) as e:
                # Network unreachable or socket forbidden — fail fast so fallback triggers immediately
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


def generate_infrastructure_recommendations(summary_payload_json: str) -> str:
    """
    Generate AI-powered infrastructure anomaly explanations and optimization recommendations
    using Gemini, based on pre-summarized infrastructure metrics and Isolation Forest results.
    """
    prompt = f"""
You are an expert Enterprise Cloud Infrastructure Architect and ESG Sustainability Advisor.

Analyze the summarized infrastructure telemetry, detected statistical anomalies, and Scope 2 modeled emissions below.
Provide:
1. "summary": A concise (1-2 short sentences, max 30 words) executive assessment of the fleet's operational efficiency and carbon impact.
2. "anomaly_explanations": For each detected anomaly in the input, explain in simple, concise technical language:
   - "resource_id": exact resource identifier
   - "timestamp": observation timestamp
   - "metric": primary unusual metric (e.g. CPU, Memory, Network)
   - "observed_value": numeric value if known, or null
   - "baseline_context": concise normal baseline reference (max 10 words)
   - "explanation": what happened in technical terms (1 short sentence, max 20 words)
   - "possible_causes": 1 plausible hypothesis to investigate (1 short sentence, max 18 words)
   - "operational_impact": potential reliability or latency impact (1 short sentence, max 18 words)
   - "investigation_steps": concrete next step to investigate (1 short sentence, max 18 words)
   NOTE: If the input data has NO anomalies (anomalies list is empty), set "anomaly_explanations" to an empty array []. NEVER fabricate anomalies.
3. "recommendations": Exactly 3 to 5 actionable, prioritized optimization recommendations based on the actual observed patterns.

STRICT LENGTH AND FORMAT RULES FOR EACH RECOMMENDATION:
- "title": Short, action-oriented title. MAXIMUM 8 WORDS.
- "target_resource": Resource ID or "Fleet-wide".
- "observation": The Issue. Maximum 1-2 short sentences (target 15-25 words). State the actual problem using evidence from data. Do not repeat raw metric tables.
- "action": Suggested Action. Maximum 1-2 short sentences (target 20-30 words). Clearly state what the team should investigate or do.
- "expected_benefit": Exactly one qualitative label: "High", "Medium", or "Low".
- "category": one of ["Compute Rightsizing", "Workload Optimization", "Decarbonization", "Memory Tuning", "Storage Lifecycle"]
- "reason": concise technical justification (max 15 words).
- "evidence": brief metric reference from data (max 12 words).
- "estimated_impact": optional qualitative benefit statement (max 15 words).

STRICT RULES:
1. Base all findings strictly on the provided infrastructure metrics.
2. In underutilized-resource recommendations, never display incomplete issue text (e.g. never write '8%'). Include the metric name ('average CPU utilization') and correct average value. Before suggesting downsizing or rightsizing, explicitly advise checking standby, failover and peak-demand requirements.
3. Do not generate contradictory or unsupported statements such as '0%, contributing significant carbon'. CPU utilization alone does not establish carbon impact. Only describe issues supported by actual uploaded metrics.
4. Preserve carbon intensity values and units correctly: always format as '0.XXX kg CO₂e/kWh' (e.g. '0.379 kg CO₂e/kWh'), never '379 kg/kWh'. Do not remove decimal places or CO₂e notation.
5. Anomaly baselines must match the unusual metric: compare CPU against CPU baselines, memory against memory baselines, network against network baselines. NEVER use a CPU baseline to explain a network anomaly.
6. Present causes as hypotheses to investigate ("Investigate potential..."), never as confirmed facts.
7. Do not make unsupported numerical savings claims (e.g. NEVER claim "save 48%" or "60% energy reduction"). Use qualitative benefits (High, Medium, Low).
8. For decarbonization recommendations, evaluate as an option considering latency, data residency (GDPR), and compliance constraints.
9. Return ONLY valid JSON (no markdown fences) matching the exact schema:
{{
  "summary": "...",
  "anomaly_explanations": [
    {{
      "resource_id": "...",
      "timestamp": "...",
      "metric": "...",
      "observed_value": 0.0,
      "baseline_context": "...",
      "explanation": "...",
      "possible_causes": "...",
      "operational_impact": "...",
      "investigation_steps": "..."
    }}
  ],
  "recommendations": [
    {{
      "title": "...",
      "category": "...",
      "target_resource": "...",
      "observation": "...",
      "action": "...",
      "reason": "...",
      "expected_benefit": "High",
      "evidence": "...",
      "estimated_impact": "..."
    }}
  ]
}}

INFRASTRUCTURE TELEMETRY & ANALYSIS SUMMARY:
{summary_payload_json}
"""
    return _call_with_retry(prompt, retries=1, delay=1)

