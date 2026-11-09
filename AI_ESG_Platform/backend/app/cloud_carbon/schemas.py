"""Pydantic schemas for Cloud & Carbon Data Ingestion and Preprocessing."""

from __future__ import annotations

from typing import Any, Optional
import uuid
from pydantic import BaseModel, Field


class CanonicalRecord(BaseModel):
    """Canonical representation of an infrastructure metric observation."""
    timestamp: str = Field(..., description="ISO-8601 formatted UTC timestamp")
    resource_id: str = Field(..., description="Unique hardware / instance identifier")
    resource_type: Optional[str] = Field(None, description="e.g. Compute, Database, Storage, Worker")
    provider: Optional[str] = Field(None, description="AWS, Azure, Custom")
    region: Optional[str] = Field(None, description="e.g. us-east-1, westeurope")
    cpu_utilization_pct: Optional[float] = Field(None, description="0.0 - 100.0 percentage")
    memory_utilization_pct: Optional[float] = Field(None, description="0.0 - 100.0 percentage")
    network_in: Optional[float] = Field(None, description="Network ingress (preserved units)")
    network_out: Optional[float] = Field(None, description="Network egress (preserved units)")
    storage_used: Optional[float] = Field(None, description="Storage used (preserved units)")
    storage_capacity: Optional[float] = Field(None, description="Storage capacity (preserved units)")


class ColumnMappingItem(BaseModel):
    """Details of a mapped column from the source file to canonical field."""
    source_column: str
    canonical_field: Optional[str] = None
    confidence: float = 1.0
    method: str = "deterministic"  # "deterministic", "gemini", "user_confirmed", "unmapped"
    is_ambiguous: bool = False
    candidate_fields: list[str] = Field(default_factory=list)


class ValidationErrorItem(BaseModel):
    """Information regarding a rejected or invalid record."""
    record_index: int
    resource_id: Optional[str] = None
    field: str
    reason: str
    raw_value: Optional[Any] = None


class ConfirmMappingRequest(BaseModel):
    """User-confirmed column mapping for ambiguous fields."""
    mapping: dict[str, Optional[str]] = Field(..., description="source_column -> canonical_field")


class UploadInspectionResponse(BaseModel):
    """Full inspection, validation and preprocessing response."""
    upload_id: str
    filename: str
    file_format: str  # "CSV" or "JSON"
    detected_provider: str  # "AWS", "Azure", "Custom", "Unknown"
    total_records: int
    accepted_records: int
    rejected_records: int
    duplicate_records: int
    available_metrics: list[str]
    column_mapping: dict[str, ColumnMappingItem]
    ambiguous_columns: list[ColumnMappingItem]
    missing_metrics: list[str]
    validation_errors: list[ValidationErrorItem]
    preview_records: list[CanonicalRecord]
    processing_status: str  # "SUCCESS", "REQUIRES_CONFIRMATION", "FAILED"


class PreviewResponse(BaseModel):
    """Response model for previewing preprocessed records."""
    upload_id: str
    filename: str
    total_records: int
    accepted_records: int
    available_metrics: list[str]
    preview_records: list[CanonicalRecord]


# ---------------------------------------------------------------------------
# Phase 3: Anomaly Detection Schemas
# ---------------------------------------------------------------------------

class AnomalyDetectionRequest(BaseModel):
    """Optional configuration for Isolation Forest anomaly detection."""
    contamination: float = Field(0.1, ge=0.01, le=0.5, description="Expected proportion of outliers in the dataset")
    random_state: int = Field(42, description="Random seed for reproducibility")


class AnomalyRecordItem(BaseModel):
    """Per-record anomaly detection result."""
    record_index: int
    resource_id: str
    timestamp: str
    status: str = Field(..., description="'Anomaly' or 'Normal'")
    is_anomaly: bool
    anomaly_score: float = Field(..., description="Normalized anomaly score (0.0 to 1.0, higher is more anomalous)")
    contributing_metrics: list[str] = Field(default_factory=list, description="Metrics exhibiting statistically significant deviation")
    raw_metrics: dict[str, Optional[float]] = Field(default_factory=dict)


