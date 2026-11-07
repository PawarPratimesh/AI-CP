"""GitHub REST API client with demo-mode fallback.

When a real GitHub personal access token is supplied, all calls hit the live
GitHub REST API (v3).  When the caller requests demo mode (no token), the same
functions return curated sample data so the entire green-code workflow is
demonstrable without GitHub credentials.
"""

from __future__ import annotations

import os
from typing import Any

import requests

GITHUB_API = "https://api.github.com"


# ─── Demo data ─────────────────────────────────────────────────────────────────
# Curated sample data that exercises every code-efficiency pattern.

DEMO_USER: dict[str, Any] = {
    "login": "acme-global",
    "name": "Acme Global",
    "avatar_url": "https://avatars.githubusercontent.com/u/9919?v=4",
    "html_url": "https://github.com/acme-global",
    "type": "Organization",
}

DEMO_REPOS: list[dict[str, Any]] = [
    {
        "id": 100001,
        "full_name": "acme-global/esg-platform",
        "name": "esg-platform",
        "default_branch": "main",
        "private": False,
        "language": "JavaScript",
        "html_url": "https://github.com/acme-global/esg-platform",
        "description": "Enterprise ESG reporting platform — React + Node backend.",
    },
    {
        "id": 100002,
        "full_name": "acme-global/data-services",
        "name": "data-services",
        "default_branch": "main",
        "private": True,
        "language": "Python",
        "html_url": "https://github.com/acme-global/data-services",
        "description": "Python data ingestion and analytics microservices.",
    },
]

DEMO_BRANCHES: dict[str, list[dict[str, Any]]] = {
    "acme-global/esg-platform": [
        {"name": "main", "commit": {"sha": "a1b2c3d"}, "protected": True},
        {"name": "develop", "commit": {"sha": "e5f6g7h"}, "protected": False},
        {"name": "feature/carbon-api", "commit": {"sha": "i9j0k1l"}, "protected": False},
    ],
    "acme-global/data-services": [
        {"name": "main", "commit": {"sha": "m2n3o4p"}, "protected": True},
        {"name": "feature/batch-ingestion", "commit": {"sha": "q5r6s7t"}, "protected": False},
    ],
}

DEMO_PRS: dict[str, list[dict[str, Any]]] = {
    "acme-global/esg-platform": [
        {
            "number": 42,
            "title": "Optimize report generation pipeline",
            "body": "Reduce redundant API calls and add response caching to the report builder.",
            "state": "open",
            "head": {"ref": "optimize/reports"},
            "base": {"ref": "main"},
            "user": {"login": "sarah-dev"},
            "html_url": "https://github.com/acme-global/esg-platform/pull/42",
            "changed_files": 4,
        },
        {
            "number": 38,
            "title": "Refactor API layer with request batching",
            "body": "Batch supplier data requests to cut network round-trips.",
            "state": "open",
            "head": {"ref": "refactor/api-batching"},
            "base": {"ref": "main"},
            "user": {"login": "mike-eng"},
            "html_url": "https://github.com/acme-global/esg-platform/pull/38",
            "changed_files": 3,
        },
        {
            "number": 15,
            "title": "Update CI pipeline with dependency caching",
            "state": "merged",
            "head": {"ref": "ci/caching"},
            "base": {"ref": "main"},
            "user": {"login": "ci-bot"},
            "html_url": "https://github.com/acme-global/esg-platform/pull/15",
            "changed_files": 2,
        },
    ],
    "acme-global/data-services": [
        {
            "number": 7,
            "title": "Batch database queries in ingestion worker",
            "body": "Replace per-row lookups with a single batched query.",
            "state": "open",
            "head": {"ref": "fix/batch-queries"},
            "base": {"ref": "main"},
            "user": {"login": "sarah-dev"},
            "html_url": "https://github.com/acme-global/data-services/pull/7",
            "changed_files": 2,
        },
    ],
}

