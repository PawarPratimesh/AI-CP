"""Tests for the Green Code Score calculator."""

from app.green.scorer import calculate_score


class TestGreenCodeScore:
    def test_no_findings_gives_perfect_score(self):
        result = calculate_score([])
        assert result["overall_score"] == 100.0
        assert result["finding_count"] == 0
        assert result["high_priority_count"] == 0

    def test_high_severity_reduces_dimension(self):
        findings = [{"severity": "high", "category": "network"}]
        result = calculate_score(findings)
        assert result["overall_score"] < 100.0
        dims = result["dimension_scores"]
        # Network dimension should drop by 15
        assert dims["network"] == 85.0
        # Other dimensions should be unaffected
        assert dims["database"] == 100.0
        assert result["high_priority_count"] == 1

    def test_multiple_findings_accumulate(self):
        findings = [
            {"severity": "high", "category": "network"},
            {"severity": "high", "category": "network"},
        ]
        result = calculate_score(findings)
        dims = result["dimension_scores"]
        assert dims["network"] == 70.0  # 100 - 15 - 15

    def test_severity_weights(self):
        """High=15, Medium=8, Low=3."""
        high = calculate_score([{"severity": "high", "category": "compute"}])
        med = calculate_score([{"severity": "medium", "category": "compute"}])
        low = calculate_score([{"severity": "low", "category": "compute"}])
        assert high["dimension_scores"]["compute"] == 85.0
        assert med["dimension_scores"]["compute"] == 92.0
        assert low["dimension_scores"]["compute"] == 97.0

    def test_score_clamped_to_zero(self):
        """Dimension score should not go below 0."""
        findings = [{"severity": "high", "category": "network"}] * 10
        result = calculate_score(findings)
        assert result["dimension_scores"]["network"] == 0.0  # 100 - 150, clamped to 0

    def test_overall_is_weighted_average(self):
        """Overall score = weighted sum of dimensions."""
        findings = [
            {"severity": "high", "category": "network"},  # network → 85
        ]
        result = calculate_score(findings)
        # Expected: 85*0.20 + 100*0.20 + 100*0.20 + 100*0.15 + 100*0.15 + 100*0.10
        # = 17 + 20 + 20 + 15 + 15 + 10 = 97
        assert result["overall_score"] == 97.0

    def test_counts_by_severity(self):
        findings = [
            {"severity": "high", "category": "network"},
            {"severity": "high", "category": "database"},
            {"severity": "medium", "category": "compute"},
            {"severity": "low", "category": "cicd"},
        ]
        result = calculate_score(findings)
        assert result["finding_count"] == 4
        assert result["high_priority_count"] == 2
        assert result["medium_priority_count"] == 1
        assert result["low_priority_count"] == 1

    def test_category_aliases(self):
        """Category aliases should map to correct dimensions."""
        findings = [{"severity": "high", "category": "api"}]
        result = calculate_score(findings)
        assert result["dimension_scores"]["network"] == 85.0

    def test_formula_string_present(self):
        result = calculate_score([])
        assert "formula" in result
        assert "weighted" in result["formula"].lower()

    def test_dimension_scores_json_is_valid(self):
        import json
        result = calculate_score([{"severity": "high", "category": "network"}])
        dims = json.loads(result["dimension_scores_json"])
        assert dims["network"] == 85.0
        assert dims["database"] == 100.0
