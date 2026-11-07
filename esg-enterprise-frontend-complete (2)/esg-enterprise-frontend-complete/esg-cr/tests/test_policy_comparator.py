import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from policy_comparator import (
    classify_deterministically,
    compare_policies,
    match_commitments,
    summarize,
)
from schemas import Commitment, SourceEvidence


def _item(**overrides) -> Commitment:
    data = {
        "commitment_id": "ENV-001",
        "category": "Environmental",
        "policy_statement": "The Company shall reduce emissions.",
        "metric": "Absolute Scope 1 + Scope 2 greenhouse-gas emissions",
        "baseline": "2020 = 100 index",
        "target": "10% by 2026",
        "deadline": "31 December 2026",
        "responsible_owner": "Corporate Sustainability Office",
        "scope": "All controlled manufacturing facilities globally",
        "evidence_requirement": "Annual verified emissions inventory.",
        "monitoring_frequency": "Quarterly",
        "escalation": "Escalate material deviation.",
        "source": SourceEvidence(page_numbers=[10], evidence="ENV-001 The Company shall reduce emissions."),
        "confidence": 0.99,
    }
    data.update(overrides)
    return Commitment(**data)


def test_unchanged_target():
    old = _item(target="10% by 2026")
    new = _item(target="10% by 2026")
    result = classify_deterministically(old, new)
    assert result is not None
    assert result["classification"] == "UNCHANGED"


def test_strengthened_target():
    old = _item(target="10%")
    new = _item(target="20%")
    result = classify_deterministically(old, new)
    assert result is not None
    assert result["classification"] == "STRENGTHENED"


def test_reduced_target():
    old = _item(target="30%")
    new = _item(target="20%")
    result = classify_deterministically(old, new)
    assert result is not None
    assert result["classification"] == "WEAKENED"


def test_reduced_minimum_target_is_weakened():
    old = _item(
        commitment_id="ENV-002",
        policy_statement="The Company will source at least 35% of electricity from renewable sources.",
        target="35% of electricity from renewable sources",
    )
    new = _item(
        commitment_id="ENV-002",
        policy_statement="The Company will source at least 25% of electricity from renewable sources.",
        target="25% of electricity from renewable sources",
    )
    result = classify_deterministically(old, new)
    assert result is not None
    assert result["classification"] == "WEAKENED"


def test_deadline_weakened():
    old = _item(deadline="31 December 2026")
    new = _item(deadline="31 December 2028")
    result = classify_deterministically(old, new)
    assert result is not None
    assert result["classification"] == "WEAKENED"


def test_removed_commitment():
    old = [_item(commitment_id="ENV-001")]
    new: list[Commitment] = []
    rows, _warnings = compare_policies(old, new, llm_comparer=None)
    assert len(rows) == 1
    assert rows[0].classification == "REMOVED"
    assert rows[0].old_commitment_id == "ENV-001"


def test_new_commitment():
    old: list[Commitment] = []
    new = [_item(commitment_id="GOV-011")]
    rows, _warnings = compare_policies(old, new, llm_comparer=None)
    assert len(rows) == 1
    assert rows[0].classification == "NEW"
    assert rows[0].new_commitment_id == "GOV-011"


def test_exact_commitment_id_matching():
    old = [_item(commitment_id="ENV-001", target="10%")]
    new = [_item(commitment_id="ENV-001", target="20%", source=SourceEvidence(page_numbers=[11], evidence="new"))]
    matching = match_commitments(old, new)
    assert matching["matched"] == [(0, 0, 1.0)]


def test_same_commitment_id_matches_even_when_extracted_text_differs():
    old = _item(commitment_id="GOV-001", policy_statement="Anti-bribery controls", target=None)
    new = _item(commitment_id="GOV-001", policy_statement="The Company shall maintain anti-bribery controls.", target=None)
    matching = match_commitments([old], [new])
    assert matching["matched"][0][:2] == (0, 0)
    assert matching["matched"][0][2] >= 0.82


def test_evidence_preservation():
    old = [_item(commitment_id="ENV-001", target="10%")]
    new = [
        _item(
            commitment_id="ENV-001",
            target="20%",
            source=SourceEvidence(page_numbers=[11], evidence="ENV-001 20%"),
        )
    ]
    rows, _warnings = compare_policies(old, new, llm_comparer=None)
    assert rows[0].old_source.page_numbers == [10]
    assert "ENV-001" in rows[0].old_source.evidence
    assert rows[0].new_source.page_numbers == [11]
    assert rows[0].new_source.evidence == "ENV-001 20%"


def test_llm_is_mocked_for_ambiguous_wording():
    old = _item(evidence_requirement="Keep records.")
    new = _item(evidence_requirement="Publish independently assured records each quarter.")
    called = {"count": 0}

    def fake_llm(_old, _new):
        called["count"] += 1
        return {
            "classification": "STRENGTHENED",
            "reason": "The evidence requirement became more specific and more frequent.",
            "changed_fields": ["evidence_requirement"],
            "confidence": 0.88,
        }

    rows, _warnings = compare_policies([old], [new], llm_comparer=fake_llm)
    assert called["count"] == 1
    assert rows[0].classification == "STRENGTHENED"
    assert rows[0].changed_fields == ["evidence_requirement"]


def test_summary_counts_are_calculated():
    old = [
        _item(commitment_id="ENV-001", target="10%"),
        _item(commitment_id="ENV-002", target="30%"),
        _item(commitment_id="SOC-001"),
    ]
    new = [
        _item(commitment_id="ENV-001", target="20%"),
        _item(commitment_id="ENV-002", target="20%"),
        _item(commitment_id="GOV-011"),
    ]
    rows, _warnings = compare_policies(old, new, llm_comparer=None)
    summary = summarize(rows)
    assert summary.strengthened == 1
    assert summary.reduced == 1
    assert summary.removed == 1
    assert summary.new == 1
    assert summary.unchanged == 0


def test_demo_frequency_and_hours_requirements_are_classified_as_strengthened():
    old = _item(commitment_id="ENV-004", monitoring_frequency="Annual")
    new = _item(commitment_id="ENV-004", monitoring_frequency="Every 6 months")
    result = classify_deterministically(old, new)
    assert result is not None
    assert result["classification"] == "STRENGTHENED"

    old_training = _item(commitment_id="SOC-001", policy_statement="Employees will receive at least 20 hours of training each year.")
    new_training = _item(commitment_id="SOC-001", policy_statement="Employees will receive at least 40 hours of training each year.")
    result_training = classify_deterministically(old_training, new_training)
    assert result_training is not None
    assert result_training["classification"] == "STRENGTHENED"

    old_reporting = _item(commitment_id="ENV-005", policy_statement="The company will divert at least 60% of non-hazardous operational waste from landfill by 31 December 2027.")
    new_reporting = _item(commitment_id="ENV-005", policy_statement="The company will divert at least 60% of non-hazardous operational waste from landfill by 31 December 2027 and will report progress quarterly.")
    result_reporting = classify_deterministically(old_reporting, new_reporting)
    assert result_reporting is not None
    assert result_reporting["classification"] == "STRENGTHENED"
