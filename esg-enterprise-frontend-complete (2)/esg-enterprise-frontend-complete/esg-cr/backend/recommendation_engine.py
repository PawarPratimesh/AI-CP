"""Recommendation engine.


"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from dotenv import load_dotenv


DEFAULT_HF_MODEL = "Qwen/Qwen2.5-7B-Instruct"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_runtime_env() -> None:
    load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"), override=False)
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=False)


_load_runtime_env()
HF_URL = "https://router.huggingface.co/v1/chat/completions"


CONTEXT_FIELDS = (
    "policy_statement", "metric", "baseline", "target", "deadline", "scope",
    "monitoring_frequency", "evidence_requirement", "responsible_owner",
)


def build_recommendation_contexts(comparisons: list[dict], old_commitments: list[dict], new_commitments: list[dict]) -> dict[str, dict]:
    """Join comparison rows to their original commitment fields for recommendations only."""
    old_by_id = {str(item.get("commitment_id") or "").upper(): item for item in old_commitments}
    new_by_id = {str(item.get("commitment_id") or "").upper(): item for item in new_commitments}
    contexts = {}
    for row in comparisons:
        old_id = str(row.get("old_commitment_id") or "").upper()
        new_id = str(row.get("new_commitment_id") or "").upper()
        commitment_id = row.get("new_commitment_id") or row.get("old_commitment_id")
        old_item, new_item = old_by_id.get(old_id, {}), new_by_id.get(new_id, {})
        if commitment_id:
            contexts[str(commitment_id).upper()] = {
                "commitment_id": commitment_id,
                "category": new_item.get("category") or old_item.get("category"),
                "classification": row.get("classification"),
                "changed_fields": row.get("changed_fields") or [],
                "reason": row.get("reason") or "",
                "old": {field: old_item.get(field) for field in CONTEXT_FIELDS if old_item.get(field) not in (None, "")},
                "new": {field: new_item.get(field) for field in CONTEXT_FIELDS if new_item.get(field) not in (None, "")},
            }
    return contexts


def _value(value: object) -> str:
    return str(value) if value not in (None, "") else "not stated"


def _change_description(risk: dict, context: dict) -> str:
    old, new = context.get("old", {}), context.get("new", {})
    fields = context.get("changed_fields") or []
    changes = []
    for field in fields:
        before, after = old.get(field), new.get(field)
        if before != after:
            changes.append(f"{field.replace('_', ' ')} changed from '{_value(before)}' to '{_value(after)}'")
    if changes:
        return "; ".join(changes)
    if risk.get("classification") == "NEW":
        return f"new commitment text: '{_value(new.get('policy_statement'))}'"
    if risk.get("classification") == "REMOVED":
        return f"old commitment text removed: '{_value(old.get('policy_statement'))}'"
    return context.get("reason") or "the policy commitment changed"


def _deterministic_recommendation(risk: dict, context: dict | None = None) -> dict:
    c = risk["classification"]
    cat = risk["category"].title()
    context = context or {}
    details = _change_description(risk, context)
    commitment_id = risk.get("commitment_id") or context.get("commitment_id")
    title_id = commitment_id or c.title()
    commitment_label = commitment_id or "the commitment"
    old, new = context.get("old", {}), context.get("new", {})
    action = {
        "REMOVED": f"Restore {commitment_label} with the prior requirement ({details}), or formally approve and document why that exact requirement is not being retained.",
        "WEAKENED": f"Restore the prior {commitment_label} requirement where possible; otherwise formally approve and document this exact change ({details}) and its control evidence.",
        "REDUCED": f"Reassess the reduced requirement for {commitment_label} ({details}) and document the rationale for the new value '{_value(new.get('target'))}'.",
        "MODIFIED": f"Approve and operationalize the new {commitment_label} requirement ({details}); retain evidence that demonstrates the supplied new wording or control, because this material change is assessed at {risk['risk_level']} risk with score {risk['risk_score']}.",
        "NEW": f"For new commitment {commitment_label} ({details}), establish only the stated monitoring frequency and evidence requirement, and assign ownership where the supplied commitment identifies it.",
        "STRENGTHENED": f"Operationalize the stronger {commitment_label} requirement ({details}) by updating monitoring and evidence records to demonstrate the new requirement.",
        "UNCHANGED": f"Continue the stated monitoring frequency and evidence process for unchanged commitment {commitment_label}.",
    }.get(c, f"Address the specific change for {commitment_label}: {details}.")
    return {
        "title": f"{cat} — {title_id} commitment",
        "priority": risk["risk_level"],
        "action": action,
        "basis": f"{details}. {risk.get('description', '')} This {c.lower()} change has deterministic risk score {risk['risk_score']} ({risk['risk_level']}).",
        "source": "deterministic_fallback",
    }


def _call_huggingface(risks: list[dict], contexts: dict[str, dict]) -> list[dict]:
    _load_runtime_env()
    token = (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY") or "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN is not configured.")

    model = (os.getenv("HF_MODEL") or DEFAULT_HF_MODEL).strip()
    top = risks[:5]
    recommendation_inputs = []
    risk_fields = (
        "commitment_id", "category", "classification", "risk_score", "risk_level",
        "description", "changed_fields", "evidence", "old_commitment_text", "new_commitment_text",
    )
    for risk in top:
        context = contexts.get(str(risk.get("commitment_id") or "").upper(), {})
        classification = str(risk.get("classification") or "").upper()
        changed = set(context.get("changed_fields") or [])
        if classification == "NEW":
            changed = set(context.get("new", {}))
        elif classification == "REMOVED":
            changed = set(context.get("old", {}))
        recommendation_context = {
            "commitment_id": context.get("commitment_id"),
            "category": context.get("category"),
            "classification": context.get("classification"),
            "changed_fields": context.get("changed_fields", []),
            "reason": context.get("reason"),
            "old": {key: value for key, value in context.get("old", {}).items() if key in changed},
            "new": {key: value for key, value in context.get("new", {}).items() if key in changed},
        }
        recommendation_inputs.append({
            "risk": {key: risk[key] for key in risk_fields if key in risk},
            "commitment_context": recommendation_context,
        })
    prompt = """Write exactly one short ESG policy-change recommendation per input, preserving input order.
