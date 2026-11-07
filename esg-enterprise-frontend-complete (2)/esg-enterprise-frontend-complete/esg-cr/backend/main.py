"""FastAPI app for PDF text extraction and ESG commitment extraction."""

import logging
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from commitment_extractor import CommitmentExtractionError, extract_commitments
from pdf_extractor import PDFExtractionError, extract_pdf
from policy_comparator import compare_policies, summarize
from risk_engine import build_risk_report
from recommendation_engine import build_recommendation_contexts, generate_recommendations
from schemas import (
    ComparePoliciesResponse, ExtractCommitmentsResponse, RiskReportResponse,
    RecommendationsResponse,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
UPLOADS_DIR = BASE_DIR / "uploads"
EXTRACTED_DIR = BASE_DIR / "extracted"
PDF_MAGIC = b"%PDF"

load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ESG Policy Intelligence", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500", "http://127.0.0.1:5500",
        "http://localhost:5501", "http://127.0.0.1:5501",
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:4173",
        "null",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str


class PageText(BaseModel):
    page_number: int
    extracted_text: str
    character_count: int


class ExtractPdfResponse(BaseModel):
    filename: str
    page_count: int
    pages: list[PageText]
    warnings: list[str] = Field(default_factory=list)


def _is_pdf_upload(filename: str | None, content_type: str | None, file_bytes: bytes) -> bool:
    """Check extension, content type, and PDF file header."""
    name = (filename or "").lower()
    has_pdf_extension = name.endswith(".pdf")
    looks_like_pdf_type = (content_type or "").lower() in {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
        "",
    }
    has_pdf_header = file_bytes.lstrip().startswith(PDF_MAGIC)
    return has_pdf_extension and looks_like_pdf_type and has_pdf_header


def _save_uploaded_pdf(file: UploadFile, file_bytes: bytes) -> tuple[str, Path]:
    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="No file was uploaded.")
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if not _is_pdf_upload(filename, file.content_type, file_bytes):
        raise HTTPException(
            status_code=400,
            detail="Invalid file. Please upload a valid PDF document.",
        )

    original_name = Path(filename).name
    saved_path = UPLOADS_DIR / f"{uuid4().hex}_{original_name}"
    saved_path.write_bytes(file_bytes)
    return original_name, saved_path


def _extract_pages(saved_path: Path) -> dict:
    try:
        return extract_pdf(saved_path)
    except PDFExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="The PDF file is corrupted or could not be processed.",
        ) from exc


@app.get("/")
def root() -> RedirectResponse:
    """OpenAPI docs. The IDE preview opens `/`, which is not an API route."""
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/extract-pdf", response_model=ExtractPdfResponse)
async def extract_pdf_endpoint(file: UploadFile = File(...)) -> ExtractPdfResponse:
    file_bytes = await file.read()
    original_name, saved_path = _save_uploaded_pdf(file, file_bytes)
    result = _extract_pages(saved_path)
    logger.info("Pages extracted: %s", result["page_count"])
    return ExtractPdfResponse(
        filename=original_name,
        page_count=result["page_count"],
        pages=result["pages"],
        warnings=result["warnings"],
    )


def _optional_comparison_llm():
    """Keep comparison deterministic; Hugging Face is reserved for recommendations."""
    return None


def _get_chunk_extractor():
    """Return the LLM-based chunk extractor for narrative PDFs."""
    try:
        from llm_client import extract_commitments_from_chunk
        return extract_commitments_from_chunk
    except Exception:
        return None


def _commitments_from_saved_pdf(saved_path: Path) -> tuple[list, list[str]]:
    result = _extract_pages(saved_path)
    try:
        commitments, extra_warnings = extract_commitments(
            result["pages"],
            _get_chunk_extractor(),
        )
    except CommitmentExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    warnings = list(result["warnings"]) + extra_warnings
    return commitments, warnings


