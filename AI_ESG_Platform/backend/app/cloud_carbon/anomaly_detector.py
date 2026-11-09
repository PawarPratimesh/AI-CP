"""ML-based Infrastructure Anomaly Detection using Isolation Forest.

Identifies unusual infrastructure resource usage patterns from available
numerical metrics (CPU, Memory, Network, Storage).
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import numpy as np
from sklearn.ensemble import IsolationForest

from app.cloud_carbon.schemas import (
    AnomalyDetectionResponse,
    AnomalyRecordItem,
    CanonicalRecord,
)

logger = logging.getLogger(__name__)

# Candidate numerical features in priority order
CANDIDATE_NUMERICAL_FEATURES = [
    "cpu_utilization_pct",
    "memory_utilization_pct",
    "network_in",
    "network_out",
    "storage_used",
]

MIN_REQUIRED_OBSERVATIONS = 5


def detect_infrastructure_anomalies(
    records: list[CanonicalRecord],
    upload_id: str,
    contamination: float = 0.1,
    random_state: int = 42,
) -> AnomalyDetectionResponse:
    """Run Isolation Forest anomaly detection on canonical records.

    1. Determines which numerical metrics are reliably available across records.
    2. Filters out dimensions that are completely missing (does NOT treat missing metrics as 0).
    3. Requires at least MIN_REQUIRED_OBSERVATIONS (5) usable data points.
    4. Evaluates Isolation Forest and generates normalized anomaly scores (0.0 to 1.0).
    5. Attributes contributing metrics using transparent median/IQR distribution deviation.
    """
    if not records or len(records) < MIN_REQUIRED_OBSERVATIONS:
        return AnomalyDetectionResponse(
            upload_id=upload_id,
            status="INSUFFICIENT_DATA",
            features_used=[],
            total_records_analyzed=len(records) if records else 0,
            anomalies_detected=0,
            normal_records=len(records) if records else 0,
            anomaly_percentage=0.0,
            methodology_note=(
                f"Insufficient usable observations for ML training. At least "
                f"{MIN_REQUIRED_OBSERVATIONS} records are required, but {len(records) if records else 0} were provided."
            ),
            attribution_note="No anomaly analysis performed due to insufficient sample size.",
            anomalies=[],
        )

    # Step 1: Detect which candidate features actually have data across records
    usable_features = []
    for feat in CANDIDATE_NUMERICAL_FEATURES:
        valid_vals = [getattr(r, feat, None) for r in records if getattr(r, feat, None) is not None]
        # Include feature if at least 50% of records have non-null numeric values
        if len(valid_vals) >= max(3, len(records) * 0.5):
            usable_features.append(feat)

    if not usable_features:
        return AnomalyDetectionResponse(
            upload_id=upload_id,
            status="INSUFFICIENT_DATA",
            features_used=[],
            total_records_analyzed=len(records),
            anomalies_detected=0,
            normal_records=len(records),
            anomaly_percentage=0.0,
            methodology_note="No numerical metrics (CPU, Memory, Network, Storage) were present in the uploaded dataset.",
            attribution_note="No anomaly analysis performed.",
            anomalies=[],
        )

    # Step 2: Build feature matrix X and record indices
    # Impute missing values with column median if a record has sporadic missing entries
    # Compute median per usable feature
    medians: dict[str, float] = {}
    iqrs: dict[str, float] = {}
    for feat in usable_features:
        vals = [float(getattr(r, feat)) for r in records if getattr(r, feat, None) is not None]
        if vals:
            medians[feat] = float(np.median(vals))
            q75, q25 = np.percentile(vals, [75, 25])
            iqr = q75 - q25
            iqrs[feat] = float(iqr) if iqr > 1e-4 else (float(np.std(vals)) or 1.0)
        else:
            medians[feat] = 0.0
            iqrs[feat] = 1.0

    X_list = []
    for r in records:
        row = []
        for feat in usable_features:
            val = getattr(r, feat, None)
            if val is not None:
                row.append(float(val))
            else:
                row.append(medians[feat])
        X_list.append(row)

    X = np.array(X_list, dtype=np.float64)

    # Step 3: Fit Isolation Forest
    # Clamping contamination between 0.01 and 0.5
    safe_contamination = float(np.clip(contamination, 0.01, 0.5))
    model = IsolationForest(
        contamination=safe_contamination,
        random_state=random_state,
        n_estimators=100,
    )
    model.fit(X)

    # Predictions: 1 for inliers (Normal), -1 for outliers (Anomaly)
    predictions = model.predict(X)
    # Decision function: lower values mean more anomalous
    decision_scores = model.decision_function(X)

    # Normalize anomaly score to [0.0, 1.0] where 1.0 is most anomalous
    # decision_function typically ranges from ~ -0.5 (very anomalous) to +0.5 (very normal)
    min_score, max_score = float(np.min(decision_scores)), float(np.max(decision_scores))
    score_range = max_score - min_score if (max_score - min_score) > 1e-6 else 1.0

    # Step 4: Construct per-record results and attribution
    anomaly_items: list[AnomalyRecordItem] = []
    anomalies_detected = 0

    for idx, r in enumerate(records):
        is_anomaly = bool(predictions[idx] == -1)
        if is_anomaly:
            anomalies_detected += 1

        # Normalized anomaly score: 1.0 - (score - min) / range -> invert so high = anomalous
        normalized_score = float(np.clip(1.0 - ((decision_scores[idx] - min_score) / score_range), 0.0, 1.0))
        normalized_score = round(normalized_score, 4)

        # Transparent heuristic attribution: compare observation to median and IQR
        contributing: list[str] = []
        raw_metrics: dict[str, Optional[float]] = {}
        for feat_idx, feat in enumerate(usable_features):
            val = getattr(r, feat, None)
            raw_metrics[feat] = float(val) if val is not None else None
            if is_anomaly and val is not None:
                diff = float(val) - medians[feat]
                # Check deviation in terms of IQR or standard dev
                spread = iqrs[feat] if iqrs[feat] > 1e-4 else 1.0
                z_approx = diff / spread
                if abs(z_approx) >= 1.5:
                    direction = "+" if diff > 0 else ""
                    contributing.append(
                        f"{feat}: {val:.1f} (baseline median: {medians[feat]:.1f}, deviation: {direction}{diff:.1f})"
                    )

        anomaly_items.append(
            AnomalyRecordItem(
                record_index=idx + 1,
                resource_id=r.resource_id,
                timestamp=r.timestamp,
                status="Anomaly" if is_anomaly else "Normal",
                is_anomaly=is_anomaly,
                anomaly_score=normalized_score,
                contributing_metrics=contributing,
                raw_metrics=raw_metrics,
            )
        )

    normal_count = len(records) - anomalies_detected
    pct = round((anomalies_detected / len(records)) * 100.0, 2) if records else 0.0

    return AnomalyDetectionResponse(
        upload_id=upload_id,
        status="SUCCESS",
        features_used=usable_features,
        total_records_analyzed=len(records),
        anomalies_detected=anomalies_detected,
        normal_records=normal_count,
        anomaly_percentage=pct,
        methodology_note=(
            "Trained scikit-learn Isolation Forest on active numerical infrastructure metrics. "
            "Observations are scored based on mean isolation path lengths in randomized partition trees."
        ),
        attribution_note=(
            "Contributing metrics are identified using transparent heuristic distribution deviation "
            "(median and interquartile range comparison), not directly from Isolation Forest decision trees."
        ),
        anomalies=anomaly_items,
    )

