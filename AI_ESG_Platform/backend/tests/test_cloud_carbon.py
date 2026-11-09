"""Automated Backend Test Suite for Cloud & Carbon Data Ingestion and Preprocessing.

Covers 16 required edge cases and scenarios:
1. Valid AWS CloudWatch CSV upload
2. Valid Azure Monitor JSON upload
3. Valid Custom Server Logs CSV upload
4. Missing optional metrics (CPU only, CPU + Network)
5. Missing required structural fields (no timestamp, no resource_id -> 400)
6. Invalid numeric / percentage values (>100%, negative, non-numeric -> records_rejected)
7. Malformed CSV syntax
8. Malformed JSON syntax
9. Empty file (0 bytes and whitespace-only -> 400)
10. Duplicate record handling (same resource_id and timestamp -> duplicate_count incremented)
11. Ambiguous column mapping collision -> REQUIRES_CONFIRMATION
12. Unsupported file extensions (.pdf, .exe, .xlsx -> 400)
13. File size limit enforcement (> 25MB -> 400)
14. Canonical field normalization (ISO 8601 UTC, 0-100 float range)
15. Preview endpoint GET /api/cloud-carbon/preview/{upload_id}
16. Confirm mapping endpoint POST /api/cloud-carbon/confirm-mapping/{upload_id}
"""

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

from fastapi import FastAPI, UploadFile, HTTPException
from starlette.datastructures import Headers

from app.cloud_carbon.router import (
    router as cloud_carbon_router,
    upload_metrics_file,
    get_preview_data,
    confirm_column_mapping,
)
from app.cloud_carbon.column_mapper import normalize_header, map_columns
from app.cloud_carbon.validators import (
    FileValidationError,
    validate_file_payload,
    parse_timestamp_utc,
    parse_percentage_metric,
)
from app.cloud_carbon.preprocessor import preprocess_records
from app.cloud_carbon.schemas import ConfirmMappingRequest


def _make_upload_file(filename: str, content: bytes, content_type: str = "text/csv") -> UploadFile:
    """Helper to create an in-memory UploadFile for testing."""
    stream = io.BytesIO(content)
    headers = Headers({"content-type": content_type})
    return UploadFile(file=stream, filename=filename, headers=headers)


