"""Preprocessing & Normalization Engine for Infrastructure Metrics."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.cloud_carbon.schemas import (
    CanonicalRecord,
    ColumnMappingItem,
    ValidationErrorItem,
)
from app.cloud_carbon.validators import (
    FileValidationError,
    parse_numeric_metric,
    parse_percentage_metric,
    parse_timestamp_utc,
)

logger = logging.getLogger(__name__)

ALL_STANDARD_METRICS = ["cpu", "memory", "network", "storage"]


def preprocess_records(
    raw_records: list[dict[str, Any]],
    column_mapping: dict[str, ColumnMappingItem],
    fallback_provider: str = "Custom"
) -> dict[str, Any]:
    """Transform raw records into canonical format using the established column mapping.

    Returns:
      {
        "accepted": list[CanonicalRecord],
        "rejected_count": int,
        "duplicate_count": int,
        "errors": list[ValidationErrorItem],
        "available_metrics": list[str],
        "missing_metrics": list[str]
      }
    """
    # Invert mapping: canonical_field -> source_column
    field_to_source: dict[str, str] = {}
    for source_col, item in column_mapping.items():
        if item.canonical_field and not item.is_ambiguous:
            field_to_source[item.canonical_field] = source_col

    # Verify structural requirements
    if "timestamp" not in field_to_source:
        raise FileValidationError(
            "Missing required structural field: No column could be mapped to 'timestamp'."
        )
    if "resource_id" not in field_to_source:
        raise FileValidationError(
            "Missing required structural field: No column could be mapped to 'resource_id'."
        )

    ts_col = field_to_source["timestamp"]
    res_col = field_to_source["resource_id"]
    type_col = field_to_source.get("resource_type")
    provider_col = field_to_source.get("provider")
    region_col = field_to_source.get("region")
    cpu_col = field_to_source.get("cpu_utilization_pct")
    mem_col = field_to_source.get("memory_utilization_pct")
    net_in_col = field_to_source.get("network_in")
    net_out_col = field_to_source.get("network_out")
    storage_used_col = field_to_source.get("storage_used")
    storage_cap_col = field_to_source.get("storage_capacity")

    accepted_records: list[CanonicalRecord] = []
    validation_errors: list[ValidationErrorItem] = []
    seen_composite_keys: set[tuple[str, str]] = set()
    duplicate_count = 0

    has_cpu = False
    has_mem = False
    has_net = False
    has_storage = False

    for idx, row in enumerate(raw_records, start=1):
        row_errors: list[str] = []

        # 1. Resource ID
        raw_res = row.get(res_col)
        res_id = str(raw_res).strip() if raw_res is not None else ""
        if not res_id or res_id.lower() in ("null", "none", "nan"):
            validation_errors.append(ValidationErrorItem(
                record_index=idx,
                resource_id=None,
                field="resource_id",
                reason="resource_id is missing or empty.",
                raw_value=raw_res
            ))
            continue

        # 2. Timestamp
        raw_ts = row.get(ts_col)
        norm_ts, ts_err = parse_timestamp_utc(raw_ts)
        if ts_err:
            validation_errors.append(ValidationErrorItem(
                record_index=idx,
                resource_id=res_id,
                field="timestamp",
                reason=ts_err,
                raw_value=raw_ts
            ))
            continue

        # 3. Deduplication (Key: resource_id + timestamp)
        comp_key = (res_id, norm_ts)
        if comp_key in seen_composite_keys:
            duplicate_count += 1
            # Flag duplicate error
            validation_errors.append(ValidationErrorItem(
                record_index=idx,
                resource_id=res_id,
                field="duplicate",
                reason=f"Duplicate observation for resource '{res_id}' at timestamp '{norm_ts}'.",
                raw_value=None
            ))
            continue
        seen_composite_keys.add(comp_key)

        # 4. CPU Metric
        cpu_val = None
        if cpu_col and cpu_col in row:
            cpu_val, cpu_err = parse_percentage_metric(row[cpu_col], "cpu_utilization_pct")
            if cpu_err:
                validation_errors.append(ValidationErrorItem(
                    record_index=idx,
                    resource_id=res_id,
                    field="cpu_utilization_pct",
                    reason=cpu_err,
                    raw_value=row[cpu_col]
                ))
                continue
            if cpu_val is not None:
                has_cpu = True

        # 5. Memory Metric
        mem_val = None
        if mem_col and mem_col in row:
            mem_val, mem_err = parse_percentage_metric(row[mem_col], "memory_utilization_pct")
            if mem_err:
                validation_errors.append(ValidationErrorItem(
                    record_index=idx,
                    resource_id=res_id,
                    field="memory_utilization_pct",
                    reason=mem_err,
                    raw_value=row[mem_col]
                ))
                continue
            if mem_val is not None:
                has_mem = True

        # 6. Network Metrics
        net_in_val = None
        if net_in_col and net_in_col in row:
            net_in_val, net_in_err = parse_numeric_metric(row[net_in_col], "network_in")
            if net_in_err:
                validation_errors.append(ValidationErrorItem(
                    record_index=idx,
                    resource_id=res_id,
                    field="network_in",
                    reason=net_in_err,
                    raw_value=row[net_in_col]
                ))
                continue
            if net_in_val is not None:
                has_net = True

        net_out_val = None
        if net_out_col and net_out_col in row:
            net_out_val, net_out_err = parse_numeric_metric(row[net_out_col], "network_out")
            if net_out_err:
                validation_errors.append(ValidationErrorItem(
                    record_index=idx,
                    resource_id=res_id,
                    field="network_out",
                    reason=net_out_err,
                    raw_value=row[net_out_col]
                ))
                continue
            if net_out_val is not None:
                has_net = True

        # 7. Storage Metrics
        storage_used_val = None
        if storage_used_col and storage_used_col in row:
            storage_used_val, s_err = parse_numeric_metric(row[storage_used_col], "storage_used")
            if s_err:
                validation_errors.append(ValidationErrorItem(
                    record_index=idx,
                    resource_id=res_id,
                    field="storage_used",
                    reason=s_err,
                    raw_value=row[storage_used_col]
                ))
                continue
            if storage_used_val is not None:
                has_storage = True

        storage_cap_val = None
        if storage_cap_col and storage_cap_col in row:
            storage_cap_val, sc_err = parse_numeric_metric(row[storage_cap_col], "storage_capacity")
            if sc_err:
                validation_errors.append(ValidationErrorItem(
                    record_index=idx,
                    resource_id=res_id,
                    field="storage_capacity",
                    reason=sc_err,
                    raw_value=row[storage_cap_col]
                ))
                continue
            if storage_cap_val is not None:
                has_storage = True

        # 8. Optional Metadata Strings
        raw_type = row.get(type_col) if type_col else None
        res_type = str(raw_type).strip() if raw_type not in (None, "") else None

        raw_prov = row.get(provider_col) if provider_col else None
        prov = str(raw_prov).strip() if raw_prov not in (None, "") else fallback_provider

        raw_reg = row.get(region_col) if region_col else None
        region = str(raw_reg).strip() if raw_reg not in (None, "") else None

        # Build clean record
        accepted_records.append(CanonicalRecord(
            timestamp=norm_ts,
            resource_id=res_id,
            resource_type=res_type,
            provider=prov,
            region=region,
            cpu_utilization_pct=cpu_val,
            memory_utilization_pct=mem_val,
            network_in=net_in_val,
            network_out=net_out_val,
            storage_used=storage_used_val,
            storage_capacity=storage_cap_val,
        ))

    # Evaluate metric dimensions
    available_metrics: list[str] = []
    if has_cpu:
        available_metrics.append("cpu")
    if has_mem:
        available_metrics.append("memory")
    if has_net:
        available_metrics.append("network")
    if has_storage:
        available_metrics.append("storage")

    missing_metrics = [m for m in ALL_STANDARD_METRICS if m not in available_metrics]

    return {
        "accepted": accepted_records,
        "rejected_count": len(validation_errors),
        "duplicate_count": duplicate_count,
        "errors": validation_errors,
        "available_metrics": available_metrics,
        "missing_metrics": missing_metrics,
    }

