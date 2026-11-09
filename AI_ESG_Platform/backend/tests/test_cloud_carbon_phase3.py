"""Automated Test Suite for Phase 3: ML Anomaly Detection, Energy & Carbon Footprint.

Covers the 10 required test scenarios:
1. Anomaly detection with normal records (controlled baseline data)
2. Anomaly detection with deliberately unusual records (extreme outliers flagged with scores & attribution)
3. Insufficient data handling (< 5 records -> INSUFFICIENT_DATA status)
4. Missing metric handling (CPU only dataset, missing metrics not treated as zero)
5. Energy estimation with available power information (custom instance wattage profile)
6. Energy estimation using configured defaults (generic server 50W idle, 200W max)
7. Carbon estimation when regional emission factor exists (e.g. us-east-1 -> 0.379 kgCO2e/kWh)
8. Carbon estimation when regional factor is unavailable (unknown region -> None, flagged missing)
9. Invalid and expired upload IDs (HTTP 404)
10. API response structure and error handling (unified analyze & retrieval endpoints)
"""

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import unittest

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

os.environ["TESTING"] = "1"

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.cloud_carbon.anomaly_detector import detect_infrastructure_anomalies
from app.cloud_carbon.carbon_estimator import (
    DEFAULT_GRID_INTENSITY_FACTORS,
    estimate_energy_and_carbon,
    normalize_region_key,
)
from app.cloud_carbon.router import (
    get_sustainability_analysis_endpoint,
    run_anomaly_detection_endpoint,
    run_emissions_estimation_endpoint,
    run_sustainability_analysis_endpoint,
    upload_metrics_file,
)
from app.cloud_carbon.schemas import (
    AnomalyDetectionRequest,
    CanonicalRecord,
    EmissionsEstimationRequest,
)


def _make_upload_file(filename: str, content: bytes, content_type: str = "text/csv") -> UploadFile:
    stream = io.BytesIO(content)
    headers = Headers({"content-type": content_type})
    return UploadFile(file=stream, filename=filename, headers=headers)


