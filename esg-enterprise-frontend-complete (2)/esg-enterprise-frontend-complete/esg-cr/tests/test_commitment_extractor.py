import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from commitment_extractor import (
    clamp_confidence,
    create_chunks,
    deduplicate_commitments,
    empty_to_null,
    extract_commitments,
    looks_like_header_or_footer,
    normalize_commitment,
    parse_structured_commitments,
)
from schemas import Commitment, SourceEvidence


def _commitment(**overrides) -> Commitment:
    data = {
        "commitment_id": "GOV-010",
        "category": "Governance",
        "policy_statement": (
            "The Company shall link a minimum of 10% of executive variable compensation "
            "to the achievement of approved ESG targets by 2026."
        ),
        "metric": "Percentage of executive variable compensation linked to approved ESG targets",
        "baseline": "2021 = 0%",
        "target": "10% by 2026",
        "deadline": "31 December 2026",
        "responsible_owner": "Board Sustainability & Risk Committee",
        "scope": "Executive Committee members",
        "evidence_requirement": (
            "Executive compensation plan documentation and Remuneration Committee minutes."
        ),
        "monitoring_frequency": "Annual",
        "escalation": "Non-implementation shall be escalated to the full Board.",
        "source": SourceEvidence(
            page_numbers=[27],
            evidence="COMMITMENT ID: GOV-010 The Company shall link a minimum of 10%",
        ),
        "confidence": 0.99,
    }
    data.update(overrides)
    return Commitment(**data)


def test_empty_text_does_not_produce_a_fake_commitment():
    pages = [{"page_number": 1, "extracted_text": "   "}]
    chunks = create_chunks(pages)
    assert chunks == []

    def fake_llm(_chunk):
        raise AssertionError("LLM should not be called for empty text")

    try:
        extract_commitments(pages, fake_llm)
        assert False, "Expected empty-document error"
    except Exception as exc:
        assert "no usable text" in str(exc).lower()


def test_missing_optional_fields_become_null():
    raw = {
        "commitment_id": "",
        "category": "Environment",
        "policy_statement": "The Company shall reduce Scope 1 emissions.",
        "metric": "n/a",
        "baseline": None,
        "target": "none",
        "source": {"page_numbers": [4], "evidence": "The Company shall reduce Scope 1 emissions."},
        "confidence": 0.8,
    }
    commitment = normalize_commitment(raw, [4])
    assert commitment is not None
    assert commitment.commitment_id is None
    assert commitment.metric is None
    assert commitment.baseline is None
    assert commitment.target is None
    assert commitment.deadline is None
    assert commitment.responsible_owner is None


def test_commitment_ids_are_preserved():
    raw = {
        "commitment_id": "ENV-002",
        "policy_statement": "The Company shall publish an annual water-use report.",
        "source": {"page_numbers": [8], "evidence": "ENV-002"},
        "confidence": 0.9,
    }
    commitment = normalize_commitment(raw, [8])
    assert commitment is not None
    assert commitment.commitment_id == "ENV-002"


def test_duplicate_commitments_are_removed():
    first = _commitment()
    duplicate = _commitment(
        source=SourceEvidence(page_numbers=[27], evidence="duplicate overlap"),
        confidence=0.7,
    )
    same_statement = _commitment(
        commitment_id=None,
        source=SourceEvidence(page_numbers=[26], evidence="same statement"),
    )
    unique, removed = deduplicate_commitments([first, duplicate, same_statement])
    assert removed == 2
    assert len(unique) == 1
    assert unique[0].commitment_id == "GOV-010"
    assert unique[0].source.page_numbers == [27, 26]


def test_page_numbers_are_preserved():
    chunks = create_chunks(
        [
            {"page_number": 26, "extracted_text": "Earlier commitment text on page 26."},
            {"page_number": 27, "extracted_text": "COMMITMENT ID: GOV-010 appears on this page."},
        ]
    )
    assert chunks[0]["page_numbers"] == [26]
    assert 27 in chunks[1]["page_numbers"]

    raw = {
        "commitment_id": "GOV-010",
        "policy_statement": "The Company shall link a minimum of 10% of executive variable compensation to ESG targets.",
        "source": {"page_numbers": [27], "evidence": "GOV-010"},
        "confidence": 0.95,
    }
    commitment = normalize_commitment(raw, [26, 27])
    assert commitment is not None
    assert commitment.source.page_numbers == [27]


def test_header_footer_text_does_not_become_commitments():
    assert looks_like_header_or_footer("Page 12")
    assert looks_like_header_or_footer("Table of Contents")
    raw = {
        "commitment_id": None,
        "policy_statement": "Page 27",
        "source": {"page_numbers": [27], "evidence": "Page 27"},
        "confidence": 0.4,
    }
    assert normalize_commitment(raw, [27]) is None


def test_gov_010_structured_data_can_be_represented_correctly():
    commitment = _commitment()
    assert commitment.commitment_id == "GOV-010"
    assert commitment.category == "Governance"
    assert "10%" in commitment.policy_statement
    assert commitment.metric.startswith("Percentage of executive variable compensation")
    assert commitment.baseline == "2021 = 0%"
    assert commitment.target == "10% by 2026"
    assert commitment.deadline == "31 December 2026"
    assert commitment.responsible_owner == "Board Sustainability & Risk Committee"
    assert commitment.scope == "Executive Committee members"
    assert "Remuneration Committee minutes" in commitment.evidence_requirement
    assert commitment.monitoring_frequency == "Annual"
    assert "full Board" in commitment.escalation
    assert commitment.source.page_numbers == [27]


