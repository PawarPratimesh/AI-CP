"""Infrastructure Energy Consumption and Carbon Emissions Estimation.

Implements empirical power modeling (SPECpower / Cloud Carbon Footprint standard)
and location-based Scope 2 GHG emission calculations.

Estimated Energy (kWh) = (P_total(Watts) * PUE * delta_t_hours) / 1000
Estimated CO2e (kg)   = Estimated Energy (kWh) * Grid Carbon Intensity (kgCO2e/kWh)
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any, Optional

from app.cloud_carbon.schemas import (
    CanonicalRecord,
    EmissionsEstimationRequest,
    EmissionsEstimationResponse,
    PowerModelAssumptions,
    ResourceEnergyCarbonBreakdown,
)

logger = logging.getLogger(__name__)

# Standard Regional Grid Carbon Intensities in kgCO2e/kWh (Scope 2 Location-based)
# Sourced from EPA eGRID, European Environment Agency, and Cloud Provider Sustainability Disclosures
DEFAULT_GRID_INTENSITY_FACTORS: dict[str, float] = {
    # AWS Regions
    "us-east-1": 0.379,       # Virginia
    "us-east-2": 0.442,       # Ohio
    "us-west-1": 0.210,       # N. California
    "us-west-2": 0.198,       # Oregon (Hydro-rich)
    "eu-west-1": 0.285,       # Ireland
    "eu-west-2": 0.225,       # London
    "eu-central-1": 0.338,    # Frankfurt
    "ap-south-1": 0.708,      # Mumbai
    "ap-southeast-1": 0.408,  # Singapore
    "ap-northeast-1": 0.462,  # Tokyo
    "ca-central-1": 0.120,    # Montreal (Hydro-rich)

    # Azure Regions
    "eastus": 0.379,          # Virginia
    "eastus2": 0.379,         # Virginia
    "westus": 0.210,          # California
    "westus2": 0.198,         # Washington
    "centralus": 0.415,       # Iowa
    "westeurope": 0.320,      # Netherlands
    "northeurope": 0.285,     # Ireland
    "uksouth": 0.225,         # London
    "centralindia": 0.708,    # Pune
    "southeastasia": 0.408,   # Singapore

    # GCP Regions
    "us-central1": 0.415,     # Iowa
    "europe-west1": 0.160,    # Belgium
    "asia-south1": 0.708,     # Mumbai
}

# Standard Cloud Datacenter PUE defaults
PROVIDER_PUE_DEFAULTS: dict[str, float] = {
    "AWS": 1.15,
    "Azure": 1.18,
    "GCP": 1.10,
    "Custom": 1.30,
}

# Known hardware/instance profiles for specific power lookups
INSTANCE_POWER_PROFILES: dict[str, dict[str, float]] = {
    "t3.nano": {"idle": 2.5, "max": 10.0, "ram_gb": 0.5},
    "t3.micro": {"idle": 5.0, "max": 20.0, "ram_gb": 1.0},
    "t3.small": {"idle": 10.0, "max": 40.0, "ram_gb": 2.0},
    "t3.medium": {"idle": 15.0, "max": 60.0, "ram_gb": 4.0},
    "m5.large": {"idle": 25.0, "max": 90.0, "ram_gb": 8.0},
    "m5.xlarge": {"idle": 45.0, "max": 180.0, "ram_gb": 16.0},
    "c5.large": {"idle": 30.0, "max": 110.0, "ram_gb": 4.0},
    "Standard_B1s": {"idle": 3.0, "max": 15.0, "ram_gb": 1.0},
    "Standard_B2s": {"idle": 10.0, "max": 40.0, "ram_gb": 4.0},
    "Standard_D2s_v3": {"idle": 20.0, "max": 80.0, "ram_gb": 8.0},
    "Standard_D4s_v3": {"idle": 40.0, "max": 160.0, "ram_gb": 16.0},
}


def normalize_region_key(region: Optional[str]) -> Optional[str]:
    """Normalize region string for lookup (lowercased, stripped, AZ letters trimmed if needed)."""
    if not region:
        return None
    cleaned = re.sub(r"[^a-z0-9\-]", "", str(region).strip().lower())
    if not cleaned:
        return None

    # Exact match first
    if cleaned in DEFAULT_GRID_INTENSITY_FACTORS:
        return cleaned

    # Check if stripping trailing availability zone letter matches (e.g. 'eu-west-1a' -> 'eu-west-1')
    if re.search(r"-[0-9][a-z]$", cleaned):
        base_region = cleaned[:-1]
        if base_region in DEFAULT_GRID_INTENSITY_FACTORS:
            return base_region

    return cleaned


def _parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Safely parse ISO timestamp to datetime object."""
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None


