import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from recommendation_engine import _parse_recommendation_payload, generate_recommendations


def test_recommendations_work_without_api_key(monkeypatch):
    monkeypatch.setattr("recommendation_engine._load_runtime_env", lambda: None)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    recs, warnings = generate_recommendations([{
        "category": "ENVIRONMENTAL", "classification": "WEAKENED",
        "risk_score": 70, "risk_level": "HIGH"
    }], use_ai=True)
    assert len(recs) == 1
    assert recs[0]["source"] == "deterministic_fallback"
    assert "weakened" in recs[0]["title"].lower()
    assert "commitment" in recs[0]["action"].lower()
    assert warnings


def test_recommendation_payload_accepts_markdown_json():
    payload = _parse_recommendation_payload(
        "```json\n{\"recommendations\": []}\n```"
    )
    assert payload == {"recommendations": []}


def test_recommendation_payload_extracts_json_from_surrounding_text():
    payload = _parse_recommendation_payload(
        "Here is the requested result:\n{\"recommendations\": []}\nDone."
    )
    assert payload == {"recommendations": []}


def test_recommendation_payload_recovers_valid_items_from_extra_closing_braces():
    payload = _parse_recommendation_payload(
        '{"recommendations":[{"title":"ENV-001","priority":"HIGH","action":"Restore 25%","basis":"Risk"}}},{"title":"SOC-001","priority":"MEDIUM","action":"Track survey","basis":"Risk"}}}]}'
    )
    assert len(payload["recommendations"]) == 2
    assert payload["recommendations"][0]["title"] == "ENV-001"
    assert payload["recommendations"][1]["title"] == "SOC-001"
