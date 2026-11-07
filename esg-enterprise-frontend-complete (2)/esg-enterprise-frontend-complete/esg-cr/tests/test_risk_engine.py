import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from policy_comparator import compare_policies
from risk_engine import build_risk_report, calculate_risk_score
from schemas import Commitment, SourceEvidence


def item(cid, category="Environmental", target="10%", **kw):
    data = dict(
        commitment_id=cid, category=category, policy_statement="The Company shall reduce emissions.",
        metric="emissions", baseline="2020=100", target=target, deadline="2026",
        responsible_owner="Owner", scope="All facilities", evidence_requirement="Annual evidence",
        monitoring_frequency="Annual", escalation="Escalate", source=SourceEvidence(page_numbers=[1], evidence="evidence"),
        confidence=0.9,
    )
    data.update(kw)
    return Commitment(**data)


def test_risk_formula_boundaries():
    assert calculate_risk_score(1, 1, 1, 1) >= 0
    assert calculate_risk_score(5, 5, 5, 5) == 100


def test_esg_report_is_deterministic():
    rows, _ = compare_policies([item("ENV-001", target="30%")], [item("ENV-001", target="20%")], None)
    report = build_risk_report(rows)
    assert report["risks"][0]["classification"] == "WEAKENED"
    assert report["esg_scores"]["overall"] <= 100
    assert 0 <= report["esg_scores"]["environmental"] <= 100
    assert report["aggregate_risk"]["environmental"]["risk_score"] == report["risks"][0]["risk_score"]
    assert report["aggregate_risk"]["environmental"]["risk_level"] == report["risks"][0]["risk_level"]
    assert report["aggregate_risk"]["overall"]["commitment_count"] == 1