class CloudCarbonIngestionTestCase(unittest.TestCase):

    # ------------------------------------------------------------------------
    # 1. Valid AWS CloudWatch CSV
    # ------------------------------------------------------------------------
    def test_01_valid_aws_cloudwatch_csv(self):
        csv_content = (
            "Timestamp,InstanceId,CPUUtilization,MemoryUtilization,NetworkIn,NetworkOut,DiskReadBytes,Region\n"
            "2026-03-29T10:00:00Z,i-0a1b2c3d4e5f001,42.5,68.2,1250000,850000,45000000,us-east-1\n"
            "2026-03-29T10:05:00Z,i-0a1b2c3d4e5f001,45.1,68.9,1320000,890000,46000000,us-east-1\n"
        )
        uf = _make_upload_file("aws_metrics.csv", csv_content.encode("utf-8"), "text/csv")
        data = upload_metrics_file(file=uf)
        self.assertEqual(data.processing_status, "SUCCESS")
        self.assertEqual(data.detected_provider, "AWS")
        self.assertEqual(data.total_records, 2)
        self.assertEqual(data.accepted_records, 2)
        self.assertEqual(data.rejected_records, 0)
        self.assertIn("cpu", data.available_metrics)
        self.assertIn("memory", data.available_metrics)
        self.assertIn("network", data.available_metrics)

    # ------------------------------------------------------------------------
    # 2. Valid Azure Monitor JSON
    # ------------------------------------------------------------------------
    def test_02_valid_azure_monitor_json(self):
        records = [
            {
                "time": "2026-03-29T10:00:00.000Z",
                "resourceId": "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-prod-01",
                "Percentage CPU": 55.4,
                "Memory Utilization": 62.5,
                "Network In Total": 850000,
                "Network Out Total": 420000,
                "location": "eastus",
            },
            {
                "time": "2026-03-29T10:05:00.000Z",
                "resourceId": "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-prod-01",
                "Percentage CPU": 58.1,
                "Memory Utilization": 64.0,
                "Network In Total": 890000,
                "Network Out Total": 450000,
                "location": "eastus",
            },
        ]
        uf = _make_upload_file("azure_monitor.json", json.dumps(records).encode("utf-8"), "application/json")
        data = upload_metrics_file(file=uf)
        self.assertEqual(data.processing_status, "SUCCESS")
        self.assertEqual(data.detected_provider.upper(), "AZURE")
        self.assertEqual(data.total_records, 2)
        self.assertEqual(data.accepted_records, 2)

    # ------------------------------------------------------------------------
    # 3. Valid Custom Server Logs CSV
    # ------------------------------------------------------------------------
    def test_03_valid_custom_csv(self):
        csv_content = (
            "datetime,server_hostname,cpu_load_pct,mem_used_pct,bytes_in,bytes_out\n"
            "2026-03-29 12:00:00,baremetal-srv-01,78.5,82.1,5000000,3500000\n"
            "2026-03-29 12:05:00,baremetal-srv-01,81.0,82.4,5200000,3600000\n"
        )
        uf = _make_upload_file("custom_server.csv", csv_content.encode("utf-8"), "text/csv")
        data = upload_metrics_file(file=uf)
        self.assertEqual(data.processing_status, "SUCCESS")
        self.assertEqual(data.total_records, 2)
        self.assertEqual(data.accepted_records, 2)

    # ------------------------------------------------------------------------
    # 4. Missing Optional Metrics (CPU only dataset & CPU + Network)
    # ------------------------------------------------------------------------
    def test_04_missing_optional_metrics_cpu_only(self):
        csv_content = (
            "timestamp,resource_id,cpu_utilization\n"
            "2026-03-29T10:00:00Z,vm-cpu-only,35.0\n"
            "2026-03-29T10:05:00Z,vm-cpu-only,38.0\n"
        )
        uf = _make_upload_file("cpu_only.csv", csv_content.encode("utf-8"), "text/csv")
        data = upload_metrics_file(file=uf)
        self.assertEqual(data.processing_status, "SUCCESS")
        self.assertIn("cpu", data.available_metrics)
        self.assertIn("memory", data.missing_metrics)
        self.assertIn("network", data.missing_metrics)
        self.assertIn("storage", data.missing_metrics)

    # ------------------------------------------------------------------------
    # 5. Missing Required Structural Fields (no timestamp or no resource_id -> 400)
    # ------------------------------------------------------------------------
    def test_05_missing_timestamp_column_fails(self):
        csv_content = "resource_id,cpu_utilization\nvm-test,50.0\n"
        uf = _make_upload_file("no_timestamp.csv", csv_content.encode("utf-8"), "text/csv")
        with self.assertRaises(HTTPException) as ctx:
            upload_metrics_file(file=uf)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("timestamp", str(ctx.exception.detail).lower())

    def test_05b_missing_resource_id_column_fails(self):
        csv_content = "timestamp,cpu_utilization\n2026-03-29T10:00:00Z,50.0\n"
        uf = _make_upload_file("no_resource_id.csv", csv_content.encode("utf-8"), "text/csv")
        with self.assertRaises(HTTPException) as ctx:
            upload_metrics_file(file=uf)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("resource", str(ctx.exception.detail).lower())

    # ------------------------------------------------------------------------
    # 6. Invalid Numeric and Percentage Values (>100% or negative or corrupt)
    # ------------------------------------------------------------------------
    def test_06_invalid_numeric_values_rejected(self):
        csv_content = (
            "timestamp,resource_id,cpu_utilization\n"
            "2026-03-29T10:00:00Z,vm-val-1,50.0\n"          # Valid
            "2026-03-29T10:05:00Z,vm-val-1,150.0\n"         # Invalid (>100%)
            "2026-03-29T10:10:00Z,vm-val-1,-5.0\n"          # Invalid (negative)
            "2026-03-29T10:15:00Z,vm-val-1,invalid_num\n"   # Invalid (string)
            "corrupt_timestamp,vm-val-1,50.0\n"             # Invalid timestamp
        )
        uf = _make_upload_file("invalid_vals.csv", csv_content.encode("utf-8"), "text/csv")
        data = upload_metrics_file(file=uf)
        self.assertEqual(data.total_records, 5)
        self.assertEqual(data.accepted_records, 1)
        self.assertEqual(data.rejected_records, 4)
        self.assertGreater(len(data.validation_errors), 0)

    # ------------------------------------------------------------------------
    # 7. Malformed CSV Syntax (Unbalanced quotes / corrupt row)
    # ------------------------------------------------------------------------
    def test_07_malformed_csv_syntax(self):
        malformed_csv = b'timestamp,resource_id,cpu\n"unclosed quote,res1,50'
        uf = _make_upload_file("broken.csv", malformed_csv, "text/csv")
        with self.assertRaises(HTTPException) as ctx:
            upload_metrics_file(file=uf)
        self.assertEqual(ctx.exception.status_code, 400)

    # ------------------------------------------------------------------------
    # 8. Malformed JSON Syntax (Truncated JSON)
    # ------------------------------------------------------------------------
    def test_08_malformed_json_syntax(self):
        malformed_json = b'[{"timestamp": "2026-03-29T10:00:00Z", "resource_id": "res-1"'
        uf = _make_upload_file("broken.json", malformed_json, "application/json")
        with self.assertRaises(HTTPException) as ctx:
            upload_metrics_file(file=uf)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("json", str(ctx.exception.detail).lower())

    # ------------------------------------------------------------------------
    # 9. Empty File and Whitespace-only File (0 bytes -> 400)
    # ------------------------------------------------------------------------
    def test_09_empty_file_zero_bytes(self):
        uf = _make_upload_file("empty.csv", b"", "text/csv")
        with self.assertRaises(HTTPException) as ctx:
            upload_metrics_file(file=uf)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("empty", str(ctx.exception.detail).lower())

    def test_09b_whitespace_only_file(self):
        uf = _make_upload_file("whitespace.csv", b"   \n\r\t   \n", "text/csv")
        with self.assertRaises(HTTPException) as ctx:
            upload_metrics_file(file=uf)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("empty", str(ctx.exception.detail).lower())

    # ------------------------------------------------------------------------
    # 10. Duplicate Record Handling (same resource_id and timestamp)
    # ------------------------------------------------------------------------
    def test_10_duplicate_record_handling(self):
        csv_content = (
            "timestamp,resource_id,cpu_utilization\n"
            "2026-03-29T10:00:00Z,vm-dup-01,30.0\n"
            "2026-03-29T10:00:00Z,vm-dup-01,35.0\n"  # Duplicate resource_id + timestamp
            "2026-03-29T10:05:00Z,vm-dup-01,40.0\n"
        )
        uf = _make_upload_file("duplicates.csv", csv_content.encode("utf-8"), "text/csv")
        data = upload_metrics_file(file=uf)
        self.assertEqual(data.accepted_records, 2)
        self.assertEqual(data.duplicate_records, 1)

    # ------------------------------------------------------------------------
    # 11. Ambiguous Column Mapping Collision
    # ------------------------------------------------------------------------
    def test_11_ambiguous_column_mapping_requires_confirmation(self):
        # File has both 'CPUUtilization' and 'cpu_percent' which both map to cpu_utilization_pct
        csv_content = (
            "timestamp,resource_id,CPUUtilization,cpu_percent\n"
            "2026-03-29T10:00:00Z,vm-ambig-01,45.0,46.0\n"
        )
        uf = _make_upload_file("ambiguous.csv", csv_content.encode("utf-8"), "text/csv")
        data = upload_metrics_file(file=uf)
        self.assertEqual(data.processing_status, "REQUIRES_CONFIRMATION")
        self.assertGreater(len(data.ambiguous_columns), 0)
        self.assertTrue(bool(data.upload_id))

    # ------------------------------------------------------------------------
    # 12. Unsupported File Extensions (.pdf, .exe, .xlsx -> 400)
    # ------------------------------------------------------------------------
    def test_12_unsupported_file_extensions(self):
        unsupported = [
            ("report.pdf", b"%PDF-1.4 ...", "application/pdf"),
            ("installer.exe", b"MZ...", "application/octet-stream"),
            ("metrics.xlsx", b"PK...", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("data.parquet", b"PAR1...", "application/octet-stream"),
        ]
        for filename, content, mime in unsupported:
            uf = _make_upload_file(filename, content, mime)
            with self.assertRaises(HTTPException) as ctx:
                upload_metrics_file(file=uf)
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("unsupported", str(ctx.exception.detail).lower())

    # ------------------------------------------------------------------------
    # 13. File Size Limit Enforcement (> 25MB -> 400)
    # ------------------------------------------------------------------------
    def test_13_file_size_limit_exceeded(self):
        large_bytes = b"0" * (25 * 1024 * 1024 + 10)
        with self.assertRaises(FileValidationError) as ctx:
            validate_file_payload("test.csv", large_bytes)
        self.assertIn("exceeds", str(ctx.exception.message).lower())

    # ------------------------------------------------------------------------
    # 14. Canonical Field Integrity (Strict UTC ISO-8601 & 0-100 float range)
    # ------------------------------------------------------------------------
    def test_14_canonical_normalization_integrity(self):
        # 1. Unix timestamp parsed to UTC ISO-8601
        dt_str, err = parse_timestamp_utc(1700000000)
        self.assertIsNone(err)
        self.assertTrue(dt_str.endswith("Z"))
        self.assertEqual(dt_str, "2023-11-14T22:13:20Z")

        # 2. Decimal ratio percentage (0.68) scaled to 68.0
        pct_val, err_pct = parse_percentage_metric(0.68, "cpu")
        self.assertIsNone(err_pct)
        self.assertEqual(pct_val, 68.0)

        # 3. Standard percentage (68.0) preserved
        pct_val2, err_pct2 = parse_percentage_metric(68.0, "cpu")
        self.assertIsNone(err_pct2)
        self.assertEqual(pct_val2, 68.0)

    # ------------------------------------------------------------------------
    # 15. Preview Endpoint GET /api/cloud-carbon/preview/{upload_id}
    # ------------------------------------------------------------------------
    def test_15_preview_endpoint(self):
        csv_content = (
            "timestamp,resource_id,cpu_utilization,memory_utilization\n"
            "2026-03-29T10:00:00Z,vm-preview-01,25.0,50.0\n"
            "2026-03-29T10:05:00Z,vm-preview-01,30.0,52.0\n"
        )
        uf = _make_upload_file("preview_test.csv", csv_content.encode("utf-8"), "text/csv")
        upload_data = upload_metrics_file(file=uf)
        upload_id = upload_data.upload_id

        pdata = get_preview_data(upload_id)
        self.assertEqual(pdata.upload_id, upload_id)
        self.assertEqual(pdata.total_records, 2)
        self.assertEqual(len(pdata.preview_records), 2)
        self.assertEqual(pdata.preview_records[0].resource_id, "vm-preview-01")
        self.assertEqual(pdata.preview_records[0].cpu_utilization_pct, 25.0)

    # ------------------------------------------------------------------------
    # 16. Confirm Mapping Endpoint POST /api/cloud-carbon/confirm-mapping/{upload_id}
    # ------------------------------------------------------------------------
    def test_16_confirm_mapping_endpoint(self):
        # Upload ambiguous dataset
        csv_content = (
            "timestamp,resource_id,CPUUtilization,cpu_percent\n"
            "2026-03-29T10:00:00Z,vm-conf-01,45.0,46.0\n"
        )
        uf = _make_upload_file("ambig_for_confirm.csv", csv_content.encode("utf-8"), "text/csv")
        data = upload_metrics_file(file=uf)
        self.assertEqual(data.processing_status, "REQUIRES_CONFIRMATION")
        upload_id = data.upload_id

        # Confirm mapping: select CPUUtilization as cpu_utilization_pct, ignore cpu_percent
        confirm_req = ConfirmMappingRequest(
            mapping={
                "timestamp": "timestamp",
                "resource_id": "resource_id",
                "CPUUtilization": "cpu_utilization_pct",
                "cpu_percent": None,
            }
        )
        cdata = confirm_column_mapping(upload_id, confirm_req)
        self.assertEqual(cdata.processing_status, "SUCCESS")
        self.assertEqual(cdata.accepted_records, 1)
        self.assertIn("cpu", cdata.available_metrics)


if __name__ == "__main__":
    unittest.main()