def estimate_energy_and_carbon(
    records: list[CanonicalRecord],
    upload_id: str,
    options: Optional[EmissionsEstimationRequest] = None,
) -> EmissionsEstimationResponse:
    """Calculate energy consumption and carbon emissions for canonical records.

    1. Group observations by resource_id to calculate chronological time intervals.
    2. Compute instance power draw using linear utilization model (SPECpower).
    3. Apply Datacenter PUE (Power Usage Effectiveness) multiplier.
    4. Compute regional grid emissions using location-based intensity factors.
    5. Explicitly flag and withhold estimation for unknown/unsupported regions.
    """
    opts = options or EmissionsEstimationRequest()

    # Active grid emission factor table (merging defaults with any user-provided overrides)
    active_emission_factors = dict(DEFAULT_GRID_INTENSITY_FACTORS)
    if opts.custom_emission_factors:
        for k, v in opts.custom_emission_factors.items():
            norm_k = normalize_region_key(k)
            if norm_k and v >= 0:
                active_emission_factors[norm_k] = float(v)

    # 1. Group records by resource_id
    records_by_resource: dict[str, list[CanonicalRecord]] = {}
    for r in records:
        records_by_resource.setdefault(r.resource_id, []).append(r)

    total_energy_kwh = 0.0
    total_carbon_kg = 0.0
    uncalculated_energy_kwh = 0.0

    regions_detected: set[str] = set()
    missing_factor_regions: set[str] = set()
    regional_factors_applied: dict[str, float] = {}
    resource_breakdowns: list[ResourceEnergyCarbonBreakdown] = []

    # Global assumptions baseline
    idle_watts_default = opts.idle_watts or 50.0
    max_watts_default = opts.max_watts or 200.0
    memory_watts_per_gb = 0.38
    default_interval_hours = 1.0

    for resource_id, res_records in records_by_resource.items():
        # Sort chronologically by timestamp if valid
        def sort_key(rec: CanonicalRecord):
            dt = _parse_timestamp(rec.timestamp)
            return dt.timestamp() if dt else 0.0

        sorted_records = sorted(res_records, key=sort_key)

        primary_provider = sorted_records[0].provider or "Custom"
        primary_region = normalize_region_key(sorted_records[0].region)
        resource_type = sorted_records[0].resource_type or "virtual-machine"

        if primary_region:
            regions_detected.add(primary_region)

        # Determine PUE
        pue = opts.pue or PROVIDER_PUE_DEFAULTS.get(primary_provider, 1.20)

        # Determine hardware profile if recognized
        profile = INSTANCE_POWER_PROFILES.get(resource_type)
        idle_w = profile["idle"] if profile else idle_watts_default
        max_w = profile["max"] if profile else max_watts_default
        # Use profile RAM if defined, otherwise retain documented 16.0 GB baseline fallback
        ram_gb = profile.get("ram_gb", 16.0) if profile else 16.0

        resource_energy_kwh = 0.0

        for i, rec in enumerate(sorted_records):
            # Calculate time delta to next record, or to previous record, or fallback
            delta_hours = default_interval_hours
            dt_curr = _parse_timestamp(rec.timestamp)
            if dt_curr and i < len(sorted_records) - 1:
                dt_next = _parse_timestamp(sorted_records[i + 1].timestamp)
                if dt_next and dt_next > dt_curr:
                    diff_sec = (dt_next - dt_curr).total_seconds()
                    # Cap unreasonable time jumps (e.g. gap > 7 days) at 24 hours
                    delta_hours = min(24.0, max(0.01, diff_sec / 3600.0))
            elif dt_curr and i > 0 and len(sorted_records) > 1:
                # For the last observation, reuse the preceding interval
                dt_prev = _parse_timestamp(sorted_records[i - 1].timestamp)
                if dt_prev and dt_curr > dt_prev:
                    diff_sec = (dt_curr - dt_prev).total_seconds()
                    delta_hours = min(24.0, max(0.01, diff_sec / 3600.0))

            # Compute CPU power: P_idle + (P_max - P_idle) * (cpu_pct / 100)
            cpu_pct = rec.cpu_utilization_pct if rec.cpu_utilization_pct is not None else 50.0
            cpu_watts = idle_w + (max_w - idle_w) * (cpu_pct / 100.0)

            # Compute Memory power: instance RAM (GB) * 0.38 W/GB * (0.5 + 0.5 * mem_pct/100)
            mem_pct = rec.memory_utilization_pct if rec.memory_utilization_pct is not None else 50.0
            mem_watts = ram_gb * memory_watts_per_gb * (0.5 + 0.5 * (mem_pct / 100.0))

            total_watts = cpu_watts + mem_watts

            # Interval energy: (Watts * PUE * hours) / 1000 = kWh
            interval_kwh = (total_watts * pue * delta_hours) / 1000.0
            resource_energy_kwh += interval_kwh

        resource_energy_kwh = round(resource_energy_kwh, 4)
        total_energy_kwh += resource_energy_kwh

        # Carbon calculation for this resource
        intensity_factor = active_emission_factors.get(primary_region) if primary_region else None

        if intensity_factor is not None:
            res_carbon = round(resource_energy_kwh * intensity_factor, 4)
            total_carbon_kg += res_carbon
            regional_factors_applied[primary_region] = intensity_factor
            carbon_status = "ESTIMATED"
        else:
            res_carbon = None
            uncalculated_energy_kwh += resource_energy_kwh
            carbon_status = "EMISSION_FACTOR_UNAVAILABLE"
            if primary_region:
                missing_factor_regions.add(primary_region)
            else:
                missing_factor_regions.add("unspecified_region")

        resource_breakdowns.append(
            ResourceEnergyCarbonBreakdown(
                resource_id=resource_id,
                provider=primary_provider,
                region=primary_region,
                observation_count=len(sorted_records),
                estimated_energy_kwh=resource_energy_kwh,
                grid_intensity_factor_kg_per_kwh=intensity_factor,
                estimated_carbon_kg=res_carbon,
                carbon_status=carbon_status,
            )
        )

    # Global status and response construction
    all_regions_have_factors = (len(missing_factor_regions) == 0) and (total_energy_kwh > 0)
    has_partial_carbon = (total_carbon_kg > 0) or all_regions_have_factors

    assumptions = PowerModelAssumptions(
        pue=opts.pue or 1.15,
        idle_watts_default=idle_watts_default,
        max_watts_default=max_watts_default,
        memory_watts_per_gb=memory_watts_per_gb,
        default_interval_hours=default_interval_hours,
    )

    response_status = "SUCCESS" if all_regions_have_factors else "PARTIAL_CALCULATION"
    if not has_partial_carbon and missing_factor_regions:
        response_status = "EMISSION_FACTOR_UNAVAILABLE"

    return EmissionsEstimationResponse(
        upload_id=upload_id,
        status=response_status,
        total_energy_kwh=round(total_energy_kwh, 4),
        total_carbon_kgco2e=round(total_carbon_kg, 4) if (total_carbon_kg > 0 or all_regions_have_factors) else None,
        uncalculated_energy_kwh=round(uncalculated_energy_kwh, 4),
        regions_detected=sorted(list(regions_detected)),
        missing_factor_regions=sorted(list(missing_factor_regions)),
        regional_factors_applied=regional_factors_applied,
        assumptions=assumptions,
        resources_breakdown=resource_breakdowns,
        estimation_notice=(
            "Energy consumption and carbon emissions are estimates based on resource usage "
            "assumptions and emission factors, not direct meter readings."
        ),
    )