def test_parse_structured_gov_010_from_page_text():
    text = """
COMMITMENT ID: GOV-010
CATEGORY: Governance
POLICY STATEMENT:
The Company shall link a minimum of 10% of executive variable compensation
to the achievement of approved ESG targets by 2026.
METRIC:
Percentage of executive variable compensation linked to approved ESG targets
BASELINE:
2021 = 0%
TARGET:
10% by 2026
DEADLINE:
31 December 2026
RESPONSIBLE OWNER:
Board Sustainability & Risk Committee
SCOPE:
Executive Committee members
EVIDENCE REQUIREMENT:
Executive compensation plan documentation and Remuneration Committee
minutes.
MONITORING FREQUENCY:
Annual
ESCALATION:
Non-implementation shall be escalated to the full Board.
APEX INDUSTRIAL TECHNOLOGIES LTD.
Environmental, Social & Governance Policy — 2024
ESG-POL-2024-001 | Version 1.0 | Page 27 of 27
Synthetic Demonstration Document — Created for ESG Platform Evaluation
"""
    parsed = parse_structured_commitments(text, [27])
    assert len(parsed) == 1
    item = parsed[0]
    assert item["commitment_id"] == "GOV-010"
    assert item["category"] == "Governance"
    assert item["baseline"] == "2021 = 0%"
    assert item["target"] == "10% by 2026"
    assert item["deadline"] == "31 December 2026"
    assert "Apex" not in (item["escalation"] or "")
    assert "Page 27" not in (item["escalation"] or "")

    commitments, _warnings = extract_commitments(
        [{"page_number": 27, "extracted_text": text}],
        chunk_extractor=lambda _chunk: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    assert len(commitments) == 1
    assert commitments[0].commitment_id == "GOV-010"
    assert commitments[0].source.page_numbers == [27]


def test_demo_policy_register_blocks_are_parsed_with_real_statement_text():
    text = """
ENVIRONMENTAL COMMITMENTS
ENV-001 — Carbon Emissions Reduction
Apex Industrial Systems will reduce Scope 1 and Scope 2 carbon emissions by 30% from the 2024 baseline by 31 December 2026.
Accountable Owner: Sustainability Office
ENV-002 — Renewable Energy
The company will source at least 20% of electricity consumed across major operational facilities from renewable energy sources by 31 December 2026.
Accountable Owner: Energy Management Team
"""
    commitments, _warnings = extract_commitments(
        [{"page_number": 3, "extracted_text": text}],
        chunk_extractor=lambda _chunk: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    assert len(commitments) == 2
    env_001 = next(item for item in commitments if item.commitment_id == "ENV-001")
    assert "30%" in (env_001.target or "")
    assert "Scope 1 and Scope 2" in (env_001.policy_statement or "")
    assert env_001.responsible_owner == "Sustainability Office"


def test_section_headings_are_not_appended_to_fields():
    text = """
COMMITMENT ID: ENV-015
CATEGORY: Environmental
POLICY STATEMENT:
The Company shall maintain single-use plastic packaging below 5% of total packaging material by weight.
ESCALATION:
Deviation from the reduction trajectory shall be reported to Business Unit Leaders.
6.2 Social Commitments (SOC-001 – SOC-010)
COMMITMENT ID: SOC-001
CATEGORY: Social
POLICY STATEMENT:
The Company shall reduce the total recordable injury frequency rate by 35% by 2028 from a 2021 baseline.
ESCALATION:
Any fatality or serious injury shall be escalated immediately to the Chief Executive Officer.
"""
    parsed = parse_structured_commitments(text, [17])
    env = next(item for item in parsed if item["commitment_id"] == "ENV-015")
    assert "6.2" not in (env["escalation"] or "")
    assert "Social Commitments" not in (env["escalation"] or "")
    assert env["escalation"] == (
        "Deviation from the reduction trajectory shall be reported to Business Unit Leaders."
    )


def test_confidence_is_between_0_and_1():
    assert clamp_confidence(-1) == 0.0
    assert clamp_confidence(1.5) == 1.0
    assert clamp_confidence("0.99") == 0.99
    assert 0.0 <= clamp_confidence("bad") <= 1.0

    raw = {
        "policy_statement": "The Company shall disclose supplier audit results annually.",
        "source": {"page_numbers": [5], "evidence": "shall disclose supplier audit results"},
        "confidence": 2.5,
    }
    commitment = normalize_commitment(raw, [5])
    assert commitment is not None
    assert 0.0 <= commitment.confidence <= 1.0


def test_empty_to_null():
    assert empty_to_null("") is None
    assert empty_to_null("  ") is None
    assert empty_to_null("null") is None
    assert empty_to_null("10% by 2026") == "10% by 2026"


def test_mocked_llm_extraction_pipeline():
    pages = [
        {
            "page_number": 4,
            "extracted_text": (
                "The Company shall disclose supplier audit results annually "
                "and will publish the findings in the ESG report."
            ),
        }
    ]

    def fake_llm(chunk):
        assert 4 in chunk["page_numbers"]
        return [
            {
                "commitment_id": None,
                "category": None,
                "policy_statement": (
                    "The Company shall disclose supplier audit results annually "
                    "and will publish the findings in the ESG report."
                ),
                "source": {
                    "page_numbers": [4],
                    "evidence": "The Company shall disclose supplier audit results annually",
                },
                "confidence": 0.8,
            },
            {
                "commitment_id": None,
                "category": None,
                "policy_statement": (
                    "The Company shall disclose supplier audit results annually "
                    "and will publish the findings in the ESG report."
                ),
                "source": {"page_numbers": [4], "evidence": "duplicate"},
                "confidence": 0.7,
            },
        ]

    commitments, warnings = extract_commitments(pages, fake_llm)
    assert len(commitments) == 1
    assert commitments[0].commitment_id is None
    assert any("duplicate" in warning.lower() for warning in warnings)
