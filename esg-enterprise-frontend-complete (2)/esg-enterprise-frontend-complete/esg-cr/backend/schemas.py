"""Pydantic models for ESG commitment extraction."""

from pydantic import BaseModel, Field


class SourceEvidence(BaseModel):
    page_numbers: list[int]
    evidence: str


class Commitment(BaseModel):
    commitment_id: str | None = None
    category: str | None = None
    policy_statement: str | None = None
    metric: str | None = None
    baseline: str | None = None
    target: str | None = None
    deadline: str | None = None
    responsible_owner: str | None = None
    scope: str | None = None
    evidence_requirement: str | None = None
    monitoring_frequency: str | None = None
    escalation: str | None = None
    source: SourceEvidence
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractCommitmentsResponse(BaseModel):
    filename: str
    page_count: int
    commitment_count: int
    commitments: list[Commitment]
    warnings: list[str] = Field(default_factory=list)


class ComparisonSummary(BaseModel):
    strengthened: int = 0
    weakened: int = 0
    reduced: int = 0
    modified: int = 0
    unchanged: int = 0
    new: int = 0
    removed: int = 0


class CommitmentComparison(BaseModel):
    old_commitment_id: str | None = None
    new_commitment_id: str | None = None
    classification: str
    reason: str
    changed_fields: list[str] = Field(default_factory=list)
    match_confidence: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    old_source: SourceEvidence
    new_source: SourceEvidence


class ComparePoliciesResponse(BaseModel):
    old_filename: str
    new_filename: str
    old_commitment_count: int
    new_commitment_count: int
    comparison_summary: ComparisonSummary
    comparisons: list[CommitmentComparison]
    warnings: list[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    commitment_id: str | None = None
    category: str
    classification: str
    severity: str
    likelihood: int
    impact: int
    evidence_quality: int
    risk_score: float
    risk_level: str
    title: str
    description: str
    likelihood_reason: str
    impact_reason: str
    methodology: str
    evidence: str
    source: dict


class ESGScores(BaseModel):
    environmental: float
    social: float
    governance: float
    overall: float
    method: str


class RiskReportResponse(BaseModel):
    old_filename: str | None = None
    new_filename: str | None = None
    risk_count: int
    high_or_critical_count: int
    risks: list[RiskItem]
    esg_scores: ESGScores
    formula: dict


class RecommendationItem(BaseModel):
    title: str
    priority: str
    action: str
    basis: str
    source: str


class RecommendationsResponse(BaseModel):
    recommendation_count: int
    recommendations: list[RecommendationItem]
    warnings: list[str] = Field(default_factory=list)
