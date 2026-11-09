"""FastAPI router for Cloud & Carbon Data Ingestion and Preprocessing.

Prefix: /api/cloud-carbon
Tags:   Cloud & Carbon
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.cloud_carbon.anomaly_detector import detect_infrastructure_anomalies
from app.cloud_carbon.carbon_estimator import estimate_energy_and_carbon
from app.cloud_carbon.recommendation_engine import generate_cloud_carbon_insights
from app.cloud_carbon.column_mapper import (
    CANONICAL_FIELDS,
    detect_cloud_provider,
    map_columns,
)
from app.cloud_carbon.preprocessor import preprocess_records
from app.cloud_carbon.schemas import (
    AnomalyDetectionRequest,
    AnomalyDetectionResponse,
    CloudCarbonRecommendationsResponse,
    ColumnMappingItem,
    ConfirmMappingRequest,
    EmissionsEstimationRequest,
    EmissionsEstimationResponse,
    PreviewResponse,
    UnifiedAnalysisResponse,
    UploadInspectionResponse,
)
from app.cloud_carbon.session_store import (
    create_session,
    get_session,
    get_session_analysis,
    store_session_analysis,
    update_session_mapping,
)
from app.cloud_carbon.validators import FileValidationError, validate_file_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cloud-carbon", tags=["Cloud & Carbon"])


@router.get("/health")
def cloud_carbon_health():
    """Service health check."""
    return {
        "status": "healthy",
        "module": "cloud_carbon",
        "phase": "4.0.0 (AI Insights & Optimization Recommendations)"
    }


@router.post("/upload", response_model=UploadInspectionResponse)
def upload_metrics_file(file: UploadFile = File(...)):
    """Upload and inspect CSV or JSON infrastructure metric exports.

    - Validates file content and size (<= 25 MB).
    - Detects cloud provider signature (AWS, Azure, Custom).
    - Maps column headers to canonical fields.
    - Validates data, timestamps and percentages.
    - Returns inspection summary, errors, and normalized preview.
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file was uploaded."
        )

    try:
        content_bytes = file.file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read uploaded file: {exc}"
        )

    try:
        file_format, raw_records, columns = validate_file_payload(file.filename, content_bytes)
    except FileValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    # 1. Detect provider
    detected_provider = detect_cloud_provider(columns, raw_records)

    # 2. Map columns
    column_mapping, ambiguous_columns = map_columns(columns, raw_records, allow_gemini=True)

    # 3. Determine initial status
    processing_status = "REQUIRES_CONFIRMATION" if ambiguous_columns else "SUCCESS"

    # 4. Preprocess records if required fields are mapped
    preprocessed_result = {
        "accepted": [],
        "rejected_count": 0,
        "duplicate_count": 0,
        "errors": [],
        "available_metrics": [],
        "missing_metrics": ["cpu", "memory", "network", "storage"],
    }

    try:
        preprocessed_result = preprocess_records(
            raw_records, column_mapping, fallback_provider=detected_provider
        )
    except FileValidationError as exc:
        if ambiguous_columns:
            processing_status = "REQUIRES_CONFIRMATION"
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)

    # 5. Save temporary session
    upload_id = create_session(
        filename=file.filename,
        file_format=file_format,
        detected_provider=detected_provider,
        columns=columns,
        raw_records=raw_records,
        column_mapping=column_mapping,
        preprocessed_result=preprocessed_result,
    )

    accepted_records = preprocessed_result["accepted"]

    return UploadInspectionResponse(
        upload_id=upload_id,
        filename=file.filename,
        file_format=file_format,
        detected_provider=detected_provider,
        total_records=len(raw_records),
        accepted_records=len(accepted_records),
        rejected_records=preprocessed_result["rejected_count"],
        duplicate_records=preprocessed_result["duplicate_count"],
        available_metrics=preprocessed_result["available_metrics"],
        column_mapping=column_mapping,
        ambiguous_columns=ambiguous_columns,
        missing_metrics=preprocessed_result["missing_metrics"],
        validation_errors=preprocessed_result["errors"][:50],  # Cap error list
        preview_records=accepted_records[:25],
        processing_status=processing_status,
    )


@router.get("/preview/{upload_id}", response_model=PreviewResponse)
def get_preview_data(upload_id: str):
    """Retrieve normalized preview records and statistics for an uploaded batch."""
    session = get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found or expired. Please re-upload your file."
        )

    res = session["preprocessed_result"]
    accepted = res.get("accepted", [])

    return PreviewResponse(
        upload_id=upload_id,
        filename=session["filename"],
        total_records=len(session["raw_records"]),
        accepted_records=len(accepted),
        available_metrics=res.get("available_metrics", []),
        preview_records=accepted[:25],
    )


