"""Flexible Column Mapping for Infrastructure Sustainability Metrics.

Supports AWS CloudWatch, Azure Monitor, and Custom Server Logs via:
1. Header normalization.
2. Deterministic alias dictionary lookup.
3. Ambiguity and conflict detection.
4. Optional Gemini-assisted mapping suggestions for unfamiliar schemas.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from app.cloud_carbon.schemas import ColumnMappingItem

logger = logging.getLogger(__name__)

# Standard canonical fields
CANONICAL_FIELDS = {
    "timestamp",
    "resource_id",
    "resource_type",
    "provider",
    "region",
    "cpu_utilization_pct",
    "memory_utilization_pct",
    "network_in",
    "network_out",
    "storage_used",
    "storage_capacity",
}

# Metric dimensions mapping to canonical fields
METRIC_FIELD_MAP = {
    "cpu": "cpu_utilization_pct",
    "memory": "memory_utilization_pct",
    "network": ["network_in", "network_out"],
    "storage": ["storage_used", "storage_capacity"],
}

# Deterministic aliases: normalized key -> canonical field
DETERMINISTIC_ALIASES: dict[str, str] = {
    # Timestamps
    "timestamp": "timestamp",
    "time": "timestamp",
    "datetime": "timestamp",
    "date": "timestamp",
    "recordedat": "timestamp",
    "eventtime": "timestamp",
    "sampletime": "timestamp",
    "ts": "timestamp",
    "@timestamp": "timestamp",
    "periodstart": "timestamp",
    "periodend": "timestamp",

    # Resource Identification
    "resourceid": "resource_id",
    "instanceid": "resource_id",
    "vmname": "resource_id",
    "servername": "resource_id",
    "serverhostname": "resource_id",
    "host": "resource_id",
    "hostname": "resource_id",
    "node": "resource_id",
    "nodename": "resource_id",
    "deviceid": "resource_id",
    "machineid": "resource_id",
    "resource": "resource_id",
    "instance": "resource_id",
    "server": "resource_id",

    # Resource Type
    "resourcetype": "resource_type",
    "instancetype": "resource_type",
    "type": "resource_type",
    "service": "resource_type",
    "vmtype": "resource_type",
    "sku": "resource_type",
    "category": "resource_type",

    # Provider & Region
    "provider": "provider",
    "cloudprovider": "provider",
    "cloud": "provider",
    "vendor": "provider",
    "platform": "provider",
    "region": "region",
    "location": "region",
    "availabilityzone": "region",
    "zone": "region",
    "datacenter": "region",
    "az": "region",

    # CPU Utilization
    "cpuutilization": "cpu_utilization_pct",
    "cpuutilizationpct": "cpu_utilization_pct",
    "cpuutil": "cpu_utilization_pct",
    "cpuusage": "cpu_utilization_pct",
    "cpu%": "cpu_utilization_pct",
    "cpupercentage": "cpu_utilization_pct",
    "percentagecpu": "cpu_utilization_pct",
    "cpupercent": "cpu_utilization_pct",
    "cpuloadpct": "cpu_utilization_pct",
    "cpuload": "cpu_utilization_pct",
    "cpu": "cpu_utilization_pct",
    "processorutilization": "cpu_utilization_pct",
    "avgcpu": "cpu_utilization_pct",
    "cpu_utilization_pct": "cpu_utilization_pct",
    "cpuutilizationpercent": "cpu_utilization_pct",

    # Memory Utilization
    "memoryutilization": "memory_utilization_pct",
    "memoryutilizationpct": "memory_utilization_pct",
    "memutil": "memory_utilization_pct",
    "memoryusage": "memory_utilization_pct",
    "memusedpct": "memory_utilization_pct",
    "memused": "memory_utilization_pct",
    "memory%": "memory_utilization_pct",
    "percentagememory": "memory_utilization_pct",
    "ramusage": "memory_utilization_pct",
    "ram%": "memory_utilization_pct",
    "mempercent": "memory_utilization_pct",
    "memory": "memory_utilization_pct",
    "mem_utilization_pct": "memory_utilization_pct",
    "memoryutilizationpercent": "memory_utilization_pct",
    "availablerealandusedmemorypct": "memory_utilization_pct",
    "availablememorypercent": "memory_utilization_pct",
    "memorypercent": "memory_utilization_pct",

    # Network
    "networkin": "network_in",
    "bytesin": "network_in",
    "networkintotal": "network_in",
    "rxbytes": "network_in",
    "trafficin": "network_in",
    "networkinbytes": "network_in",
    "netin": "network_in",
    "networkout": "network_out",
    "bytesout": "network_out",
    "networkouttotal": "network_out",
    "txbytes": "network_out",
    "trafficout": "network_out",
    "networkoutbytes": "network_out",
    "netout": "network_out",

    # Storage
    "storageused": "storage_used",
    "diskused": "storage_used",
    "usedstorage": "storage_used",
    "diskusage": "storage_used",
    "volumeused": "storage_used",
    "diskusedbytes": "storage_used",
    "diskreadbytes": "storage_used",
    "diskwritebytes": "storage_used",
    "disktotalbytes": "storage_capacity",
    "diskbytes": "storage_used",
    "storagecapacity": "storage_capacity",
    "diskcapacity": "storage_capacity",
    "totalstorage": "storage_capacity",
    "disktotal": "storage_capacity",
    "volumetotal": "storage_capacity",
    "diskcapacitybytes": "storage_capacity",
}


def normalize_header(header: str) -> str:
    """Normalize a column header by lowercasing and stripping non-alphanumeric chars (except %)."""
    cleaned = re.sub(r"[^a-zA-Z0-9%@]", "", str(header).strip().lower())
    return cleaned


def detect_cloud_provider(columns: list[str], sample_records: list[dict[str, Any]]) -> str:
    """Infer cloud provider signature from column names and sample data."""
    norm_cols = {normalize_header(c) for c in columns}

    # Check data content first if a provider column exists
    for r in sample_records[:5]:
        for k, v in r.items():
            if normalize_header(k) in {"provider", "cloudprovider", "cloud"}:
                val = str(v).strip().upper()
                if "AWS" in val:
                    return "AWS"
                if "AZURE" in val:
                    return "Azure"
                if "CUSTOM" in val:
                    return "Custom"

    # Check CloudWatch signature
    aws_hints = {"instanceid", "cpuutilization", "availabilityzone", "networkin"}
    if len(norm_cols.intersection(aws_hints)) >= 2:
        return "AWS"

    # Check Azure Monitor signature
    azure_hints = {"vmname", "percentagecpu", "networkintotal", "location"}
    if len(norm_cols.intersection(azure_hints)) >= 2:
        return "Azure"

    return "Custom"


def map_columns(
    columns: list[str],
    sample_records: Optional[list[dict[str, Any]]] = None,
    allow_gemini: bool = True
) -> tuple[dict[str, ColumnMappingItem], list[ColumnMappingItem]]:
    """Map source columns to canonical fields.

    Returns:
      (mapping_dict, list_of_ambiguous_columns)
    """
    mapping: dict[str, ColumnMappingItem] = {}
    canonical_usage: dict[str, list[str]] = {}

    unmapped_columns: list[str] = []

    # Step 1: Deterministic matching
    for col in columns:
        norm = normalize_header(col)
        canonical = DETERMINISTIC_ALIASES.get(norm)

        if canonical:
            mapping[col] = ColumnMappingItem(
                source_column=col,
                canonical_field=canonical,
                confidence=1.0,
                method="deterministic",
                is_ambiguous=False,
                candidate_fields=[canonical]
            )
            canonical_usage.setdefault(canonical, []).append(col)
        else:
            unmapped_columns.append(col)

    # Step 2: Detect multi-column collisions for the same canonical field
    # (e.g. if file has both 'CPU %' and 'CPUUsage')
    ambiguous_columns: list[ColumnMappingItem] = []
    for canonical, source_cols in canonical_usage.items():
        if len(source_cols) > 1:
            for sc in source_cols:
                item = mapping[sc]
                item.is_ambiguous = True
                item.confidence = 0.5
                item.candidate_fields = [canonical]
                if item not in ambiguous_columns:
                    ambiguous_columns.append(item)

    # Step 3: Optional Gemini LLM mapping for remaining unfamiliar columns
    if unmapped_columns and allow_gemini and os.getenv("GEMINI_API_KEY"):
        gemini_mappings = _query_gemini_column_mapping(unmapped_columns, sample_records)
        for col in unmapped_columns:
            suggested = gemini_mappings.get(col)
            if suggested and suggested in CANONICAL_FIELDS:
                item = ColumnMappingItem(
                    source_column=col,
                    canonical_field=suggested,
                    confidence=0.85,
                    method="gemini",
                    is_ambiguous=False,
                    candidate_fields=[suggested]
                )
                mapping[col] = item
                # Check for collision
                if suggested in canonical_usage:
                    item.is_ambiguous = True
                    ambiguous_columns.append(item)
                else:
                    canonical_usage.setdefault(suggested, []).append(col)
            else:
                mapping[col] = ColumnMappingItem(
                    source_column=col,
                    canonical_field=None,
                    confidence=0.0,
                    method="unmapped",
                    is_ambiguous=False,
                    candidate_fields=[]
                )
    else:
        for col in unmapped_columns:
            mapping[col] = ColumnMappingItem(
                source_column=col,
                canonical_field=None,
                confidence=0.0,
                method="unmapped",
                is_ambiguous=False,
                candidate_fields=[]
            )

    return mapping, ambiguous_columns


def _query_gemini_column_mapping(
    unmapped_columns: list[str],
    sample_records: Optional[list[dict[str, Any]]] = None
) -> dict[str, str]:
    """Ask Gemini for suggestions on unfamiliar column names."""
    if os.getenv("TESTING") == "1" or not os.getenv("GEMINI_API_KEY"):
        return {}
    try:
        from app.services.llm import _call_with_retry

        sample_preview = []
        if sample_records:
            sample_preview = sample_records[:3]

        prompt = f"""