Return only valid JSON: {"recommendations":[{"title":"...","priority":"LOW|MEDIUM|HIGH|CRITICAL","action":"...","basis":"..."}]}

For each item:
- Title must include the exact commitment_id and classification.
- Action: at most 2 concise sentences. State the actual old-to-new change using the specific values (for example, '35% to 25%', not a field name or a copied full paragraph); explain why this exact change affects ESG risk; give a concrete action addressing it.
- Basis: state the supplied category, comparison reason, risk_score, and risk_level.
- For NEW, name the new requirement and only its supplied owner, target, deadline, scope, frequency, or evidence needs. For STRENGTHENED, explain how to operationalize the stronger requirement. For WEAKENED/REDUCED, recommend restoring the prior value or formally approving and documenting the weaker value. For REMOVED, identify the removed requirement and recommend restoring it or documenting an approved rationale.

Use only supplied facts. Never invent an owner, value, date, evidence, or regulation. Do not recalculate or change classification, risk_score, or risk_level. If a detail is absent, omit it. Avoid generic advice such as 'review the commitment' or 'resolve the changed fields'.
""" + json.dumps(recommendation_inputs, ensure_ascii=True)

    body = json.dumps({
        "model": model,
        "temperature": 0.2,
        "max_tokens": 2200,
        "messages": [
            {"role": "system", "content": "You provide factual ESG remediation recommendations from structured findings."},
            {"role": "user", "content": prompt},
        ],
    }).encode("utf-8")
    request = urllib.request.Request(
        HF_URL,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HF_TOKEN is present but invalid or rejected by Hugging Face ({detail}).") from exc
    except Exception as exc:
        raise RuntimeError(f"HF request failed: {exc}") from exc
    content = payload["choices"][0]["message"]["content"]
    parsed = _parse_recommendation_payload(content)
    result = parsed.get("recommendations", [])
    if not isinstance(result, list):
        raise ValueError("Hugging Face returned an invalid recommendations object.")
    if len(result) != len(top):
        raise ValueError("Hugging Face did not return one recommendation per supplied risk.")
    recommendations = [
        {
            "title": str(x.get("title", "ESG recommendation")),
            "priority": str(x.get("priority", "MEDIUM")).upper(),
            "action": str(x.get("action", "")),
            "basis": str(x.get("basis", "")),
            "source": "huggingface",
        }
        for x in result if isinstance(x, dict)
    ]
    if len(recommendations) != len(top):
        raise ValueError("Hugging Face returned a non-object recommendation item.")
    for recommendation, risk in zip(recommendations, top):
        context = contexts.get(str(risk.get("commitment_id") or "").upper(), {})
        text = " ".join(recommendation[key] for key in ("title", "action", "basis")).lower()
        commitment_id = str(risk.get("commitment_id") or context.get("commitment_id") or "").lower()
        classification = str(risk.get("classification") or context.get("classification") or "").lower()
        if commitment_id and commitment_id not in text:
            recommendation["title"] = f"{commitment_id.upper()} {classification.upper()}: {recommendation['title']}"
        elif classification and classification not in text:
            recommendation["title"] = f"{classification.upper()}: {recommendation['title']}"
        text = " ".join(recommendation[key] for key in ("title", "action", "basis")).lower()
        supplied_values = [str(value).lower() for side in ("old", "new") for value in context.get(side, {}).values() if value]
        supplied_values.extend(str(risk.get(key) or "").lower() for key in ("evidence", "old_commitment_text", "new_commitment_text"))
        stop_words = {"the", "and", "for", "with", "from", "will", "shall", "company", "this", "that", "commitment", "policy", "target", "baseline", "deadline", "scope", "monitoring", "frequency", "evidence", "requirement", "annual", "annually", "ongoing"}
        response_words = set(re.findall(r"[a-z0-9%]+", text))
        has_actual_value = False
        for value in supplied_values:
            value_words = set(re.findall(r"[a-z0-9%]+", value)) - stop_words
            overlap = value_words & response_words
            if len(overlap) >= 2 or any(any(char.isdigit() for char in word) for word in overlap):
                has_actual_value = True
                break
        generic = ("resolve the specific change", "review the commitment", "document the change")
        if not commitment_id or commitment_id not in text or classification not in text or not has_actual_value or any(phrase in text for phrase in generic):
            raise ValueError("Hugging Face returned a generic or insufficiently grounded recommendation.")
    return recommendations


def _parse_recommendation_payload(content: object) -> dict:
    """Parse JSON returned directly, in a code fence, or within brief prose."""
    if not isinstance(content, str):
        raise ValueError("Hugging Face returned non-text recommendation content.")

    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    candidates = [text]
    object_start = text.find("{")
    object_end = text.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(text[object_start : object_end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    marker = text.find('"recommendations"')
    array_start = text.find("[", marker) if marker >= 0 else -1
    if array_start >= 0:
        decoder = json.JSONDecoder()
        recommendations = []
        position = array_start + 1
        while position < len(text):
            while position < len(text) and (text[position].isspace() or text[position] in ",}"):
                position += 1
            if position >= len(text) or text[position] == "]":
                break
            if text[position] != "{":
                next_item = text.find('{"title"', position)
                if next_item < 0:
                    break
                position = next_item
            try:
                item, position = decoder.raw_decode(text, position)
            except json.JSONDecodeError:
                break
            if isinstance(item, dict):
                recommendations.append(item)
        if recommendations:
            return {"recommendations": recommendations}

    raise ValueError("Hugging Face returned invalid recommendation JSON.")


def generate_recommendations(risks: list[dict], use_ai: bool = True, contexts: dict[str, dict] | None = None) -> tuple[list[dict], list[str]]:
    contexts = contexts or {}
    warnings: list[str] = []
    if use_ai:
        try:
            return _call_huggingface(risks, contexts), warnings
        except Exception as exc:
            warnings.append(f"AI recommendations unavailable; deterministic recommendations used: {exc}")

    return [_deterministic_recommendation(risk, contexts.get(str(risk.get("commitment_id") or "").upper())) for risk in risks[:20]], warnings
