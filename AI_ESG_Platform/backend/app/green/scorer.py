"""Green Code Score calculator.

The score is **transparent**: every finding reduces a specific efficiency
dimension, and the overall score is a weighted average of dimension scores.

Dimensions and weights:
  network     20%  — API calls, network round-trips
  database    20%  — query efficiency, N+1 patterns
  compute     20%  — unnecessary computation, expensive operations
  caching     15%  — missing caching, repeated fetches
  cicd        15%  — wasteful CI/CD patterns
  code_quality 10% — general linter issues

Per-dimension penalty by severity:
  high   -15
  medium  -8
  low     -3

Dimension scores are clamped to [0, 100].
Overall = round(weighted average of dimensions).
"""

from __future__ import annotations

import json
from typing import Any

# ─── Configuration ─────────────────────────────────────────────────────────────

DIMENSION_WEIGHTS: dict[str, float] = {
    "network": 0.20,
    "database": 0.20,
    "compute": 0.20,
    "caching": 0.15,
    "cicd": 0.15,
    "code_quality": 0.10,
}

SEVERITY_PENALTY: dict[str, int] = {
    "high": 15,
    "medium": 8,
    "low": 3,
}

# Map finding categories (from static_analysis.py) to dimensions.
# Most categories already use dimension names; this is a safety net.
CATEGORY_TO_DIMENSION: dict[str, str] = {
    "network": "network",
    "database": "database",
    "compute": "compute",
    "caching": "caching",
    "cicd": "cicd",
    "code_quality": "code_quality",
    # Aliases
    "api": "network",
    "db": "database",
    "cpu": "compute",
    "cache": "caching",
    "ci": "cicd",
    "cd": "cicd",
}


def _resolve_dimension(category: str) -> str:
    """Map a finding category to a scoring dimension."""
    key = category.lower().strip()
    return CATEGORY_TO_DIMENSION.get(key, "code_quality")


# ─── Public API ───────────────────────────────────────────────────────────────

def calculate_score(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate the Green Code Score from a list of findings.

    Returns a dict with:
      overall_score       — float 0-100
      dimension_scores    — dict of dimension -> score
      finding_count       — int
      high_priority_count  — int
      medium_priority_count — int
      low_priority_count   — int
      formula              — str (human-readable explanation)
    """
    # Initialise all dimensions at 100.
    dimensions: dict[str, float] = {dim: 100.0 for dim in DIMENSION_WEIGHTS}

    severity_counts = {"high": 0, "medium": 0, "low": 0}

    for finding in findings:
        severity = (finding.get("severity") or "low").lower()
        category = finding.get("category") or "code_quality"
        dimension = _resolve_dimension(category)
        penalty = SEVERITY_PENALTY.get(severity, 3)

        dimensions[dimension] -= penalty
        if severity in severity_counts:
            severity_counts[severity] += 1

    # Clamp each dimension to [0, 100].
    for dim in dimensions:
        dimensions[dim] = max(0.0, min(100.0, dimensions[dim]))

    # Weighted average for overall score.
    overall = sum(
        dimensions[dim] * weight for dim, weight in DIMENSION_WEIGHTS.items()
    )
    overall = round(overall, 1)

    return {
        "overall_score": overall,
        "dimension_scores": dimensions,
        "dimension_scores_json": json.dumps(dimensions),
        "finding_count": len(findings),
        "high_priority_count": severity_counts["high"],
        "medium_priority_count": severity_counts["medium"],
        "low_priority_count": severity_counts["low"],
        "formula": (
            "Score = weighted average of 6 efficiency dimensions "
            "(network 20%, database 20%, compute 20%, caching 15%, "
            "cicd 15%, code_quality 10%). Each dimension starts at 100 and "
            "is reduced by 15 per high, 8 per medium, 3 per low finding. "
            "Dimensions are clamped to [0, 100]."
        ),
    }
