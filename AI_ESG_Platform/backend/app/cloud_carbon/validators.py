"""Data and File Validation Rules for Cloud & Carbon Ingestion."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
import math
import re
from typing import Any, Optional, Union

# 25 MB max upload limit
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024


class FileValidationError(Exception):
    """Raised when file upload fails structural or format validation."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_file_payload(filename: str, content_bytes: bytes) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Validate file extension, size, and parse content into raw row dictionaries.

    Returns:
      (file_format, raw_records, column_names)
    """
    if not filename:
        raise FileValidationError("No filename provided.")

    if not content_bytes or len(content_bytes.strip()) == 0:
        raise FileValidationError("The uploaded file is empty.")

    if len(content_bytes) > MAX_FILE_SIZE_BYTES:
        raise FileValidationError(
            f"File size exceeds 25 MB limit ({len(content_bytes) / (1024 * 1024):.1f} MB)."
        )

    # Determine format by extension and actual bytes
    lower_name = filename.lower()
    is_csv_ext = lower_name.endswith(".csv")
    is_json_ext = lower_name.endswith(".json")

    if not (is_csv_ext or is_json_ext):
        raise FileValidationError("Unsupported file extension. Only CSV and JSON files are accepted.")

    # Try decoding text with UTF-8 (handling BOM) or latin-1
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = content_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise FileValidationError("Failed to decode file. Please ensure it is saved in UTF-8 encoding.")

    text_stripped = text.strip()
    if not text_stripped:
        raise FileValidationError("The uploaded file contains no data.")

    # Parse JSON
    if is_json_ext or text_stripped.startswith(("[", "{")):
        try:
            parsed = json.loads(text_stripped)
        except json.JSONDecodeError as exc:
            if is_json_ext:
                raise FileValidationError(f"Malformed JSON syntax: {exc}")
            parsed = None

        if parsed is not None:
            return _extract_json_records(parsed)

    # Parse CSV
    if is_csv_ext or "\n" in text_stripped or "," in text_stripped:
        return _extract_csv_records(text)

    raise FileValidationError("File content could not be parsed as valid CSV or JSON.")


def _extract_json_records(parsed: Any) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Extract flat dictionaries from JSON payload."""
    records: list[dict[str, Any]] = []

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                records.append(item)
    elif isinstance(parsed, dict):
        # Look for common wrapper keys (e.g. {"records": [...]}, {"data": [...]}, {"MetricDataResults": [...]})
        for key in ("records", "data", "metrics", "MetricDataResults", "value", "items"):
            if key in parsed and isinstance(parsed[key], list):
                for item in parsed[key]:
                    if isinstance(item, dict):
                        records.append(item)
                break
        if not records:
            # Single object metric
            records.append(parsed)

    if not records:
        raise FileValidationError("JSON file does not contain a list of metric records or recognizable objects.")

    # Collect all unique keys as columns
    cols: list[str] = []
    seen = set()
    for r in records:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                cols.append(k)

    if not cols:
        raise FileValidationError("JSON records contain no key-value metric fields.")

    return "JSON", records, cols


def _extract_csv_records(text: str) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Extract flat dictionaries from CSV string."""
    try:
        sample = text[:4096]
        # Sniff delimiter safely
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except Exception:
            dialect = csv.excel

        reader = csv.DictReader(io.StringIO(text), dialect=dialect, strict=True)
        fieldnames = reader.fieldnames

        if not fieldnames or len(fieldnames) == 0:
            raise FileValidationError("CSV file contains no valid column headers.")

        # Clean BOM from headers if present
        clean_fieldnames = [str(f).lstrip("\ufeff").strip() for f in fieldnames if f]
        if not clean_fieldnames:
            raise FileValidationError("CSV file header row is empty or malformed.")

        records: list[dict[str, Any]] = []
        for row in reader:
            # Check if row has at least one non-empty value
            if any(v is not None and str(v).strip() != "" for v in row.values()):
                clean_row = {
                    str(k).lstrip("\ufeff").strip(): (v.strip() if isinstance(v, str) else v)
                    for k, v in row.items()
                    if k is not None
                }
                records.append(clean_row)

        if not records:
            raise FileValidationError("CSV file contains headers but no data rows.")

        return "CSV", records, clean_fieldnames

    except csv.Error as exc:
        raise FileValidationError(f"Malformed CSV: {exc}")


def parse_timestamp_utc(value: Any) -> tuple[Optional[str], Optional[str]]:
    """Parse various timestamp formats and normalize to ISO-8601 UTC.

    Returns:
      (iso_string, error_message)
    """
    if value is None:
        return None, "Timestamp is missing."

    val_str = str(value).strip()
    if not val_str:
        return None, "Timestamp is empty."

    # Epoch timestamp in seconds or milliseconds
    if re.match(r"^\d{10}(\.\d+)?$", val_str):
        try:
            dt = datetime.fromtimestamp(float(val_str), tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), None
        except Exception as exc:
            return None, f"Invalid unix timestamp: {exc}"
    elif re.match(r"^\d{13}$", val_str):
        try:
            dt = datetime.fromtimestamp(float(val_str) / 1000.0, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), None
        except Exception as exc:
            return None, f"Invalid epoch millisecond timestamp: {exc}"

    # Try ISO formats with z or timezone
    cleaned = val_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), None
    except Exception:
        pass

    # Common date formats
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(val_str, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), None
        except ValueError:
            continue

    return None, f"Unrecognized date/time format: '{val_str}'"


def parse_percentage_metric(value: Any, field_name: str) -> tuple[Optional[float], Optional[str]]:
    """Parse percentage value, normalize fractions (0-1 to 0-100), and validate bounds.

    Returns:
      (normalized_float, error_message)
    """
    if value is None or str(value).strip() in ("", "null", "none", "nan"):
        return None, None

    val_str = str(value).strip().rstrip("%")
    try:
        num = float(val_str)
    except (ValueError, TypeError):
        return None, f"Non-numeric value '{value}' for percentage field {field_name}."

    if math.isnan(num) or math.isinf(num):
        return None, f"Invalid numeric value ({num}) for {field_name}."

    # If represented as a fraction between 0.0 and 1.0 (and not exactly 0.0), scale to percentage
    # Note: 0.0 stays 0.0; if max values are <= 1.0, it's typically a fraction
    # However, if it's <= 1.0 and > 0.0, e.g., 0.85 -> 85.0%
    if 0.0 < num <= 1.0:
        num = num * 100.0

    if num < 0.0 or num > 100.0:
        return None, f"Percentage {field_name} value ({num:.2f}%) out of range [0, 100]."

    return round(num, 2), None


def parse_numeric_metric(value: Any, field_name: str) -> tuple[Optional[float], Optional[str]]:
    """Parse generic positive numeric metrics (network, storage).

    Returns:
      (normalized_float, error_message)
    """
    if value is None or str(value).strip() in ("", "null", "none", "nan"):
        return None, None

    # Strip common units if present (KB, MB, GB, B)
    val_str = str(value).strip()
    match = re.match(r"^([+-]?\d+(\.\d+)?)\s*([a-zA-Z]*)$", val_str)
    if match:
        val_str = match.group(1)

    try:
        num = float(val_str)
    except (ValueError, TypeError):
        return None, f"Non-numeric value '{value}' for field {field_name}."

    if math.isnan(num) or math.isinf(num):
        return None, f"Invalid float ({num}) for {field_name}."

    if num < 0.0:
        return None, f"Negative value ({num}) not permitted for metric {field_name}."

    return round(num, 2), None