@app.post("/api/compare-policies", response_model=ComparePoliciesResponse)
async def compare_policies_endpoint(
    old_policy: UploadFile = File(...),
    new_policy: UploadFile = File(...),
) -> ComparePoliciesResponse:
    old_bytes = await old_policy.read()
    new_bytes = await new_policy.read()
    old_name, old_path = _save_uploaded_pdf(old_policy, old_bytes)
    new_name, new_path = _save_uploaded_pdf(new_policy, new_bytes)

    old_commitments, old_warnings = _commitments_from_saved_pdf(old_path)
    new_commitments, new_warnings = _commitments_from_saved_pdf(new_path)

    try:
        # Core comparison is deterministic so the endpoint works without paid LLM credits.
        comparisons, compare_warnings = compare_policies(
            old_commitments,
            new_commitments,
            llm_comparer=_optional_comparison_llm(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Policy comparison failed: {exc}") from exc

    warnings = old_warnings + new_warnings + compare_warnings
    return ComparePoliciesResponse(
        old_filename=old_name,
        new_filename=new_name,
        old_commitment_count=len(old_commitments),
        new_commitment_count=len(new_commitments),
        comparison_summary=summarize(comparisons),
        comparisons=comparisons,
        warnings=warnings,
    )


@app.post("/api/full-analysis")
async def full_analysis_endpoint(
    old_policy: UploadFile = File(...),
    new_policy: UploadFile = File(...),
    use_ai_recommendations: bool = True,
):
    """Single demo endpoint: extraction -> comparison -> deterministic risk/ESG -> recommendations."""
    old_bytes = await old_policy.read()
    new_bytes = await new_policy.read()
    old_name, old_path = _save_uploaded_pdf(old_policy, old_bytes)
    new_name, new_path = _save_uploaded_pdf(new_policy, new_bytes)

    old_commitments, old_warnings = _commitments_from_saved_pdf(old_path)
    new_commitments, new_warnings = _commitments_from_saved_pdf(new_path)
    comparisons, compare_warnings = compare_policies(
        old_commitments, new_commitments, llm_comparer=_optional_comparison_llm()
    )
    risk_report = build_risk_report(comparisons)
    recommendation_contexts = build_recommendation_contexts(
        [row.model_dump() for row in comparisons],
        [item.model_dump() for item in old_commitments],
        [item.model_dump() for item in new_commitments],
    )
    recommendations, rec_warnings = generate_recommendations(
        risk_report["risks"], use_ai=use_ai_recommendations, contexts=recommendation_contexts
    )
    return {
        "old_filename": old_name,
        "new_filename": new_name,
        "old_commitment_count": len(old_commitments),
        "new_commitment_count": len(new_commitments),
        "comparison_summary": summarize(comparisons).model_dump(),
        "comparisons": [row.model_dump() for row in comparisons],
        "risk_report": risk_report,
        "recommendations": recommendations,
        "recommendation_count": len(recommendations),
        "warnings": old_warnings + new_warnings + compare_warnings + rec_warnings,
    }


@app.post("/api/risk-report", response_model=RiskReportResponse)
async def risk_report_endpoint(
    old_policy: UploadFile = File(...),
    new_policy: UploadFile = File(...),
) -> RiskReportResponse:
    """Run extraction + comparison + deterministic risk/ESG scoring in one call."""
    old_bytes = await old_policy.read()
    new_bytes = await new_policy.read()
    old_name, old_path = _save_uploaded_pdf(old_policy, old_bytes)
    new_name, new_path = _save_uploaded_pdf(new_policy, new_bytes)

    old_commitments, old_warnings = _commitments_from_saved_pdf(old_path)
    new_commitments, new_warnings = _commitments_from_saved_pdf(new_path)

    try:
        comparisons, compare_warnings = compare_policies(
            old_commitments, new_commitments, llm_comparer=_optional_comparison_llm()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Policy comparison failed: {exc}") from exc

    report = build_risk_report(comparisons)
    # Surface extraction/comparison warnings without changing the deterministic score.
    report["_warnings"] = old_warnings + new_warnings + compare_warnings
    return RiskReportResponse(
        old_filename=old_name,
        new_filename=new_name,
        **{k: v for k, v in report.items() if k != "_warnings"},
    )


@app.post("/api/recommendations", response_model=RecommendationsResponse)
async def recommendations_endpoint(
    old_policy: UploadFile = File(...),
    new_policy: UploadFile = File(...),
    use_ai: bool = True,
) -> RecommendationsResponse:
    """Generate recommendations from deterministic risk findings.

    AI is optional. If HF is not configured or fails, deterministic recommendations
    are returned so the endpoint remains usable for a demo.
    """
    old_bytes = await old_policy.read()
    new_bytes = await new_policy.read()
    old_name, old_path = _save_uploaded_pdf(old_policy, old_bytes)
    new_name, new_path = _save_uploaded_pdf(new_policy, new_bytes)

    old_commitments, old_warnings = _commitments_from_saved_pdf(old_path)
    new_commitments, new_warnings = _commitments_from_saved_pdf(new_path)
    comparisons, compare_warnings = compare_policies(
        old_commitments, new_commitments, llm_comparer=_optional_comparison_llm()
    )
    report = build_risk_report(comparisons)
    recommendation_contexts = build_recommendation_contexts(
        [row.model_dump() for row in comparisons],
        [item.model_dump() for item in old_commitments],
        [item.model_dump() for item in new_commitments],
    )
    recommendations, rec_warnings = generate_recommendations(
        report["risks"], use_ai=use_ai, contexts=recommendation_contexts
    )
    return RecommendationsResponse(
        recommendation_count=len(recommendations),
        recommendations=recommendations,
        warnings=old_warnings + new_warnings + compare_warnings + rec_warnings,
    )


@app.post("/api/extract-commitments", response_model=ExtractCommitmentsResponse)
async def extract_commitments_endpoint(
    file: UploadFile = File(...),
) -> ExtractCommitmentsResponse:
    file_bytes = await file.read()
    original_name, saved_path = _save_uploaded_pdf(file, file_bytes)
    result = _extract_pages(saved_path)

    try:
        commitments, extra_warnings = extract_commitments(
            result["pages"],
            None,
        )
    except CommitmentExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    warnings = list(result["warnings"]) + extra_warnings
    return ExtractCommitmentsResponse(
        filename=original_name,
        page_count=result["page_count"],
        commitment_count=len(commitments),
        commitments=commitments,
        warnings=warnings,
    )