# Demo file contents keyed by repo/PR — these trigger the built-in patterns.
DEMO_PR_FILES: dict[tuple[str, int], list[dict[str, Any]]] = {
    ("acme-global/esg-platform", 42): [
        {
            "filename": "src/services/reportService.js",
            "status": "modified",
            "additions": 25,
            "deletions": 4,
            "content": """const API_BASE = 'https://api.esg-platform.io/v1';

async function buildReport(supplierIds) {
  const results = [];

  // Repeated API calls — same endpoint called in a loop
  for (const id of supplierIds) {
    const response = await fetch(`${API_BASE}/suppliers/${id}`);
    const data = await response.json();
    results.push(data);
  }

  // Same endpoint called again without caching
  const summary = await fetch(`${API_BASE}/suppliers/summary`);
  const summaryData = await summary.json();

  // Expensive deep clone
  const clonedResults = JSON.parse(JSON.stringify(results));

  return { results: clonedResults, summary: summaryData };
}

async function getSupplierMetrics(id) {
  // No cache — every call hits the network
  const res = await fetch(`${API_BASE}/suppliers/${id}/metrics`);
  return res.json();
}
""",
        },
        {
            "filename": "src/utils/export.js",
            "status": "modified",
            "additions": 12,
            "deletions": 2,
            "content": """export function transformExportData(records) {
  // Processes all fields even though export only needs 3 columns
  return records
    .map(r => ({ ...r, computed: expensiveCalc(r) }))
    .filter(r => r.active)
    .map(r => ({ id: r.id, name: r.name, date: r.date }));
}
""",
        },
        {
            "filename": ".github/workflows/ci.yml",
            "status": "modified",
            "additions": 18,
            "deletions": 0,
            "content": """name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install dependencies
        run: npm install
      - name: Lint
        run: npm run lint
      - name: Test
        run: npm test
      - name: Build
        run: npm run build
""",
        },
        {
            "filename": "src/repositories/esg.js",
            "status": "modified",
            "additions": 15,
            "deletions": 3,
            "content": """async function getSupplierScores(supplierIds) {
  const scores = [];
  // N+1 query pattern — one DB call per supplier inside a loop
  for (const id of supplierIds) {
    const row = await db.query('SELECT * FROM supplier_scores WHERE supplier_id = ?', [id]);
    scores.push(row);
  }
  return scores;
}
""",
        },
    ],
    ("acme-global/esg-platform", 38): [
        {
            "filename": "src/api/supplierApi.js",
            "status": "modified",
            "additions": 20,
            "deletions": 8,
            "content": """const API = 'https://api.esg-platform.io/v1';

async function getSuppliers(ids) {
  const results = [];
  for (const id of ids) {
    const r = await fetch(`${API}/suppliers/${id}`);
    results.push(await r.json());
  }
  return results;
}
""",
        },
        {
            "filename": "src/api/metricsApi.js",
            "status": "modified",
            "additions": 10,
            "deletions": 5,
            "content": """async function getMetrics() {
  // No caching of frequently accessed metrics
  const res = await fetch(`${API}/metrics/overview`);
  return res.json();
}
""",
        },
    ],
    ("acme-global/esg-platform", 15): [
        {
            "filename": ".github/workflows/ci.yml",
            "status": "modified",
            "additions": 10,
            "deletions": 4,
            "content": """name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install dependencies
        run: npm install
      - name: Build
        run: npm run build
""",
        },
    ],
    ("acme-global/data-services", 7): [
        {
            "filename": "ingestion/worker.py",
            "status": "modified",
            "additions": 18,
            "deletions": 5,
            "content": """import requests

API_URL = "https://api.esg-platform.io/v1"

def process_records(record_ids):
    results = []
    # Repeated API calls — one HTTP request per record
    for rid in record_ids:
        resp = requests.get(f"{API_URL}/records/{rid}")
        results.append(resp.json())

    # Same data fetched again without caching
    config = requests.get(f"{API_URL}/config").json()
    return results, config


def get_scores(supplier_ids):
    scores = []
    # N+1 database query pattern
    for sid in supplier_ids:
        row = db.execute("SELECT * FROM scores WHERE supplier_id = %s", (sid,))
        scores.append(row)
    return scores
""",
        },
        {
            "filename": "ingestion/transform.py",
            "status": "modified",
            "additions": 8,
            "deletions": 2,
            "content": """import copy

def transform_batch(batch):
    # Unnecessary deep copy of entire dataset
    cloned = copy.deepcopy(batch)
    return [transform_item(item) for item in cloned]
""",
        },
    ],
}


