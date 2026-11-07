"""Deterministic ESG risk engine using an ISO 31000-aligned 5x5 matrix.

ISO 31000:2018 provides the risk-management framework; 
    risk score = likelihood (1..5) * impact (1..5)
    1-4 Low, 5-9 Moderate, 10-16 High, 17-25 Critical

For policy-version analysis, likelihood and impact are assessed from the type of
commitment change and evidence quality. The result is a transparent, repeatable
screening score, not a claim that ISO assigns a particular number to a commitment.
"""
from __future__ import annotations

from typing import Iterable
from schemas import CommitmentComparison

LEVELS = ((68, "CRITICAL"), (40, "HIGH"), (20, "MODERATE"), (0, "LOW"))
CLASS_RISK = {
    "REMOVED": (4, 5),       # control/commitment disappears
    "WEAKENED": (4, 4),      # reduced ambition/control
    "REDUCED": (4, 4),       # legacy alias
    "MODIFIED": (3, 3),      # material change, direction uncertain
    "NEW": (2, 2),            # new exposure/control requires review
    "STRENGTHENED": (1, 2),  # reduced exposure through stronger commitment
    "UNCHANGED": (1, 2),
}


def clamp5(value: int | float) -> int:
    return max(1, min(5, int(round(float(value)))))


def risk_level(score: float) -> str:
    for minimum, label in LEVELS:
        if score >= minimum:
            return label
    return "LOW"


def calculate_risk_score(severity: int, likelihood: int, impact: int, evidence_quality: int | None = None) -> float:
    """Return a 0-100 display score derived from the 1-25 5x5 matrix.

    ``severity`` is retained for API compatibility and is not multiplied into
    the core matrix. The authoritative risk calculation is likelihood*impact.
    Evidence quality is reported separately and never artificially discounts risk.
    """
    _ = clamp5(severity)
    l, i = clamp5(likelihood), clamp5(impact)
    return round(((l * i) / 25.0) * 100.0, 2)


def category_from_comparison(row: CommitmentComparison) -> str:
    value = (row.new_commitment_id or row.old_commitment_id or "").upper()
    if value.startswith("ENV-"): return "ENVIRONMENTAL"
    if value.startswith("SOC-"): return "SOCIAL"
    if value.startswith("GOV-"): return "GOVERNANCE"
    return "GOVERNANCE"


def _evidence_quality(row: CommitmentComparison) -> int:
    # Confidence is converted only to an auditable evidence-quality indicator;
    # it does not change the risk score.
    return clamp5(round(row.confidence * 5))


def risk_from_comparison(row: CommitmentComparison) -> dict:
    classification = row.classification.upper()
    likelihood, impact = CLASS_RISK.get(classification, (3, 3))
    evidence_quality = _evidence_quality(row)
    score = calculate_risk_score(5, likelihood, impact, evidence_quality)
    severity = "CRITICAL" if impact == 5 else "HIGH" if impact == 4 else "MEDIUM" if impact == 3 else "LOW"
    likelihood_reason = {
        "REMOVED": "Likelihood 4: an existing commitment/control has been removed, creating a likely governance or control exposure if the underlying issue remains.",
        "WEAKENED": "Likelihood 4: the policy change reduces an existing control or target, making deterioration more plausible.",
        "REDUCED": "Likelihood 4: legacy reduced-target classification indicates lower policy ambition.",
        "MODIFIED": "Likelihood 3: a material change is present but its directional effect cannot be established confidently.",
        "NEW": "Likelihood 2: the commitment is newly introduced; the change itself is not evidence of an existing failure.",
        "STRENGTHENED": "Likelihood 1: the policy change strengthens the control or target, so the policy-change exposure is lower.",
        "UNCHANGED": "Likelihood 1: no material deterioration was detected in the compared commitment.",
    }.get(classification, "Likelihood 3: default moderate screening criterion.")
    impact_reason = {
        "REMOVED": "Impact 5: removal can eliminate an existing ESG control/target and may affect environmental, social or governance objectives.",
        "WEAKENED": "Impact 4: a weaker target or control can materially reduce the organisation's ability to manage the related ESG objective.",
        "REDUCED": "Impact 4: reduced ambition or coverage can materially affect progress toward the stated ESG objective.",
        "MODIFIED": "Impact 3: the change is material but its consequence is uncertain from the available policy data.",
        "NEW": "Impact 2: a new commitment requires ownership and monitoring, but the policy change alone does not demonstrate a severe adverse impact.",
        "STRENGTHENED": "Impact 2: stronger commitments generally reduce exposure; residual implementation risk remains.",
        "UNCHANGED": "Impact 2: no deterioration was detected; residual implementation risk remains.",
    }.get(classification, "Impact 3: default moderate screening criterion.")
    evidence = row.new_source.evidence if row.new_source.page_numbers else row.old_source.evidence
    return {
        "commitment_id": row.new_commitment_id or row.old_commitment_id,
        "category": category_from_comparison(row),
        "classification": classification,
        "severity": severity,
        "likelihood": likelihood,
        "impact": impact,
        "evidence_quality": evidence_quality,
        "risk_score": score,
        "risk_level": risk_level(score),
        "title": f"{classification.title()} policy commitment",
        "description": row.reason,
        "changed_fields": row.changed_fields,
        "likelihood_reason": likelihood_reason,
        "impact_reason": impact_reason,
        "methodology": "ISO 31000:2018-aligned 5x5 likelihood-impact screening matrix; application-specific criteria documented in METHODOLOGY.md.",
        "evidence": evidence,
        "old_commitment_text": row.old_source.evidence,
        "new_commitment_text": row.new_source.evidence,
        "source": {"old_pages": row.old_source.page_numbers, "new_pages": row.new_source.page_numbers},
    }