@router.post("/confirm-mapping/{upload_id}", response_model=UploadInspectionResponse)
def confirm_column_mapping(upload_id: str, request: ConfirmMappingRequest):
    """Confirm user-selected mappings for ambiguous or unmapped columns and reprocess."""
    session = get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found or expired. Please re-upload your file."
        )

    column_mapping = session["column_mapping"]

    # Apply user-confirmed mapping
    for source_col, target_canonical in request.mapping.items():
        if source_col in column_mapping:
            if target_canonical in CANONICAL_FIELDS:
                column_mapping[source_col] = ColumnMappingItem(
                    source_column=source_col,
                    canonical_field=target_canonical,
                    confidence=1.0,
                    method="user_confirmed",
                    is_ambiguous=False,
                    candidate_fields=[target_canonical],
                )
            elif target_canonical is None or target_canonical == "" or str(target_canonical).lower() == "unmapped":
                column_mapping[source_col] = ColumnMappingItem(
                    source_column=source_col,
                    canonical_field=None,
                    confidence=0.0,
                    method="user_confirmed",
                    is_ambiguous=False,
                    candidate_fields=[],
                )

    # Re-preprocess with updated mapping
    try:
        new_preprocessed = preprocess_records(
            session["raw_records"],
            column_mapping,
            fallback_provider=session["detected_provider"],
        )
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)

    update_session_mapping(upload_id, column_mapping, new_preprocessed)

    accepted_records = new_preprocessed["accepted"]

    return UploadInspectionResponse(
        upload_id=upload_id,
        filename=session["filename"],
        file_format=session["file_format"],
        detected_provider=session["detected_provider"],
        total_records=len(session["raw_records"]),
        accepted_records=len(accepted_records),
        rejected_records=new_preprocessed["rejected_count"],
        duplicate_records=new_preprocessed["duplicate_count"],
        available_metrics=new_preprocessed["available_metrics"],
        column_mapping=column_mapping,
        ambiguous_columns=[],  # Resolved
        missing_metrics=new_preprocessed["missing_metrics"],
        validation_errors=new_preprocessed["errors"][:50],
        preview_records=accepted_records[:25],
        processing_status="SUCCESS",
    )


# ---------------------------------------------------------------------------
# Phase 3 Endpoints: Anomaly Detection, Energy & Carbon Estimation
# ---------------------------------------------------------------------------

@router.post("/anomaly-detection/{upload_id}", response_model=AnomalyDetectionResponse)
def run_anomaly_detection_endpoint(
    upload_id: str,
    request: Optional[AnomalyDetectionRequest] = None,
):
    """Run scikit-learn Isolation Forest anomaly detection on normalized records."""
    session = get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found or expired. Please upload a file first."
        )

    accepted_records = session["preprocessed_result"].get("accepted", [])
    contamination = request.contamination if request else 0.1
    random_state = request.random_state if request else 42

    result = detect_infrastructure_anomalies(
        records=accepted_records,
        upload_id=upload_id,
        contamination=contamination,
        random_state=random_state,
    )
    store_session_analysis(upload_id, "anomaly_detection", result.model_dump())
    return result


@router.post("/estimate-emissions/{upload_id}", response_model=EmissionsEstimationResponse)
def run_emissions_estimation_endpoint(
    upload_id: str,
    request: Optional[EmissionsEstimationRequest] = None,
):
    """Calculate energy consumption and location-based Scope 2 carbon footprint."""
    session = get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found or expired. Please upload a file first."
        )

    accepted_records = session["preprocessed_result"].get("accepted", [])
    result = estimate_energy_and_carbon(
        records=accepted_records,
        upload_id=upload_id,
        options=request,
    )
    store_session_analysis(upload_id, "emissions_estimation", result.model_dump())
    return result


