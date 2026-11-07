"""Pydantic request/response models for the Green Software API."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ─── Request models ───────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    """Connect a GitHub account via personal access token or demo mode."""
    token: Optional[str] = Field(
        default=None,
        description="GitHub personal access token. Omit for demo mode.",
    )
    demo: bool = Field(
        default=False,
        description="Set true to connect with sample data (no real GitHub needed).",
    )


class AnalyzeRequest(BaseModel):
    """Trigger green-code analysis on a pull request."""
    repository_id: int
    pr_number: int


# ─── Response models ───────────────────────────────────────────────────────────

class AccountResponse(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    html_url: Optional[str] = None
    is_demo: bool = False


class RepositoryResponse(BaseModel):
    id: int
    github_id: int
    full_name: str
    name: Optional[str] = None
    default_branch: Optional[str] = None
    private: bool = False
    language: Optional[str] = None
    html_url: Optional[str] = None
    description: Optional[str] = None


class BranchResponse(BaseModel):
    name: str
    commit_sha: Optional[str] = None
    protected: bool = False


class PullRequestResponse(BaseModel):
    id: Optional[int] = None
    pr_number: int
    title: Optional[str] = None
    state: Optional[str] = None
    head_branch: Optional[str] = None
    base_branch: Optional[str] = None
    author: Optional[str] = None
    html_url: Optional[str] = None
    changed_files_count: int = 0
    analyzed: bool = False


class ChangedFileResponse(BaseModel):
    filename: str
    status: str  # added, modified, removed, renamed
    additions: int = 0
    deletions: int = 0
    patch: Optional[str] = None  # GitHub diff patch text


class FindingResponse(BaseModel):
    id: int
    tool: str
    rule_id: Optional[str] = None
    severity: str
    category: str
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    message: str
    code_snippet: Optional[str] = None
    explanation: Optional[str] = None
    recommendation: Optional[str] = None
    esg_impact: Optional[str] = None


class DimensionScore(BaseModel):
    compute: float = 100.0
    network: float = 100.0
    database: float = 100.0
    caching: float = 100.0
    cicd: float = 100.0
    code_quality: float = 100.0


class ScoreResponse(BaseModel):
    overall_score: float
    dimensions: DimensionScore
    finding_count: int
    high_priority_count: int
    medium_priority_count: int
    low_priority_count: int


class AnalysisResultResponse(BaseModel):
    """Full analysis result: PR metadata + findings + score."""
    pull_request_id: int
    pr_number: int
    title: Optional[str] = None
    repository_full_name: Optional[str] = None
    findings: list[FindingResponse] = Field(default_factory=list)
    score: Optional[ScoreResponse] = None
    finding_count: int = 0
    high_priority_count: int = 0