def calculate_esg_scores(risks: Iterable[dict]) -> dict:
    buckets = {"ENVIRONMENTAL": [], "SOCIAL": [], "GOVERNANCE": []}
    for item in risks:
        category = str(item.get("category", "")).upper()
        if category in buckets:
            buckets[category].append(float(item.get("risk_score", 0)))
    scores = {}
    for category, values in buckets.items():
        avg = sum(values) / len(values) if values else 0.0
        scores[category] = round(100.0 - avg, 2)
    overall = round(sum(scores.values()) / 3.0, 2)
    return {
        "environmental": scores["ENVIRONMENTAL"], "social": scores["SOCIAL"],
        "governance": scores["GOVERNANCE"], "overall": overall,
        "method": "100 - average 0-100 risk display score per E/S/G category; equal category weights.",
    }


def calculate_aggregate_risk(risks: Iterable[dict]) -> dict:
    """Aggregate existing individual risk scores without changing their formula."""
    buckets = {"ENVIRONMENTAL": [], "SOCIAL": [], "GOVERNANCE": []}
    all_scores = []
    for item in risks:
        score = float(item.get("risk_score", 0))
        all_scores.append(score)
        category = str(item.get("category", "")).upper()
        if category in buckets:
            buckets[category].append(score)

    def aggregate(values: list[float]) -> dict:
        score = round(sum(values) / len(values), 2) if values else 0.0
        return {"risk_score": score, "risk_level": risk_level(score), "commitment_count": len(values)}

    return {
        "overall": aggregate(all_scores),
        "environmental": aggregate(buckets["ENVIRONMENTAL"]),
        "social": aggregate(buckets["SOCIAL"]),
        "governance": aggregate(buckets["GOVERNANCE"]),
        "method": "Arithmetic mean of existing individual 0-100 commitment risk scores; overall uses all commitments and each category uses commitments in that category.",
    }


def build_risk_report(comparisons: list[CommitmentComparison]) -> dict:
    risks = [risk_from_comparison(row) for row in comparisons]
    risks.sort(key=lambda x: x["risk_score"], reverse=True)
    return {
        "risk_count": len(risks),
        "high_or_critical_count": sum(1 for item in risks if item["risk_level"] in {"HIGH", "CRITICAL"}),
        "risks": risks,
        "aggregate_risk": calculate_aggregate_risk(risks),
        "esg_scores": calculate_esg_scores(risks),
        "formula": {
            "risk_score": "Likelihood (1-5) × Impact (1-5); 1-25 matrix, displayed as (L×I)/25×100",
            "scales": "Likelihood and impact are 1..5; evidence quality is 1..5 and does not alter risk.",
            "risk_levels": "Matrix: 1-4 LOW, 5-9 MODERATE, 10-16 HIGH, 17-25 CRITICAL; display-score equivalents: 0-19.99 LOW, 20-39.99 MODERATE, 40-67.99 HIGH, 68-100 CRITICAL.",
            "standard_basis": "ISO 31000:2018-aligned risk identification, analysis and evaluation; numeric matrix is the application's documented operational criterion.",
        },
    }
