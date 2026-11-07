"""FastAPI router for Green Software Intelligence endpoints.

Prefix: /green
Tags:   Green Software

Endpoints:
  POST   /green/github/connect                      — connect a GitHub account
  GET    /green/github/accounts                      — list connected accounts
  DELETE /green/github/accounts/{account_id}          — disconnect an account
  GET    /green/github/accounts/{account_id}/repos    — list repositories
  GET    /green/github/repositories/{repo_id}/branches — list branches
  GET    /green/github/repositories/{repo_id}/pulls   — list pull requests
  GET    /green/github/repositories/{repo_id}/pulls/{pr_number} — PR + changed files
  POST   /green/analysis/analyze                     — run green-code analysis
  GET    /green/analysis/results/{pr_id}             — get findings + score
  GET    /green/analysis/scores                      — list all analysed PRs
  GET    /green/health                               — service health
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.green.database import get_db
from app.green.github_client import GitHubClient, GitHubClientError
from app.green.models import (
    CodeFinding,
    GitHubAccount,
    GreenCodeScore,
    PullRequest,
    Repository,
)
from app.green.schemas import (
    AccountResponse,
    AnalysisResultResponse,
    AnalyzeRequest,
    BranchResponse,
    ChangedFileResponse,
    ConnectRequest,
    DimensionScore,
    FindingResponse,
    PullRequestResponse,
    RepositoryResponse,
    ScoreResponse,
)
from app.green.scorer import calculate_score
from app.green.security import decrypt_token, encrypt_token
from app.green.static_analysis import analyze_files
from app.services.llm import generate_green_code_analysis

router = APIRouter(prefix="/green", tags=["Green Software"])


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _parse_json_response(response: str) -> list | dict:
    """Parse JSON from an LLM response, stripping markdown fences if present."""
    text = response.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


def _get_client_for_account(account: GitHubAccount) -> GitHubClient:
    """Build a GitHubClient from a stored account."""
    if account.is_demo:
        return GitHubClient(demo=True)
    token = decrypt_token(account.token_encrypted or "")
    if not token:
        raise HTTPException(status_code=401, detail="Stored token could not be decrypted.")
    return GitHubClient(token=token)


def _owner_repo(full_name: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, repo)."""
    parts = full_name.split("/", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail=f"Invalid repository name: {full_name}")
    return parts[0], parts[1]


# ─── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
def green_health():
    return {"status": "healthy", "module": "green_software"}


# ─── GitHub connection ─────────────────────────────────────────────────────────

@router.post("/github/connect", response_model=AccountResponse)
def connect_account(req: ConnectRequest, db: Session = Depends(get_db)):
    """Connect a GitHub account via personal access token or demo mode."""
    if not req.token and not req.demo:
        raise HTTPException(status_code=400, detail="Provide a token or set demo=true.")

    client = GitHubClient(token=req.token, demo=req.demo)
    try:
        user = client.get_user()
    except GitHubClientError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")

    username = user.get("login", "")
    if not username:
        raise HTTPException(status_code=502, detail="GitHub returned no username.")

    # Upsert account.
    account = db.query(GitHubAccount).filter(GitHubAccount.username == username).first()
    if account:
        account.token_encrypted = None if req.demo else encrypt_token(req.token)
        account.is_demo = req.demo
        account.display_name = user.get("name")
        account.avatar_url = user.get("avatar_url")
        account.html_url = user.get("html_url")
    else:
        account = GitHubAccount(
            username=username,
            token_encrypted=None if req.demo else encrypt_token(req.token),
            is_demo=req.demo,
            display_name=user.get("name"),
            avatar_url=user.get("avatar_url"),
            html_url=user.get("html_url"),
        )
        db.add(account)

    db.commit()
    db.refresh(account)

    # Pre-fetch and store repositories.
    try:
        repos_data = client.list_repositories(username)
        for r in repos_data:
            existing = (
                db.query(Repository)
                .filter(Repository.github_id == r["id"], Repository.account_id == account.id)
                .first()
            )
            if existing:
                existing.full_name = r.get("full_name", existing.full_name)
                existing.name = r.get("name")
                existing.default_branch = r.get("default_branch")
                existing.private = r.get("private", False)
                existing.language = r.get("language")
                existing.html_url = r.get("html_url")
                existing.description = r.get("description")
            else:
                db.add(Repository(
                    account_id=account.id,
                    github_id=r["id"],
                    full_name=r.get("full_name", ""),
                    name=r.get("name"),
                    default_branch=r.get("default_branch"),
                    private=r.get("private", False),
                    language=r.get("language"),
                    html_url=r.get("html_url"),
                    description=r.get("description"),
                ))
        db.commit()
    except Exception:
        pass  # repos can be fetched later

    return AccountResponse(
        id=account.id,
        username=account.username,
        display_name=account.display_name,
        avatar_url=account.avatar_url,
        html_url=account.html_url,
        is_demo=account.is_demo,
    )