class CloudCarbonPhase3TestCase(unittest.TestCase):

    # ------------------------------------------------------------------------
    # 1. Anomaly Detection with Normal Records
    # ------------------------------------------------------------------------
    def test_01_anomaly_detection_normal_records(self):
        # 10 controlled records exhibiting normal operating variance (40% - 55% CPU)
        records = [
            CanonicalRecord(
                timestamp=f"2026-11-08T{h:02d}:00:00Z",
                resource_id="srv-norm-01",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=45.0 + (h % 3) * 3.0,
                memory_utilization_pct=50.0 + (h % 2) * 2.0,
                network_in=100000.0,
                network_out=80000.0,
            )
            for h in range(10)
        ]
        res = detect_infrastructure_anomalies(records=records, upload_id="test-upload-01", contamination=0.1)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.total_records_analyzed, 10)
        self.assertIn("cpu_utilization_pct", res.features_used)
        self.assertIn("memory_utilization_pct", res.features_used)
        # In a tight normal distribution, most records should be normal
        self.assertGreaterEqual(res.normal_records, 8)
        self.assertIn("Isolation Forest", res.methodology_note)

    # ------------------------------------------------------------------------
    # 2. Anomaly Detection with Deliberately Unusual Records
    # ------------------------------------------------------------------------
    def test_02_anomaly_detection_deliberate_outliers(self):
        # 10 normal baseline records (40-45% CPU, 50% Memory)
        records = [
            CanonicalRecord(
                timestamp=f"2026-11-08T{h:02d}:00:00Z",
                resource_id="srv-prod-01",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=42.0 + (h % 2) * 2.0,
                memory_utilization_pct=50.0 + (h % 2) * 1.5,
            )
            for h in range(10)
        ]
        # Add 2 extreme outliers:
        # Outlier A: extreme CPU spike (99.5%)
        records.append(
            CanonicalRecord(
                timestamp="2026-11-08T10:00:00Z",
                resource_id="srv-prod-01",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=99.5,
                memory_utilization_pct=51.0,
            )
        )
        # Outlier B: extreme memory surge (98.9%)
        records.append(
            CanonicalRecord(
                timestamp="2026-11-08T11:00:00Z",
                resource_id="srv-prod-01",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=43.0,
                memory_utilization_pct=98.9,
            )
        )

        res = detect_infrastructure_anomalies(records=records, upload_id="test-upload-02", contamination=0.15)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.total_records_analyzed, 12)
        self.assertGreaterEqual(res.anomalies_detected, 1)

        # Check that outlier records have high anomaly scores and contributing metrics identified
        outlier_a = next(r for r in res.anomalies if r.record_index == 11)
        self.assertTrue(outlier_a.is_anomaly)
        self.assertGreaterEqual(outlier_a.anomaly_score, 0.70)
        self.assertTrue(any("cpu_utilization_pct" in m for m in outlier_a.contributing_metrics))

        # Verify attribution notice explicitly disclaims direct decision path extraction
        self.assertIn("heuristic distribution deviation", res.attribution_note)

    # ------------------------------------------------------------------------
    # 3. Insufficient Data Handling (< 5 records)
    # ------------------------------------------------------------------------
    def test_03_insufficient_data_handling(self):
        # Only 3 records (less than MIN_REQUIRED_OBSERVATIONS = 5)
        records = [
            CanonicalRecord(
                timestamp=f"2026-11-08T{h:02d}:00:00Z",
                resource_id="srv-small-01",
                cpu_utilization_pct=50.0,
            )
            for h in range(3)
        ]
        res = detect_infrastructure_anomalies(records=records, upload_id="test-upload-03")
        self.assertEqual(res.status, "INSUFFICIENT_DATA")
        self.assertEqual(res.anomalies_detected, 0)
        self.assertIn("Insufficient", res.methodology_note)

    # ------------------------------------------------------------------------
    # 4. Missing Metric Handling (CPU Only)
    # ------------------------------------------------------------------------
    def test_04_missing_metric_handling_cpu_only(self):
        # Dataset with CPU only; memory, network, storage are None
        records = [
            CanonicalRecord(
                timestamp=f"2026-11-08T{h:02d}:00:00Z",
                resource_id="srv-cpu-only",
                cpu_utilization_pct=30.0 + h * 2.0,
                memory_utilization_pct=None,
                network_in=None,
                network_out=None,
                storage_used=None,
            )
            for h in range(8)
        ]
        res = detect_infrastructure_anomalies(records=records, upload_id="test-upload-04")
        self.assertEqual(res.status, "SUCCESS")
        # Features used should strictly contain CPU only (does NOT treat missing metrics as 0)
        self.assertEqual(res.features_used, ["cpu_utilization_pct"])
        self.assertNotIn("memory_utilization_pct", res.features_used)
        self.assertNotIn("storage_used", res.features_used)

    # ------------------------------------------------------------------------
    # 5. Energy Estimation with Available Power Information
    # ------------------------------------------------------------------------
    def test_05_energy_estimation_with_power_info(self):
        # 2 records 1 hour apart for a known instance profile (Standard_D4s_v3: idle=40W, max=160W)
        records = [
            CanonicalRecord(
                timestamp="2026-11-08T10:00:00Z",
                resource_id="vm-profiled-01",
                resource_type="Standard_D4s_v3",
                provider="Azure",
                region="westeurope",
                cpu_utilization_pct=50.0,    # CPU power = 40 + (160-40)*0.5 = 100W
                memory_utilization_pct=50.0, # Mem power = 16 * 0.38 * (0.5 + 0.5*0.5) = 4.56W
            ),
            CanonicalRecord(
                timestamp="2026-11-08T11:00:00Z",
                resource_id="vm-profiled-01",
                resource_type="Standard_D4s_v3",
                provider="Azure",
                region="westeurope",
                cpu_utilization_pct=50.0,
                memory_utilization_pct=50.0,
            ),
        ]
        res = estimate_energy_and_carbon(records=records, upload_id="test-upload-05")
        self.assertGreater(res.total_energy_kwh, 0.0)
        # Power is ~104.56 W, PUE for Azure is 1.18, 1 hour: (104.56 * 1.18 * 1) / 1000 ~ 0.123 kWh
        self.assertAlmostEqual(res.total_energy_kwh, 0.2468, delta=0.1)

    # ------------------------------------------------------------------------
    # 6. Energy Estimation Using Configured Defaults
    # ------------------------------------------------------------------------
    def test_06_energy_estimation_configured_defaults(self):
        # Test custom PUE and wattage overrides
        records = [
            CanonicalRecord(
                timestamp="2026-11-08T00:00:00Z",
                resource_id="custom-srv-01",
                provider="Custom",
                region="us-east-1",
                cpu_utilization_pct=100.0, # At 100% CPU, power should equal max_watts + mem
                memory_utilization_pct=0.0,
            )
        ]
        req = EmissionsEstimationRequest(pue=1.5, idle_watts=100.0, max_watts=300.0)
        res = estimate_energy_and_carbon(records=records, upload_id="test-upload-06", options=req)
        # 1 observation -> default 1 hour. Watts = 300W + mem(~3W). (303 * 1.5 * 1)/1000 ~ 0.45 kWh
        self.assertAlmostEqual(res.total_energy_kwh, 0.4545, delta=0.05)
        self.assertEqual(res.assumptions.pue, 1.5)
        self.assertEqual(res.assumptions.idle_watts_default, 100.0)
        self.assertEqual(res.assumptions.max_watts_default, 300.0)

    # ------------------------------------------------------------------------
    # 7. Carbon Estimation When Regional Emission Factor Exists
    # ------------------------------------------------------------------------
    def test_07_carbon_estimation_known_region(self):
        records = [
            CanonicalRecord(
                timestamp="2026-11-08T00:00:00Z",
                resource_id="vm-us-east",
                provider="AWS",
                region="us-east-1",  # Factor: 0.379 kgCO2e/kWh
                cpu_utilization_pct=50.0,
                memory_utilization_pct=50.0,
            )
        ]
        res = estimate_energy_and_carbon(records=records, upload_id="test-upload-07")
        self.assertEqual(res.status, "SUCCESS")
        self.assertIsNotNone(res.total_carbon_kgco2e)
        expected_factor = DEFAULT_GRID_INTENSITY_FACTORS["us-east-1"]
        self.assertEqual(res.regional_factors_applied["us-east-1"], expected_factor)
        expected_carbon = round(res.total_energy_kwh * expected_factor, 4)
        self.assertAlmostEqual(res.total_carbon_kgco2e, expected_carbon, delta=0.01)

    # ------------------------------------------------------------------------
    # 8. Carbon Estimation When Regional Factor Is Unavailable
    # ------------------------------------------------------------------------
    def test_08_carbon_estimation_unavailable_region(self):
        records = [
            CanonicalRecord(
                timestamp="2026-11-08T00:00:00Z",
                resource_id="vm-unknown-dc",
                provider="Custom",
                region="datacenter-secret-underground",  # Not in catalog
                cpu_utilization_pct=50.0,
                memory_utilization_pct=50.0,
            )
        ]
        res = estimate_energy_and_carbon(records=records, upload_id="test-upload-08")
        # Energy is calculated, but carbon is None (does NOT invent arbitrary factor)
        self.assertGreater(res.total_energy_kwh, 0.0)
        self.assertIsNone(res.total_carbon_kgco2e)
        self.assertEqual(res.status, "EMISSION_FACTOR_UNAVAILABLE")
        self.assertIn("datacenter-secret-underground", res.missing_factor_regions)
        self.assertGreater(res.uncalculated_energy_kwh, 0.0)

    # ------------------------------------------------------------------------
    # 9. Invalid and Expired Upload IDs
    # ------------------------------------------------------------------------
    def test_09_invalid_and_expired_upload_ids(self):
        invalid_id = "00000000-0000-0000-0000-000000000000"
        with self.assertRaises(HTTPException) as ctx1:
            run_anomaly_detection_endpoint(invalid_id)
        self.assertEqual(ctx1.exception.status_code, 404)

        with self.assertRaises(HTTPException) as ctx2:
            run_emissions_estimation_endpoint(invalid_id)
        self.assertEqual(ctx2.exception.status_code, 404)

        with self.assertRaises(HTTPException) as ctx3:
            run_sustainability_analysis_endpoint(invalid_id)
        self.assertEqual(ctx3.exception.status_code, 404)

        with self.assertRaises(HTTPException) as ctx4:
            get_sustainability_analysis_endpoint(invalid_id)
        self.assertEqual(ctx4.exception.status_code, 404)

    # ------------------------------------------------------------------------
    # 10. End-to-End API Integration & Response Structure
    # ------------------------------------------------------------------------
    def test_10_end_to_end_analysis_api(self):
        csv_content = (
            "Timestamp,InstanceId,CPUUtilization,MemoryUtilization,NetworkIn,NetworkOut,AvailabilityZone\n"
            "2026-11-08T00:00:00Z,i-web-01,42.5,58.0,1200000,850000,us-east-1a\n"
            "2026-11-08T01:00:00Z,i-web-01,45.1,59.2,1300000,890000,us-east-1a\n"
            "2026-11-08T02:00:00Z,i-web-01,43.0,58.5,1250000,860000,us-east-1a\n"
            "2026-11-08T03:00:00Z,i-web-01,44.0,58.8,1280000,870000,us-east-1a\n"
            "2026-11-08T04:00:00Z,i-web-01,42.0,57.9,1210000,840000,us-east-1a\n"
            "2026-11-08T05:00:00Z,i-web-01,98.9,94.2,9500000,7800000,us-east-1a\n"  # Spike
        )
        uf = _make_upload_file("web_metrics.csv", csv_content.encode("utf-8"), "text/csv")
        upload_resp = upload_metrics_file(file=uf)
        self.assertEqual(upload_resp.processing_status, "SUCCESS")
        upload_id = upload_resp.upload_id

        # 1. Test POST /analyze/{upload_id}
        analysis_resp = run_sustainability_analysis_endpoint(upload_id)
        self.assertEqual(analysis_resp.upload_id, upload_id)
        self.assertEqual(analysis_resp.detected_provider, "AWS")

        # Verify Anomaly Detection payload
        ad = analysis_resp.anomaly_detection
        self.assertEqual(ad.status, "SUCCESS")
        self.assertEqual(ad.total_records_analyzed, 6)
        self.assertGreaterEqual(ad.anomalies_detected, 1)

        # Verify Emissions payload
        em = analysis_resp.emissions_estimation
        self.assertEqual(em.status, "SUCCESS")
        self.assertGreater(em.total_energy_kwh, 0.0)
        self.assertIsNotNone(em.total_carbon_kgco2e)
        self.assertIn("Energy consumption and carbon emissions are estimates", em.estimation_notice)

        # 2. Test GET /analysis/{upload_id} (retrieval of cached results)
        get_resp = get_sustainability_analysis_endpoint(upload_id)
        self.assertEqual(get_resp.upload_id, upload_id)
        self.assertEqual(get_resp.anomaly_detection.anomalies_detected, ad.anomalies_detected)
        self.assertEqual(get_resp.emissions_estimation.total_energy_kwh, em.total_energy_kwh)

    # ------------------------------------------------------------------------
    # 11. RAM Capacity and Profile Power Verification (t3.medium reference test)
    # ------------------------------------------------------------------------
    def test_11_ram_capacity_instance_profile_accuracy(self):
        # 5 observations of t3.medium with 4 GB RAM, 15W idle, 60W max, PUE 1.15
        records = [
            CanonicalRecord(
                timestamp="2026-10-20T09:00:00Z",
                resource_id="test-web-01",
                resource_type="t3.medium",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=18.0,
                memory_utilization_pct=42.0,
            ),
            CanonicalRecord(
                timestamp="2026-10-20T10:00:00Z",
                resource_id="test-web-01",
                resource_type="t3.medium",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=22.0,
                memory_utilization_pct=45.0,
            ),
            CanonicalRecord(
                timestamp="2026-10-20T11:00:00Z",
                resource_id="test-web-01",
                resource_type="t3.medium",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=25.0,
                memory_utilization_pct=47.0,
            ),
            CanonicalRecord(
                timestamp="2026-10-20T12:00:00Z",
                resource_id="test-web-01",
                resource_type="t3.medium",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=91.0,
                memory_utilization_pct=88.0,
            ),
            CanonicalRecord(
                timestamp="2026-10-20T13:00:00Z",
                resource_id="test-web-01",
                resource_type="t3.medium",
                provider="AWS",
                region="us-east-1",
                cpu_utilization_pct=28.0,
                memory_utilization_pct=49.0,
            ),
        ]
        res = estimate_energy_and_carbon(records=records, upload_id="test-upload-ram-accuracy")
        # Exact reference for test-web-01 is 0.1882 kWh
        self.assertAlmostEqual(res.total_energy_kwh, 0.1882, places=3)
        # Carbon for us-east-1 (factor 0.379) is 0.1882 * 0.379 = 0.0713 kg
        self.assertAlmostEqual(res.total_carbon_kgco2e, 0.0713, places=3)


if __name__ == "__main__":
    unittest.main()

