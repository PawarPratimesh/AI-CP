"""Automated Test Suite for Phase 4: Gemini-Powered Infrastructure Insights & Recommendations.

Covers the 10 required test scenarios:
1. Gemini successfully generating anomaly explanations.
2. Gemini generating optimization recommendations.
3. No anomalies detected (no fabricated findings).
4. No usable optimization opportunities / minimal data handling.
5. Gemini API timeout or failure (automatic fallback).
6. Malformed Gemini response (invalid JSON -> fallback).
7. Rule-based fallback working when Gemini is unavailable.
8. Invalid or expired upload ID (HTTP 404).
9. Ensuring AI output does not modify actual metrics (strict immutability).
10. End-to-end API response validation (POST and GET recommendations).
"""

import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

os.environ["TESTING"] = "1"

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.cloud_carbon.anomaly_detector import detect_infrastructure_anomalies
from app.cloud_carbon.carbon_estimator import estimate_energy_and_carbon
from app.cloud_carbon.recommendation_engine import (
    generate_cloud_carbon_insights,
    generate_rule_based_insights,
    prepare_infrastructure_summary,
)
from app.cloud_carbon.router import (
    generate_recommendations_endpoint,
    get_recommendations_endpoint,
    run_sustainability_analysis_endpoint,
    upload_metrics_file,
)
from app.cloud_carbon.schemas import (
    CanonicalRecord,
    CloudCarbonRecommendationsResponse,
    OptimizationRecommendationItem,
)
from app.cloud_carbon.session_store import (
    create_session,
    get_session,
    get_session_analysis,
    store_session_analysis,
)


def _make_upload_file(filename: str, content: bytes, content_type: str = "text/csv") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