@router.get("/github/accounts", response_model=list[AccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.query(GitHubAccount).order_by(GitHubAccount.created_at.desc()).all()
    return [
        AccountResponse(
            id=a.id,
            username=a.username,
            display_name=a.display_name,
            avatar_url=a.avatar_url,
            html_url=a.html_url,
            is_demo=a.is_demo,
        )
        for a in accounts
    ]


@router.delete("/github/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(GitHubAccount).filter(GitHubAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")
    db.delete(account)
    db.commit()
    return {"message": f"Disconnected {account.username}"}


# ─── Repositories & branches ───────────────────────────────────────────────────

@router.get("/github/accounts/{account_id}/repositories", response_model=list[RepositoryResponse])
def list_repositories(account_id: int, db: Session = Depends(get_db)):
    account = db.query(GitHubAccount).filter(GitHubAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    # Refresh from GitHub.
    client = _get_client_for_account(account)
    try:
        repos_data = client.list_repositories(account.username)
        for r in repos_data:
            existing = (
                db.query(Repository)
                .filter(Repository.github_id == r["id"], Repository.account_id == account.id)
                .first()
            )
            if existing:
                existing.full_name = r.get("full_name", existing.full_name)
                existing.name = r.get("name")
                existing.default_branch = r.get("default_branch")
                existing.private = r.get("private", False)
                existing.language = r.get("language")
                existing.html_url = r.get("html_url")
                existing.description = r.get("description")
            else:
                db.add(Repository(
                    account_id=account.id,
                    github_id=r["id"],
                    full_name=r.get("full_name", ""),
                    name=r.get("name"),
                    default_branch=r.get("default_branch"),
                    private=r.get("private", False),
                    language=r.get("language"),
                    html_url=r.get("html_url"),
                    description=r.get("description"),
                ))
        db.commit()
    except Exception:
        pass  # return cached repos if GitHub is unreachable

    repos = db.query(Repository).filter(Repository.account_id == account_id).all()
    return [
        RepositoryResponse(
            id=r.id,
            github_id=r.github_id,
            full_name=r.full_name,
            name=r.name,
            default_branch=r.default_branch,
            private=r.private,
            language=r.language,
            html_url=r.html_url,
            description=r.description,
        )
        for r in repos
    ]


@router.get("/github/repositories/{repo_id}/branches", response_model=list[BranchResponse])
def list_branches(repo_id: int, db: Session = Depends(get_db)):
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")

    account = repo.account
    client = _get_client_for_account(account)
    owner, repo_name = _owner_repo(repo.full_name)
    try:
        branches = client.list_branches(owner, repo_name)
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return [
        BranchResponse(
            name=b.get("name", ""),
            commit_sha=(b.get("commit") or {}).get("sha"),
            protected=b.get("protected", False),
        )
        for b in branches
    ]


# ─── Pull requests ─────────────────────────────────────────────────────────────

@router.get("/github/repositories/{repo_id}/pulls", response_model=list[PullRequestResponse])
def list_pull_requests(repo_id: int, state: str = "open", db: Session = Depends(get_db)):
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")

    account = repo.account
    client = _get_client_for_account(account)
    owner, repo_name = _owner_repo(repo.full_name)
    try:
        prs_data = client.list_pull_requests(owner, repo_name, state=state)
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Sync PRs to DB.
    for pr in prs_data:
        pr_number = pr.get("number")
        existing = (
            db.query(PullRequest)
            .filter(PullRequest.repository_id == repo.id, PullRequest.pr_number == pr_number)
            .first()
        )
        if existing:
            existing.title = pr.get("title")
            existing.state = pr.get("state")
            existing.head_branch = (pr.get("head") or {}).get("ref")
            existing.base_branch = (pr.get("base") or {}).get("ref")
            existing.author = (pr.get("user") or {}).get("login")
            existing.html_url = pr.get("html_url")
            existing.changed_files_count = pr.get("changed_files", 0)
        else:
            db.add(PullRequest(
                repository_id=repo.id,
                pr_number=pr_number,
                title=pr.get("title"),
                body=pr.get("body"),
                state=pr.get("state"),
                head_branch=(pr.get("head") or {}).get("ref"),
                base_branch=(pr.get("base") or {}).get("ref"),
                author=(pr.get("user") or {}).get("login"),
                html_url=pr.get("html_url"),
                changed_files_count=pr.get("changed_files", 0),
            ))
    db.commit()

    pull_requests = (
        db.query(PullRequest)
        .filter(PullRequest.repository_id == repo.id)
        .order_by(PullRequest.pr_number.desc())
        .all()
    )
    return [
        PullRequestResponse(
            id=pr.id,
            pr_number=pr.pr_number,
            title=pr.title,
            state=pr.state,
            head_branch=pr.head_branch,
            base_branch=pr.base_branch,
            author=pr.author,
            html_url=pr.html_url,
            changed_files_count=pr.changed_files_count,
            analyzed=pr.analyzed_at is not None,
        )
        for pr in pull_requests
    ]


@router.get("/github/repositories/{repo_id}/pulls/{pr_number}")
def get_pull_request_detail(repo_id: int, pr_number: int, db: Session = Depends(get_db)):
    """Return PR metadata and the list of changed files (with patches/content)."""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")

    account = repo.account
    client = _get_client_for_account(account)
    owner, repo_name = _owner_repo(repo.full_name)

    try:
        pr_data = client.get_pull_request(owner, repo_name, pr_number)
        files = client.get_pr_files(owner, repo_name, pr_number)
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "pr_number": pr_number,
        "title": pr_data.get("title"),
        "state": pr_data.get("state"),
        "head_branch": (pr_data.get("head") or {}).get("ref"),
        "base_branch": (pr_data.get("base") or {}).get("ref"),
        "author": (pr_data.get("user") or {}).get("login"),
        "html_url": pr_data.get("html_url"),
        "repository_full_name": repo.full_name,
        "changed_files": [
            ChangedFileResponse(
                filename=f.get("filename", ""),
                status=f.get("status", ""),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                patch=f.get("patch"),
            )
            for f in files
        ],
    }


# ─── Analysis ──────────────────────────────────────────────────────────────────

@router.post("/analysis/analyze", response_model=AnalysisResultResponse)
def analyze_pr(req: AnalyzeRequest, enrich: bool = False, db: Session = Depends(get_db)):
    """Run green-code static analysis + LLM enrichment on a pull request.

    Set ``enrich=true`` to attempt Gemini-based explanations (may be slow).
    Without enrichment, findings use built-in default explanations.
    """
    repo = db.query(Repository).filter(Repository.id == req.repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")

    account = repo.account
    client = _get_client_for_account(account)
    owner, repo_name = _owner_repo(repo.full_name)

    # Fetch PR files from GitHub (or demo data).
    try:
        pr_data = client.get_pull_request(owner, repo_name, req.pr_number)
        files = client.get_pr_files(owner, repo_name, req.pr_number)
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Get or create the PR record.
    pr = (
        db.query(PullRequest)
        .filter(PullRequest.repository_id == repo.id, PullRequest.pr_number == req.pr_number)
        .first()
    )
    if not pr:
        pr = PullRequest(
            repository_id=repo.id,
            pr_number=req.pr_number,
            title=pr_data.get("title"),
            body=pr_data.get("body"),
            state=pr_data.get("state"),
            head_branch=(pr_data.get("head") or {}).get("ref"),
            base_branch=(pr_data.get("base") or {}).get("ref"),
            author=(pr_data.get("user") or {}).get("login"),
            html_url=pr_data.get("html_url"),
            changed_files_count=len(files),
        )
        db.add(pr)
        db.commit()
        db.refresh(pr)
    else:
        # Update metadata.
        pr.title = pr_data.get("title")
        pr.changed_files_count = len(files)

    # Clear old findings + score for this PR (re-analysis replaces).
    db.query(CodeFinding).filter(CodeFinding.pull_request_id == pr.id).delete()
    db.query(GreenCodeScore).filter(GreenCodeScore.pull_request_id == pr.id).delete()
    db.commit()

    # ── 1. Run static analysis ─────────────────────────────────────────────────
    findings, available_tools = analyze_files(files)

    # ── 2. LLM enrichment (best-effort, opt-in via enrich=true) ────────────────
    llm_enrichments: list[dict] = []
    if findings and enrich:
        findings_for_llm = json.dumps(
            [
                {
                    "index": i,
                    "rule_id": f.get("rule_id"),
                    "severity": f.get("severity"),
                    "category": f.get("category"),
                    "file": f.get("file_path"),
                    "line": f.get("line_start"),
                    "message": f.get("message"),
                    "snippet": (f.get("code_snippet") or "")[:300],
                }
                for i, f in enumerate(findings)
            ],
            indent=2,
        )
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(generate_green_code_analysis, findings_for_llm)
                llm_raw = future.result(timeout=30)
            llm_enrichments = _parse_json_response(llm_raw)
            if not isinstance(llm_enrichments, list):
                llm_enrichments = []
        except concurrent.futures.TimeoutError:
            llm_enrichments = []
        except Exception:
            llm_enrichments = []

    # Build a lookup from LLM response by index.
    llm_map: dict[int, dict] = {}
    if isinstance(llm_enrichments, list):
        for item in llm_enrichments:
            if isinstance(item, dict) and "index" in item:
                llm_map[int(item["index"])] = item

    # ── 3. Store findings in DB ────────────────────────────────────────────────
    for i, f in enumerate(findings):
        enrichment = llm_map.get(i, {})
        db.add(CodeFinding(
            pull_request_id=pr.id,
            tool=f.get("tool", "builtin"),
            rule_id=f.get("rule_id"),
            severity=f.get("severity", "low"),
            category=f.get("category", "code_quality"),
            file_path=f.get("file_path", ""),
            line_start=f.get("line_start"),
            line_end=f.get("line_end"),
            message=f.get("message", ""),
            code_snippet=f.get("code_snippet"),
            explanation=enrichment.get("explanation") or f.get("message"),
            recommendation=enrichment.get("recommendation") or "Review and optimize this code pattern.",
            esg_impact=enrichment.get("esg_impact") or "Inefficient code increases compute resource usage, contributing to higher energy consumption and carbon emissions.",
        ))

    # ── 4. Calculate score ────────────────────────────────────────────────────
    score_data = calculate_score(findings)

    db.add(GreenCodeScore(
        pull_request_id=pr.id,
        overall_score=score_data["overall_score"],
        dimension_scores=score_data["dimension_scores_json"],
        finding_count=score_data["finding_count"],
        high_priority_count=score_data["high_priority_count"],
        medium_priority_count=score_data["medium_priority_count"],
        low_priority_count=score_data["low_priority_count"],
    ))

    pr.analyzed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pr)

    # ── 5. Return full result ──────────────────────────────────────────────────
    return _build_analysis_result(pr, repo, db)


@router.get("/analysis/results/{pr_id}", response_model=AnalysisResultResponse)
def get_analysis_results(pr_id: int, db: Session = Depends(get_db)):
    pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Pull request not found.")
    return _build_analysis_result(pr, pr.repository, db)


@router.get("/analysis/scores")
def list_scores(db: Session = Depends(get_db)):
    """List all analysed PRs with their scores (history view)."""
    results = (
        db.query(PullRequest, GreenCodeScore, Repository)
        .join(GreenCodeScore, GreenCodeScore.pull_request_id == PullRequest.id)
        .join(Repository, Repository.id == PullRequest.repository_id)
        .order_by(GreenCodeScore.calculated_at.desc())
        .all()
    )
    return [
        {
            "pull_request_id": pr.id,
            "pr_number": pr.pr_number,
            "title": pr.title,
            "repository": repo.full_name,
            "overall_score": score.overall_score,
            "finding_count": score.finding_count,
            "high_priority_count": score.high_priority_count,
            "analyzed_at": (pr.analyzed_at.isoformat() if pr.analyzed_at else None),
        }
        for pr, score, repo in results
    ]


# ─── Internal: build the analysis result response ──────────────────────────────

def _build_analysis_result(pr: PullRequest, repo: Repository, db: Session) -> AnalysisResultResponse:
    findings = (
        db.query(CodeFinding)
        .filter(CodeFinding.pull_request_id == pr.id)
        .order_by(CodeFinding.severity.desc(), CodeFinding.line_start)
        .all()
    )
    score = db.query(GreenCodeScore).filter(GreenCodeScore.pull_request_id == pr.id).first()

    dimensions = DimensionScore()
    if score:
        dim_data = json.loads(score.dimension_scores)
        dimensions = DimensionScore(**dim_data)

    return AnalysisResultResponse(
        pull_request_id=pr.id,
        pr_number=pr.pr_number,
        title=pr.title,
        repository_full_name=repo.full_name if repo else None,
        findings=[
            FindingResponse(
                id=f.id,
                tool=f.tool,
                rule_id=f.rule_id,
                severity=f.severity,
                category=f.category,
                file_path=f.file_path,
                line_start=f.line_start,
                line_end=f.line_end,
                message=f.message,
                code_snippet=f.code_snippet,
                explanation=f.explanation,
                recommendation=f.recommendation,
                esg_impact=f.esg_impact,
            )
            for f in findings
        ],
        score=ScoreResponse(
            overall_score=score.overall_score if score else 100.0,
            dimensions=dimensions,
            finding_count=score.finding_count if score else 0,
            high_priority_count=score.high_priority_count if score else 0,
            medium_priority_count=score.medium_priority_count if score else 0,
            low_priority_count=score.low_priority_count if score else 0,
        ) if score else None,
        finding_count=len(findings),
        high_priority_count=sum(1 for f in findings if f.severity == "high"),
    )