# ─── Client ─────────────────────────────────────────────────────────────────────

class GitHubClient:
    """Thin wrapper around the GitHub REST API with demo-mode support."""

    def __init__(self, token: str | None = None, demo: bool = False):
        self.token = token
        self.demo = demo or (token is None)

    # ─── helpers ───────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get(self, url: str) -> dict | list:
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if resp.status_code == 401:
            raise GitHubClientError("Invalid or expired GitHub token.")
        if resp.status_code == 403:
            # Rate limit or forbidden
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            raise GitHubClientError(
                f"GitHub API rate limit or forbidden (remaining: {remaining})."
            )
        if resp.status_code == 404:
            raise GitHubClientError("Repository or resource not found.")
        resp.raise_for_status()
        return resp.json()

    # ─── user ──────────────────────────────────────────────────────────────────

    def get_user(self) -> dict[str, Any]:
        if self.demo:
            return dict(DEMO_USER)
        return self._get(f"{GITHUB_API}/user")  # type: ignore[return-value]

    # ─── repositories ───────────────────────────────────────────────────────────

    def list_repositories(self, username: str | None = None) -> list[dict[str, Any]]:
        if self.demo:
            return [dict(r) for r in DEMO_REPOS]
        # Authenticated user's repos (includes orgs with appropriate scope)
        url = f"{GITHUB_API}/user/repos?per_page=100&sort=updated"
        return self._get(url)  # type: ignore[return-value]

    # ─── branches ──────────────────────────────────────────────────────────────

    def list_branches(self, owner: str, repo: str) -> list[dict[str, Any]]:
        if self.demo:
            return DEMO_BRANCHES.get(f"{owner}/{repo}", [])
        return self._get(f"{GITHUB_API}/repos/{owner}/{repo}/branches?per_page=100")  # type: ignore[return-value]

    # ─── pull requests ─────────────────────────────────────────────────────────

    def list_pull_requests(
        self, owner: str, repo: str, state: str = "open"
    ) -> list[dict[str, Any]]:
        if self.demo:
            return DEMO_PRS.get(f"{owner}/{repo}", [])
        return self._get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls?state={state}&per_page=50"
        )  # type: ignore[return-value]

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        if self.demo:
            prs = DEMO_PRS.get(f"{owner}/{repo}", [])
            for pr in prs:
                if pr["number"] == pr_number:
                    return dict(pr)
            raise GitHubClientError(f"PR #{pr_number} not found in demo data.")
        return self._get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}")  # type: ignore[return-value]

    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """Return changed files for a PR.

        In demo mode the ``content`` key carries the full file text so the
        static analyser can run.  In live mode the ``patch`` key carries the
        GitHub diff.
        """
        if self.demo:
            return [
                {k: v for k, v in f.items()}
                for f in DEMO_PR_FILES.get((f"{owner}/{repo}", pr_number), [])
            ]
        files = self._get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files?per_page=100"
        )
        # Optionally fetch full content for each file so the analyser has context.
        result: list[dict[str, Any]] = []
        for f in files:
            entry = {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": f.get("patch"),
            }
            # Try to fetch full content at the PR head for richer analysis.
            if f.get("status") in ("added", "modified", "renamed") and f.get("raw_url"):
                try:
                    raw = requests.get(f["raw_url"], timeout=20)
                    if raw.status_code == 200:
                        entry["content"] = raw.text
                except Exception:
                    pass  # patch-only is fine
            result.append(entry)
        return result


class GitHubClientError(Exception):
    """Raised when the GitHub API returns an error or data is unavailable."""
    pass
