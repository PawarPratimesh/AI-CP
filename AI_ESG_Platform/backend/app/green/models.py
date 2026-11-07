"""ORM models for Green Software Intelligence.

Tables:
  github_accounts   — connected GitHub accounts (token stored encrypted)
  repositories      — repositories accessible from a connected account
  pull_requests     — PRs retrieved from GitHub for analysis
  code_findings     — individual green-code findings with LLM explanations
  green_code_scores — aggregate Green Code Score per PR
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.green.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GitHubAccount(Base):
    """A connected GitHub account (real token or demo mode)."""

    __tablename__ = "github_accounts"

    id = Column(Integer, primary_key=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    token_encrypted = Column(Text, nullable=True)  # Fernet-encrypted; null for demo
    avatar_url = Column(Text, nullable=True)
    html_url = Column(Text, nullable=True)
    display_name = Column(String(255), nullable=True)
    is_demo = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)

    repositories = relationship("Repository", back_populates="account", cascade="all, delete-orphan")


class Repository(Base):
    """A GitHub repository belonging to a connected account."""

    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("github_accounts.id", ondelete="CASCADE"), nullable=False)
    github_id = Column(Integer, nullable=False)
    full_name = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    default_branch = Column(String(255), nullable=True)
    private = Column(Boolean, default=False)
    language = Column(String(100), nullable=True)
    html_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    account = relationship("GitHubAccount", back_populates="repositories")
    pull_requests = relationship("PullRequest", back_populates="repository", cascade="all, delete-orphan")


class PullRequest(Base):
    """A pull request retrieved from GitHub for green-code analysis."""

    __tablename__ = "pull_requests"

    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    pr_number = Column(Integer, nullable=False)
    title = Column(String(500), nullable=True)
    body = Column(Text, nullable=True)
    state = Column(String(50), nullable=True)  # open, closed, merged
    head_branch = Column(String(255), nullable=True)
    base_branch = Column(String(255), nullable=True)
    author = Column(String(255), nullable=True)
    html_url = Column(Text, nullable=True)
    changed_files_count = Column(Integer, default=0)
    analyzed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    repository = relationship("Repository", back_populates="pull_requests")
    findings = relationship("CodeFinding", back_populates="pull_request", cascade="all, delete-orphan")
    score = relationship("GreenCodeScore", back_populates="pull_request", uselist=False, cascade="all, delete-orphan")


class CodeFinding(Base):
    """A single green-code finding from static analysis, with LLM enrichment."""

    __tablename__ = "code_findings"

    id = Column(Integer, primary_key=True)
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False)
    tool = Column(String(50), nullable=False)  # builtin, semgrep, ruff, eslint
    rule_id = Column(String(255), nullable=True)
    severity = Column(String(50), nullable=False)  # high, medium, low
    category = Column(String(100), nullable=False)  # efficiency dimension
    file_path = Column(String(500), nullable=False)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    code_snippet = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)  # LLM-generated
    recommendation = Column(Text, nullable=True)  # LLM-generated
    esg_impact = Column(Text, nullable=True)  # LLM-generated
    created_at = Column(DateTime, default=_utcnow)

    pull_request = relationship("PullRequest", back_populates="findings")


class GreenCodeScore(Base):
    """Aggregate Green Code Score for a pull request."""

    __tablename__ = "green_code_scores"

    id = Column(Integer, primary_key=True)
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False, unique=True)
    overall_score = Column(Float, nullable=False)
    dimension_scores = Column(Text, nullable=False)  # JSON string
    finding_count = Column(Integer, default=0)
    high_priority_count = Column(Integer, default=0)
    medium_priority_count = Column(Integer, default=0)
    low_priority_count = Column(Integer, default=0)
    calculated_at = Column(DateTime, default=_utcnow)

    pull_request = relationship("PullRequest", back_populates="score")