class CloudCarbonPhase4TestCase(unittest.TestCase):
    """Test suite covering Gemini AI insights and rule-based recommendation fallback."""

    def setUp(self):
        # Create standard synthetic infrastructure dataset for session tests
        self.sample_records = [
            CanonicalRecord(
                timestamp=f"2026-03-01T{h:02d}:00:00Z",
                resource_id="srv-app-01",
                resource_type="Compute",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=82.5 if h == 12 else 45.0,
                memory_utilization_pct=55.0,
                network_in=100000.0,
                network_out=200000.0,
                storage_used=60.0,
                storage_capacity=100.0,
            )
            for h in range(14)
        ]
        # Add an underutilized server
        self.sample_records.extend([
            CanonicalRecord(
                timestamp=f"2026-03-01T{h:02d}:00:00Z",
                resource_id="srv-idle-worker",
                resource_type="Worker",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=3.2,
                memory_utilization_pct=20.0,
                network_in=5000.0,
                network_out=2000.0,
                storage_used=10.0,
                storage_capacity=100.0,
            )
            for h in range(14)
        ])

        cols = [
            "timestamp", "resource_id", "resource_type", "provider", "region",
            "cpu_utilization_pct", "memory_utilization_pct", "network_in",
            "network_out", "storage_used", "storage_capacity"
        ]

        self.upload_id = create_session(
            filename="test_fleet_telemetry.csv",
            file_format="CSV",
            detected_provider="AWS",
            columns=cols,
            raw_records=[r.model_dump() for r in self.sample_records],
            column_mapping={},
            preprocessed_result={
                "accepted": self.sample_records,
                "rejected_count": 0,
                "duplicate_count": 0,
                "errors": [],
                "available_metrics": ["cpu", "memory", "network", "storage"],
            },
        )

        # Run Phase 3 analysis to populate baseline session analysis
        self.anomaly_res = detect_infrastructure_anomalies(self.sample_records, self.upload_id)
        self.emissions_res = estimate_energy_and_carbon(self.sample_records, self.upload_id)
        store_session_analysis(self.upload_id, "anomaly_detection", self.anomaly_res.model_dump())
        store_session_analysis(self.upload_id, "emissions_estimation", self.emissions_res.model_dump())

    # 1. Gemini successfully generating anomaly explanations
    @patch("app.services.llm.generate_infrastructure_recommendations")
    def test_01_gemini_generates_anomaly_explanations(self, mock_llm):
        mock_llm.return_value = json.dumps({
            "summary": "Fleet exhibits healthy overall performance with one isolated CPU anomaly on srv-app-01.",
            "anomaly_explanations": [
                {
                    "resource_id": "srv-app-01",
                    "timestamp": "2026-03-01T12:00:00Z",
                    "metric": "CPU Utilization",
                    "observed_value": 82.5,
                    "baseline_context": "Typical CPU is ~45%",
                    "explanation": "Observed significant CPU utilization spike on srv-app-01.",
                    "possible_causes": "Heavy batch payload or unindexed database query execution.",
                    "operational_impact": "Potential latency degradation for concurrent client requests.",
                    "investigation_steps": "Review top CPU consumer processes and application request logs around 12:00 UTC."
                }
            ],
            "recommendations": [
                {
                    "title": "Rightsize Idle Worker Node",
                    "category": "Compute Rightsizing",
                    "target_resource": "srv-idle-worker",
                    "observation": "Average CPU utilization is 3.2% across all 14 observations.",
                    "action": "Downsize instance specification by 50% or consolidate onto shared nodes.",
                    "reason": "Idle baseline power is consumed without delivering computational output.",
                    "expected_benefit": "High",
                    "evidence": "Observed average 3.2% CPU utilization."
                },
                {
                    "title": "Configure Autoscaling for API Server",
                    "category": "Workload Optimization",
                    "target_resource": "srv-app-01",
                    "observation": "CPU reached peak 82.5% during mid-day batch window.",
                    "action": "Enable horizontal autoscaling with target threshold at 65% CPU.",
                    "reason": "Prevents compute queue buildup during sudden burst periods.",
                    "expected_benefit": "Medium",
                    "evidence": "Peak 82.5% CPU observed at 12:00 UTC."
                },
                {
                    "title": "Evaluate Low-Carbon Datacenter Migration",
                    "category": "Decarbonization",
                    "target_resource": "Fleet-wide",
                    "observation": "Fleet is hosted in us-east-1 with 0.379 kg CO2e/kWh grid intensity.",
                    "action": "Shift batch worker jobs to us-west-2 (0.198 kg CO2e/kWh).",
                    "reason": "Renewable hydro grid mix reduces Scope 2 location-based carbon emissions.",
                    "expected_benefit": "Medium",
                    "evidence": "us-east-1 grid factor is 0.379 kg/kWh."
                }
            ]
        })

        session = get_session(self.upload_id)
        result = generate_cloud_carbon_insights(
            upload_id=self.upload_id,
            session=session,
            anomaly_detection=self.anomaly_res.model_dump(),
            emissions_estimation=self.emissions_res.model_dump(),
            force_rule_based=False,
        )

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.generation_method, "GEMINI")
        self.assertGreaterEqual(len(result.anomaly_explanations), 1)
        exp = result.anomaly_explanations[0]
        self.assertEqual(exp.resource_id, "srv-app-01")
        self.assertEqual(exp.metric, "CPU Utilization")
        self.assertIn("Review top CPU consumer", exp.investigation_steps)

    # 2. Gemini generating optimization recommendations
    @patch("app.services.llm.generate_infrastructure_recommendations")
    def test_02_gemini_generates_optimization_recommendations(self, mock_llm):
        mock_llm.return_value = json.dumps({
            "summary": "Three practical optimization recommendations synthesized for AWS compute instances.",
            "anomaly_explanations": [],
            "recommendations": [
                {
                    "title": "Downsize Over-Provisioned Worker Nodes",
                    "category": "Compute Rightsizing",
                    "target_resource": "srv-idle-worker",
                    "observation": "Instances operate consistently below 5% CPU capacity.",
                    "action": "Downsize to smaller instance tier or migrate to scheduled serverless jobs.",
                    "reason": "Reduces fixed idle electricity consumption.",
                    "expected_benefit": "High",
                    "evidence": "Average CPU: 3.2% across 14 observations."
                },
                {
                    "title": "Migrate Batch Workloads to Low-Carbon Region",
                    "category": "Decarbonization",
                    "target_resource": "Fleet-wide",
                    "observation": "Workloads deployed in high-carbon grid intensity zone.",
                    "action": "Relocate batch queues to renewable-powered us-west-2 region.",
                    "reason": "Regional emission factor delta yields up to 48% carbon reduction.",
                    "expected_benefit": "Medium",
                    "evidence": "Grid intensity 0.379 kg/kWh vs 0.198 kg/kWh."
                },
                {
                    "title": "Implement Storage Lifecycle Policies",
                    "category": "Storage Lifecycle",
                    "target_resource": "srv-app-01",
                    "observation": "Storage capacity at 60% with accumulating log data.",
                    "action": "Transition objects older than 30 days to cold archive storage.",
                    "reason": "Lowers standard block storage capacity allocation.",
                    "expected_benefit": "Low",
                    "evidence": "60 GB active storage allocated."
                }
            ]
        })

        session = get_session(self.upload_id)
        result = generate_cloud_carbon_insights(
            upload_id=self.upload_id,
            session=session,
            anomaly_detection=self.anomaly_res.model_dump(),
            emissions_estimation=self.emissions_res.model_dump(),
            force_rule_based=False,
        )

        self.assertEqual(result.generation_method, "GEMINI")
        self.assertEqual(len(result.recommendations), 3)
        rec = result.recommendations[0]
        self.assertEqual(rec.category, "Compute Rightsizing")
        self.assertEqual(rec.expected_benefit, "High")
        self.assertIn("srv-idle-worker", rec.target_resource)

    # 3. No anomalies detected (clean dataset)
    @patch("app.services.llm.generate_infrastructure_recommendations")
    def test_03_no_anomalies_detected(self, mock_llm):
        # Empty anomaly list in input
        clean_anomaly_dict = {
            "upload_id": self.upload_id,
            "status": "SUCCESS",
            "features_used": ["cpu_utilization_pct"],
            "total_records_analyzed": 10,
            "anomalies_detected": 0,
            "normal_records": 10,
            "anomaly_percentage": 0.0,
            "methodology_note": "Isolation Forest",
            "attribution_note": "No outliers",
            "anomalies": [],
        }

        # Gemini should return empty anomaly_explanations and not hallucinate findings
        mock_llm.return_value = json.dumps({
            "summary": "All telemetry observations within normal variance.",
            "anomaly_explanations": [],
            "recommendations": [
                {
                    "title": "Maintain Baseline Monitoring",
                    "category": "Workload Optimization",
                    "target_resource": "Fleet-wide",
                    "observation": "Zero anomalous events detected.",
                    "action": "Continue automated threshold tracking.",
                    "reason": "Stability verified across all operational metrics.",
                    "expected_benefit": "Low",
                    "evidence": "100% normal observation distribution."
                },
                {
                    "title": "Adopt Renewable Grid Scheduling",
                    "category": "Decarbonization",
                    "target_resource": "Fleet-wide",
                    "observation": "Workloads run continuously.",
                    "action": "Schedule heavy jobs during solar peak windows.",
                    "reason": "Maximizes renewable energy utilization.",
                    "expected_benefit": "Medium",
                    "evidence": "Grid intensity 0.379 kg/kWh."
                }
            ]
        })

        session = get_session(self.upload_id)
        result = generate_cloud_carbon_insights(
            upload_id=self.upload_id,
            session=session,
            anomaly_detection=clean_anomaly_dict,
            emissions_estimation=self.emissions_res.model_dump(),
            force_rule_based=False,
        )

        self.assertEqual(len(result.anomaly_explanations), 0)

    # 4. No usable optimization opportunities / minimal data handling
    def test_04_no_usable_optimization_opportunities(self):
        empty_session = {
            "upload_id": "empty-session-id",
            "filename": "empty.csv",
            "preprocessed_result": {"accepted": []},
        }
        result = generate_cloud_carbon_insights(
            upload_id="empty-session-id",
            session=empty_session,
            anomaly_detection={},
            emissions_estimation={},
            force_rule_based=True,
        )
        self.assertEqual(result.status, "NO_OPPORTUNITIES")
        self.assertEqual(len(result.recommendations), 0)
        self.assertIsNotNone(result.warning_or_limitation)

    # 5. Gemini API timeout or failure triggers rule-based fallback
    @patch("app.services.llm.generate_infrastructure_recommendations")
    def test_05_gemini_api_timeout_or_failure_fallback(self, mock_llm):
        mock_llm.side_effect = TimeoutError("Gemini API call timed out after 30 seconds")

        session = get_session(self.upload_id)
        result = generate_cloud_carbon_insights(
            upload_id=self.upload_id,
            session=session,
            anomaly_detection=self.anomaly_res.model_dump(),
            emissions_estimation=self.emissions_res.model_dump(),
            force_rule_based=False,
        )

        self.assertEqual(result.generation_method, "RULE_BASED")
        self.assertIn("Gemini AI processing unavailable or timed out", result.warning_or_limitation)
        self.assertGreaterEqual(len(result.recommendations), 3)

    # 6. Malformed Gemini response triggers rule-based fallback
    @patch("app.services.llm.generate_infrastructure_recommendations")
    def test_06_malformed_gemini_response_fallback(self, mock_llm):
        mock_llm.return_value = "```json\n{\n  'unquoted_key': invalid json syntax...\n```"

        session = get_session(self.upload_id)
        result = generate_cloud_carbon_insights(
            upload_id=self.upload_id,
            session=session,
            anomaly_detection=self.anomaly_res.model_dump(),
            emissions_estimation=self.emissions_res.model_dump(),
            force_rule_based=False,
        )

        self.assertEqual(result.generation_method, "RULE_BASED")
        self.assertGreaterEqual(len(result.recommendations), 3)

    # 7. Rule-based fallback working when Gemini is unavailable
    def test_07_rule_based_fallback_working(self):
        summary_data = prepare_infrastructure_summary(
            records=self.sample_records,
            anomaly_detection=self.anomaly_res.model_dump(),
            emissions_estimation=self.emissions_res.model_dump(),
        )

        result = generate_rule_based_insights(
            upload_id=self.upload_id,
            summary_data=summary_data,
            warning_or_limitation="Deterministic fallback execution.",
        )

        self.assertEqual(result.generation_method, "RULE_BASED")
        self.assertGreaterEqual(len(result.recommendations), 3)
        self.assertLessEqual(len(result.recommendations), 5)

        # Check underutilized instance detection
        categories = [r.category for r in result.recommendations]
        self.assertIn("Compute Rightsizing", categories)

        # Check high-carbon region detection
        self.assertIn("Decarbonization", categories)

    # 8. Invalid or expired upload ID returns 404
    def test_08_invalid_and_expired_upload_ids(self):
        invalid_id = "00000000-0000-0000-0000-000000000000"
        with self.assertRaises(HTTPException) as cm:
            generate_recommendations_endpoint(upload_id=invalid_id)
        self.assertEqual(cm.exception.status_code, 404)

        with self.assertRaises(HTTPException) as cm2:
            get_recommendations_endpoint(upload_id=invalid_id)
        self.assertEqual(cm2.exception.status_code, 404)

    # 9. Ensuring AI output does not modify actual metrics (strict immutability)
    @patch("app.services.llm.generate_infrastructure_recommendations")
    def test_09_ensuring_ai_output_does_not_modify_actual_metrics(self, mock_llm):
        mock_llm.return_value = json.dumps({
            "summary": "AI attempting to hallucinate false numbers.",
            "anomaly_explanations": [],
            "recommendations": [
                {
                    "title": "Bogus Saving",
                    "category": "Compute Rightsizing",
                    "target_resource": "srv-app-01",
                    "observation": "Fake observation",
                    "action": "Fake action",
                    "reason": "Fake reason",
                    "expected_benefit": "High",
                    "evidence": "Fake evidence",
                    "estimated_impact": "Saves 99999 kWh and reduces carbon by 100%"
                },
                {
                    "title": "Bogus Action 2",
                    "category": "Decarbonization",
                    "target_resource": "Fleet-wide",
                    "observation": "Observation 2",
                    "action": "Action 2",
                    "reason": "Reason 2",
                    "expected_benefit": "Medium",
                    "evidence": "Evidence 2"
                }
            ]
        })

        # Capture metrics before recommendations
        session_before = get_session(self.upload_id)
        records_before = [
            (r.cpu_utilization_pct if hasattr(r, "cpu_utilization_pct") else r["cpu_utilization_pct"])
            for r in session_before["preprocessed_result"]["accepted"]
        ]
        energy_before = self.emissions_res.total_energy_kwh
        carbon_before = self.emissions_res.total_carbon_kgco2e

        # Run recommendations
        generate_recommendations_endpoint(upload_id=self.upload_id)

        # Verify underlying session and analysis metrics are completely unchanged
        session_after = get_session(self.upload_id)
        records_after = [
            (r.cpu_utilization_pct if hasattr(r, "cpu_utilization_pct") else r["cpu_utilization_pct"])
            for r in session_after["preprocessed_result"]["accepted"]
        ]
        cached_analysis = get_session_analysis(self.upload_id)

        self.assertEqual(records_before, records_after)
        self.assertEqual(cached_analysis["emissions_estimation"]["total_energy_kwh"], energy_before)
        self.assertEqual(cached_analysis["emissions_estimation"]["total_carbon_kgco2e"], carbon_before)

    # 10. End-to-end API response validation
    def test_10_end_to_end_api_validation(self):
        # 1. Upload sample CSV file
        csv_data = (
            "Timestamp,InstanceId,CPUUtilization,MemoryUtilization,NetworkIn,NetworkOut\n"
            "2026-03-01T00:00:00Z,i-001,8.0,40.0,1000,2000\n"
            "2026-03-01T01:00:00Z,i-001,7.5,41.0,1200,2100\n"
            "2026-03-01T02:00:00Z,i-001,9.0,39.0,900,1800\n"
            "2026-03-01T03:00:00Z,i-001,8.2,40.0,1100,2000\n"
            "2026-03-01T04:00:00Z,i-001,92.0,88.0,90000,120000\n"  # Deliberate outlier
            "2026-03-01T05:00:00Z,i-001,8.5,40.0,1050,1950\n"
            "2026-03-01T06:00:00Z,i-001,7.8,39.5,980,1900\n"
        ).encode("utf-8")

        upload_file = _make_upload_file("e2e_fleet.csv", csv_data)
        upload_resp = upload_metrics_file(file=upload_file)
        new_upload_id = upload_resp.upload_id

        # 2. Run analysis
        analysis_resp = run_sustainability_analysis_endpoint(new_upload_id)
        self.assertEqual(analysis_resp.upload_id, new_upload_id)

        # 3. Generate recommendations (force rule-based for deterministic CI)
        recs_post = generate_recommendations_endpoint(upload_id=new_upload_id, force_rule_based=True)
        self.assertIsInstance(recs_post, CloudCarbonRecommendationsResponse)
        self.assertEqual(recs_post.upload_id, new_upload_id)
        self.assertEqual(recs_post.generation_method, "RULE_BASED")
        self.assertGreaterEqual(len(recs_post.recommendations), 3)

        # 4. Retrieve recommendations via GET endpoint
        recs_get = get_recommendations_endpoint(upload_id=new_upload_id)
        self.assertEqual(recs_get.upload_id, new_upload_id)
        self.assertEqual(len(recs_get.recommendations), len(recs_post.recommendations))
        self.assertEqual(recs_get.recommendations[0].title, recs_post.recommendations[0].title)


if __name__ == "__main__":
    unittest.main()