You are an expert infrastructure sustainability and cloud monitoring system.
Match the following unfamiliar column headers to their corresponding CANONICAL ESG METRIC FIELDS.

CANONICAL FIELDS:
- timestamp
- resource_id
- resource_type
- provider
- region
- cpu_utilization_pct
- memory_utilization_pct
- network_in
- network_out
- storage_used
- storage_capacity

RULES:
1. Return ONLY valid JSON (no markdown fences) mapping the exact input column to a canonical field.
2. If an input column does NOT clearly correspond to any canonical field, map it to null.
3. NEVER invent or fabricate fields.
4. Do not map ambiguous fields.

INPUT COLUMNS:
{json.dumps(unmapped_columns)}

SAMPLE ROWS:
{json.dumps(sample_preview, default=str)}
"""
        response_text = _call_with_retry(prompt, retries=1, delay=1)
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        parsed = json.loads(text.strip())
        if isinstance(parsed, dict):
            # Deterministically validate that returned values belong to CANONICAL_FIELDS
            clean_result = {}
            for k, v in parsed.items():
                if k in unmapped_columns and v in CANONICAL_FIELDS:
                    clean_result[k] = v
            return clean_result
    except Exception as exc:
        logger.warning("Gemini column mapping fallback skipped: %s", exc)

    return {}
