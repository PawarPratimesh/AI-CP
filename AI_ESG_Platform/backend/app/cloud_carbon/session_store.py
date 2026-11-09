"""Lightweight temporary session storage for uploaded batches with TTL cleanup."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Optional
import uuid

SESSION_TTL_SECONDS = 3600  # 1 hour
MAX_SESSIONS = 100

_SESSIONS: dict[str, dict[str, Any]] = {}


def create_session(
    filename: str,
    file_format: str,
    detected_provider: str,
    columns: list[str],
    raw_records: list[dict[str, Any]],
    column_mapping: dict[str, Any],
    preprocessed_result: dict[str, Any],
) -> str:
    """Store upload session and return unique upload_id."""
    cleanup_expired_sessions()

    upload_id = str(uuid.uuid4())
    _SESSIONS[upload_id] = {
        "upload_id": upload_id,
        "filename": filename,
        "file_format": file_format,
        "detected_provider": detected_provider,
        "columns": columns,
        "raw_records": raw_records,
        "column_mapping": column_mapping,
        "preprocessed_result": preprocessed_result,
        "created_at": time.time(),
    }
    return upload_id


def get_session(upload_id: str) -> Optional[dict[str, Any]]:
    """Retrieve session by upload_id if not expired."""
    session = _SESSIONS.get(upload_id)
    if not session:
        return None
    if time.time() - session["created_at"] > SESSION_TTL_SECONDS:
        _SESSIONS.pop(upload_id, None)
        return None
    return session


def update_session_mapping(
    upload_id: str,
    updated_mapping: dict[str, Any],
    new_preprocessed_result: dict[str, Any]
) -> bool:
    """Update session with confirmed mapping and reprocessed records."""
    session = get_session(upload_id)
    if not session:
        return False
    session["column_mapping"] = updated_mapping
    session["preprocessed_result"] = new_preprocessed_result
    session["created_at"] = time.time()  # Refresh TTL
    return True


def store_session_analysis(upload_id: str, key: str, data: Any) -> bool:
    """Store analysis result (e.g. 'anomaly_detection', 'emissions_estimation') in session."""
    session = get_session(upload_id)
    if not session:
        return False
    if "analysis" not in session:
        session["analysis"] = {}
    session["analysis"][key] = data
    session["created_at"] = time.time()  # Refresh TTL
    return True


def get_session_analysis(upload_id: str) -> Optional[dict[str, Any]]:
    """Retrieve cached analysis results from session."""
    session = get_session(upload_id)
    if not session:
        return None
    return session.get("analysis", {})


def cleanup_expired_sessions() -> None:
    """Purge expired sessions or trim when exceeding MAX_SESSIONS."""
    now = time.time()
    expired = [k for k, v in _SESSIONS.items() if now - v["created_at"] > SESSION_TTL_SECONDS]
    for k in expired:
        _SESSIONS.pop(k, None)

    # Trim oldest if exceeding capacity
    if len(_SESSIONS) > MAX_SESSIONS:
        sorted_keys = sorted(_SESSIONS.keys(), key=lambda k: _SESSIONS[k]["created_at"])
        for k in sorted_keys[: len(_SESSIONS) - MAX_SESSIONS]:
            _SESSIONS.pop(k, None)