@router.post("/analyze/{upload_id}", response_model=UnifiedAnalysisResponse)
def run_sustainability_analysis_endpoint(
    upload_id: str,
    anomaly_req: Optional[AnomalyDetectionRequest] = None,
    emissions_req: Optional[EmissionsEstimationRequest] = None,
):
    """Execute combined anomaly detection and energy/carbon estimation in a single call."""
    session = get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found or expired. Please upload a file first."
        )

    accepted_records = session["preprocessed_result"].get("accepted", [])
    contamination = anomaly_req.contamination if anomaly_req else 0.1
    random_state = anomaly_req.random_state if anomaly_req else 42

    anomaly_res = detect_infrastructure_anomalies(
        records=accepted_records,
        upload_id=upload_id,
        contamination=contamination,
        random_state=random_state,
    )
    emissions_res = estimate_energy_and_carbon(
        records=accepted_records,
        upload_id=upload_id,
        options=emissions_req,
    )

    store_session_analysis(upload_id, "anomaly_detection", anomaly_res.model_dump())
    store_session_analysis(upload_id, "emissions_estimation", emissions_res.model_dump())

    return UnifiedAnalysisResponse(
        upload_id=upload_id,
        filename=session["filename"],
        detected_provider=session["detected_provider"],
        anomaly_detection=anomaly_res,
        emissions_estimation=emissions_res,
    )


@router.get("/analysis/{upload_id}", response_model=UnifiedAnalysisResponse)
def get_sustainability_analysis_endpoint(upload_id: str):
    """Retrieve existing analysis results or compute them if not yet generated."""
    session = get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found or expired. Please upload a file first."
        )

    cached = get_session_analysis(upload_id) or {}
    accepted_records = session["preprocessed_result"].get("accepted", [])

    if "anomaly_detection" in cached and "emissions_estimation" in cached:
        anomaly_res = AnomalyDetectionResponse(**cached["anomaly_detection"])
        emissions_res = EmissionsEstimationResponse(**cached["emissions_estimation"])
    else:
        anomaly_res = detect_infrastructure_anomalies(records=accepted_records, upload_id=upload_id)
        emissions_res = estimate_energy_and_carbon(records=accepted_records, upload_id=upload_id)
        store_session_analysis(upload_id, "anomaly_detection", anomaly_res.model_dump())
        store_session_analysis(upload_id, "emissions_estimation", emissions_res.model_dump())

    return UnifiedAnalysisResponse(
        upload_id=upload_id,
        filename=session["filename"],
        detected_provider=session["detected_provider"],
        anomaly_detection=anomaly_res,
        emissions_estimation=emissions_res,
    )


# ---------------------------------------------------------------------------
# Phase 4: AI Insights and Optimization Recommendations Endpoints
# ---------------------------------------------------------------------------

@router.post("/recommendations/{upload_id}", response_model=CloudCarbonRecommendationsResponse)
def generate_recommendations_endpoint(
    upload_id: str,
    force_rule_based: bool = False,
):
    """Generate AI-powered anomaly explanations and optimization recommendations.

    - Reuses Phase 3 Isolation Forest anomaly detection and carbon calculations.
    - Prompts Gemini using summarized telemetry to produce actionable recommendations.
    - Gracefully falls back to deterministic rule-based analysis if Gemini is unavailable.
    - Guarantees metrics immutability: underlying telemetry and carbon data are never mutated.
    """
    session = get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found or expired. Please upload a file first."
        )

    cached = get_session_analysis(upload_id) or {}
    accepted_records = session["preprocessed_result"].get("accepted", [])

    # Ensure Phase 3 results exist in cache
    if "anomaly_detection" in cached and "emissions_estimation" in cached:
        anomaly_dict = cached["anomaly_detection"]
        emissions_dict = cached["emissions_estimation"]
    else:
        anomaly_res = detect_infrastructure_anomalies(records=accepted_records, upload_id=upload_id)
        emissions_res = estimate_energy_and_carbon(records=accepted_records, upload_id=upload_id)
        anomaly_dict = anomaly_res.model_dump()
        emissions_dict = emissions_res.model_dump()
        store_session_analysis(upload_id, "anomaly_detection", anomaly_dict)
        store_session_analysis(upload_id, "emissions_estimation", emissions_dict)

    recs_res = generate_cloud_carbon_insights(
        upload_id=upload_id,
        session=session,
        anomaly_detection=anomaly_dict,
        emissions_estimation=emissions_dict,
        force_rule_based=force_rule_based,
    )

    store_session_analysis(upload_id, "recommendations", recs_res.model_dump())
    return recs_res


@router.get("/recommendations/{upload_id}", response_model=CloudCarbonRecommendationsResponse)
def get_recommendations_endpoint(upload_id: str):
    """Retrieve existing recommendations or compute them on demand."""
    session = get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found or expired. Please upload a file first."
        )

    cached = get_session_analysis(upload_id) or {}
    if "recommendations" in cached:
        return CloudCarbonRecommendationsResponse(**cached["recommendations"])

    # If not cached, invoke generator endpoint logic
    return generate_recommendations_endpoint(upload_id=upload_id, force_rule_based=False)


