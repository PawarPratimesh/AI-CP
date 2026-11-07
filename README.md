# ESG Intelligence Platform

An AI-powered enterprise sustainability platform with two live backend services and one unified frontend.

---

## Project Structure

```
ESG_UPDATED/
├── integrated-frontend/          # Unified frontend (serve on port 5500)
├── AI_ESG_Platform/backend/      # Document Intelligence backend (port 8001)
└── esg-enterprise-frontend-complete (2)/
    └── esg-enterprise-frontend-complete/
        └── esg-cr/backend/       # Policy Checker backend (port 8000)
```

---

## Features

### Document Center
- Upload any ESG PDF
- Automatic text extraction, chunking, and vector embedding (sentence-transformers)
- Gemini AI batch ESG analysis — extracts commitments, targets, baselines, risks
- RAG-powered Q&A — ask questions about your documents

### Policy Checker
- Upload old and new policy PDFs
- Automatic commitment extraction (structured records or Gemini fallback for narrative PDFs)
- Side-by-side comparison: STRENGTHENED / WEAKENED / UNCHANGED / NEW / REMOVED / MODIFIED
- ISO 31000-aligned risk scoring
- AI recommendations (Hugging Face or deterministic fallback)

### Green Software Intelligence
- Connect a GitHub account (personal access token or demo mode)
- Browse repositories, branches, and pull requests
- Static analysis detects: repeated API calls, N+1 queries, missing caching, unnecessary computation, wasteful CI/CD
- External linters (Ruff, ESLint, Semgrep) auto-detected when installed
- LLM-powered explanations and ESG impact descriptions (opt-in via AI Enrichment checkbox)
- Transparent Green Code Score across 6 efficiency dimensions (network, database, compute, caching, cicd, code_quality)
- Database persistence: github_accounts, repositories, pull_requests, code_findings, green_code_scores
- **Demo mode** works without GitHub credentials — click "Use Demo Mode" on the Green Code page

---

## Setup & Run

### 1. Policy Checker Backend (port 8000)

```powershell
cd "esg-enterprise-frontend-complete (2)/esg-enterprise-frontend-complete/esg-cr/backend"
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

### 2. Document Intelligence Backend (port 8001)

```powershell
cd AI_ESG_Platform/backend
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

> **Note:** This backend also serves the Green Software Intelligence API (`/green/*` endpoints).
> Install dependencies first: `..\venv\Scripts\pip install sqlalchemy>=2.0 pytest`

### 3. Frontend (port 5500)

```powershell
cd integrated-frontend
C:\Python313\python.exe -m http.server 5500
```

Then open: **http://127.0.0.1:5500/login.html**

Login: `admin` / `esg2026`

---

## API Keys

Both backends use Gemini. Keys are in:
- `AI_ESG_Platform/backend/.env` — Document Intelligence
- `esg-enterprise-frontend-complete (2)/.../esg-cr/.env` — Policy Checker

Model: `gemini-3.8-flash` with automatic fallback to older models on quota errors.

---

## Health Checks

| Service | URL | Expected |
|---|---|---|
| Policy Checker | http://localhost:8000/health | `{"status":"ok"}` |
| Document Intelligence | http://localhost:8001/health | `{"status":"healthy"}` |
| Green Software | http://localhost:8001/green/health | `{"status":"healthy","module":"green_software"}` |
| API Docs (Policy) | http://localhost:8000/docs | Swagger UI |
| API Docs (Docs) | http://localhost:8001/docs | Swagger UI |

---

## Green Software Intelligence — API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/green/health` | Service health check |
| POST | `/green/github/connect` | Connect a GitHub account (`{"demo": true}` or `{"token": "ghp_..."}`) |
| GET | `/green/github/accounts` | List connected accounts |
| DELETE | `/green/github/accounts/{id}` | Disconnect an account |
| GET | `/green/github/accounts/{id}/repositories` | List repositories for an account |
| GET | `/green/github/repositories/{id}/branches` | List branches |
| GET | `/green/github/repositories/{id}/pulls?state=open` | List pull requests |
| GET | `/green/github/repositories/{id}/pulls/{pr_number}` | Get PR detail + changed files |
| POST | `/green/analysis/analyze` | Run analysis (`{"repository_id": 1, "pr_number": 42}`, add `?enrich=true` for LLM) |
| GET | `/green/analysis/results/{pr_id}` | Get findings + Green Code Score |
| GET | `/green/analysis/scores` | List all analyzed PRs |

### Running Tests

```powershell
cd AI_ESG_Platform/backend
..\venv\Scripts\python.exe -m pytest tests/ -v
```
| Document Intelligence | http://localhost:8001/health | `{"status":"healthy"}` |
| API Docs (Policy) | http://localhost:8000/docs | Swagger UI |
| API Docs (Docs) | http://localhost:8001/docs | Swagger UI |