class AnomalyDetectionResponse(BaseModel):
    """Summary and details of ML anomaly detection."""
    upload_id: str
    status: str = Field("SUCCESS", description="'SUCCESS', 'INSUFFICIENT_DATA', or 'FAILED'")
    features_used: list[str]
    total_records_analyzed: int
    anomalies_detected: int
    normal_records: int
    anomaly_percentage: float
    methodology_note: str
    attribution_note: str
    anomalies: list[AnomalyRecordItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 3: Energy & Carbon Estimation Schemas
# ---------------------------------------------------------------------------

class PowerModelAssumptions(BaseModel):
    """Parameters used in SPECpower linear energy modeling."""
    pue: float = Field(1.15, description="Datacenter Power Usage Effectiveness")
    idle_watts_default: float = Field(50.0, description="Baseline idle power in Watts")
    max_watts_default: float = Field(200.0, description="Peak load power in Watts")
    memory_watts_per_gb: float = Field(0.38, description="Power consumed per GB RAM in Watts")
    default_interval_hours: float = Field(1.0, description="Fallback time interval per observation in hours")
    estimation_notice: str = (
        "Energy consumption and carbon emissions are estimates based on resource usage "
        "assumptions and emission factors, not direct meter readings."
    )


class EmissionsEstimationRequest(BaseModel):
    """Configurable options for energy and carbon modeling."""
    pue: Optional[float] = Field(None, ge=1.0, le=3.0, description="Custom PUE factor")
    idle_watts: Optional[float] = Field(None, ge=1.0, description="Custom idle wattage")
    max_watts: Optional[float] = Field(None, ge=1.0, description="Custom max wattage")
    custom_emission_factors: dict[str, float] = Field(
        default_factory=dict,
        description="Override or additional region-specific grid intensities in kgCO2e/kWh"
    )


class ResourceEnergyCarbonBreakdown(BaseModel):
    """Energy and carbon estimates per resource."""
    resource_id: str
    provider: str
    region: Optional[str]
    observation_count: int
    estimated_energy_kwh: float
    grid_intensity_factor_kg_per_kwh: Optional[float] = None
    estimated_carbon_kg: Optional[float] = None
    carbon_status: str = Field("ESTIMATED", description="'ESTIMATED' or 'EMISSION_FACTOR_UNAVAILABLE'")


class EmissionsEstimationResponse(BaseModel):
    """Full energy and carbon footprint calculation response."""
    upload_id: str
    status: str = Field("SUCCESS", description="'SUCCESS' or 'PARTIAL_CALCULATION'")
    total_energy_kwh: float = Field(..., description="Total estimated energy in Kilowatt-Hours (kWh)")
    total_carbon_kgco2e: Optional[float] = Field(None, description="Total estimated emissions in kgCO2e")
    uncalculated_energy_kwh: float = Field(0.0, description="Energy for which no regional carbon factor was available")
    regions_detected: list[str] = Field(default_factory=list)
    missing_factor_regions: list[str] = Field(default_factory=list)
    regional_factors_applied: dict[str, float] = Field(default_factory=dict, description="Region -> kgCO2e/kWh")
    assumptions: PowerModelAssumptions
    resources_breakdown: list[ResourceEnergyCarbonBreakdown] = Field(default_factory=list)
    estimation_notice: str


# ---------------------------------------------------------------------------
# Phase 3: Unified Analysis Response
# ---------------------------------------------------------------------------

class UnifiedAnalysisResponse(BaseModel):
    """Combined anomaly detection and energy/carbon estimation output."""
    upload_id: str
    filename: str
    detected_provider: str
    anomaly_detection: AnomalyDetectionResponse
    emissions_estimation: EmissionsEstimationResponse


# ---------------------------------------------------------------------------
# Phase 4: AI Insights and Optimization Recommendations Schemas
# ---------------------------------------------------------------------------

class AnomalyExplanationItem(BaseModel):
    """AI or rule-based explanation for a detected infrastructure anomaly."""
    resource_id: str
    timestamp: str
    metric: str = Field(..., description="Unusual metric dimension (e.g. CPU, Memory, Network)")
    observed_value: Optional[float] = None
    baseline_context: Optional[str] = None
    explanation: str = Field(..., description="What happened in technical terms")
    possible_causes: str = Field(..., description="Why this might indicate a problem")
    operational_impact: str = Field(..., description="Potential impact on infrastructure or service reliability")
    investigation_steps: str = Field(..., description="Concrete steps the administrator should investigate")


class OptimizationRecommendationItem(BaseModel):
    """Actionable infrastructure optimization recommendation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    category: str = Field(
        ...,
        description="Compute Rightsizing, Workload Optimization, Decarbonization, Memory Tuning, Storage Lifecycle"
    )
    target_resource: str = Field(..., description="Specific resource ID or 'Fleet-wide'")
    observation: str = Field(..., description="Problem or pattern observed in data")
    action: str = Field(..., description="Concrete suggested fix or next step")
    reason: str = Field(..., description="Technical justification for this action")
    expected_benefit: str = Field(..., description="'High', 'Medium', or 'Low'")
    evidence: str = Field(..., description="Supporting metrics or data points")
    estimated_impact: Optional[str] = Field(None, description="Qualitative or defensible quantitative saving")


class CloudCarbonRecommendationsResponse(BaseModel):
    """Complete response model for Phase 4 recommendations & anomaly explanations."""
    upload_id: str
    status: str = Field("SUCCESS", description="'SUCCESS', 'NO_ANOMALIES', 'NO_OPPORTUNITIES', 'FAILED'")
    generation_method: str = Field(..., description="'GEMINI' or 'RULE_BASED'")
    summary: str = Field(..., description="Executive summary of infrastructure health and opportunities")
    anomaly_explanations: list[AnomalyExplanationItem] = Field(default_factory=list)
    recommendations: list[OptimizationRecommendationItem] = Field(default_factory=list)
    warning_or_limitation: Optional[str] = None


