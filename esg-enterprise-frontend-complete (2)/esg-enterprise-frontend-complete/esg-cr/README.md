# ESG Policy Intelligence

Academic project built one feature at a time.

## Step 1 — PDF text extraction

Accept a PDF policy document and extract text page by page with PyMuPDF.

## Step 2 — ESG commitment extraction

Reuse Step 1 page extraction. For this project's structured policy register (records that start with `COMMITMENT ID:`), commitments are parsed **locally and for free**. Numbers, dates, IDs, and owners are copied from the PDF text. Nothing is invented.

A paid OpenAI key is **not required** for the 27-page Apex ESG policy.

An LLM is used only if the PDF has **no** `COMMITMENT ID:` records (narrative policies). Then the app can use OpenAI if you have credits.

The full document is never sent as one giant prompt.

## Prerequisites

- Python 3.11 or newer
- No API key needed for structured commitment registers
- Optional: Google Gemini (recommended, free tier) or OpenAI for narrative PDFs that have no COMMITMENT ID blocks
- For policy comparison (Step 3) an LLM key is required only when commitments cannot be classified deterministically

## Create a virtual environment

From the project root (`esg-cr`):

```bash
python -m venv .venv
```

Activate it:

**Windows (PowerShell)**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
source .venv/bin/activate
```

## Install requirements

```bash
pip install -r backend/requirements.txt
```

## API keys (optional)

Step 1 PDF extraction and Step 2 structured commitment parsing do **not** need an API key.

An LLM is required only for:
- Narrative PDFs with no `COMMITMENT ID:` blocks (Step 2 fallback)
- Policy comparison pairs where deterministic rules cannot classify the change (Step 3 fallback)

Do not commit `.env`. It is already in `.gitignore`.

### Recommended: Google Gemini (free tier available)

Get a free key at <https://aistudio.google.com/apikey> — no billing required for the free tier.

Model verified from the [official Gemini models page](https://ai.google.dev/gemini-api/docs/models)
(last checked 2026-09-17). `gemini-2.5-flash` is the current stable, free-tier model with the
best price-to-performance ratio in the 2.5 family.

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Free-tier rate limits (as of 2026-09-17): free input and output tokens under standard usage.
See the [Gemini pricing page](https://ai.google.dev/gemini-api/docs/pricing) for current limits.

### Alternative: OpenAI

OpenAI keys require billing credits. Creating a key does not automatically add credits.

```
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4o-mini
```

### How provider selection works

Set `LLM_PROVIDER` in `.env` to `gemini` or `openai`. It defaults to `openai` if not set,
preserving the original behaviour for anyone who has not yet added `LLM_PROVIDER`.

Both providers use the same `openai` Python package — no additional SDK is needed for Gemini.
Gemini is accessed via Google's officially supported OpenAI-compatible endpoint:
`https://generativelanguage.googleapis.com/v1beta/openai/`

Copy `.env.example` to `.env` and fill in the key for your chosen provider:

```powershell
Copy-Item .env.example .env
```

## Start FastAPI

From the project root, with the virtual environment activated:

```bash
uvicorn main:app --reload --app-dir backend
```

Or from the `backend` folder:

```bash
cd backend
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

Interactive docs: `http://127.0.0.1:8000/docs`

## Test `/health`

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Test `/api/extract-pdf` (Step 1)

```bash
curl -X POST "http://127.0.0.1:8000/api/extract-pdf" -F "file=@policy.pdf"
```

## Test `/api/extract-commitments` (Step 2)

Upload one PDF. The form field name must be `file`.

```bash
curl.exe -X POST "http://127.0.0.1:8000/api/extract-commitments" -F "file=@policy.pdf"
```

### Using Swagger /docs

1. Start the server.
2. Open `http://127.0.0.1:8000/docs`.
3. Find `POST /api/extract-commitments`.
4. Click **Try it out**.
5. Upload your 27-page ESG policy PDF.
6. Click **Execute**.

### Expected response structure

```json
{
  "filename": "policy.pdf",
  "page_count": 27,
  "commitment_count": 36,
  "commitments": [
    {
      "commitment_id": "GOV-010",
      "category": "Governance",
      "policy_statement": "...",
      "metric": "...",
      "baseline": "2021 = 0%",
      "target": "10% by 2026",
      "deadline": "31 December 2026",
      "responsible_owner": "Board Sustainability & Risk Committee",
      "scope": "Executive Committee members",
      "evidence_requirement": "...",
      "monitoring_frequency": "Annual",
      "escalation": "...",
      "source": {
        "page_numbers": [27],
        "evidence": "..."
      },
      "confidence": 0.99
    }
  ],
  "warnings": []
}
```

`commitment_count` is calculated from the extracted list. It is not hardcoded.

Missing document fields are returned as `null`. They are not invented.

## Step 3 — Policy version comparison

Compare an **old** policy PDF with a **new** policy PDF.

Pipeline:

1. Reuse Step 1 + Step 2 to extract commitments from each PDF.
2. Match commitments (exact `commitment_id` first, then content similarity if IDs are missing).
3. Compare fields with deterministic rules (targets, deadlines, scope, monitoring).
4. Use the LLM only for leftover ambiguous wording. Entire PDFs are never sent.

Classifications:

- `STRENGTHENED`, `WEAKENED`, `REDUCED`, `UNCHANGED` (primary)
- `NEW`, `REMOVED` (present only in one version)

No risk score or ESG score is calculated in this step.

### Endpoint

`POST /api/compare-policies`

Multipart field names:

- `old_policy`
- `new_policy`

```bash
curl.exe -X POST "http://127.0.0.1:8000/api/compare-policies" -F "old_policy=@old_policy.pdf" -F "new_policy=@new_policy.pdf"
```

Swagger: `http://127.0.0.1:8000/docs` → `POST /api/compare-policies` → upload both PDFs → Execute.

### Expected response structure

```json
{
  "old_filename": "old_policy.pdf",
  "new_filename": "new_policy.pdf",
  "old_commitment_count": 35,
  "new_commitment_count": 36,
  "comparison_summary": {
    "strengthened": 5,
    "weakened": 4,
    "reduced": 2,
    "unchanged": 25,
    "new": 1,
    "removed": 0
  },
  "comparisons": [
    {
      "old_commitment_id": "ENV-001",
      "new_commitment_id": "ENV-001",
      "classification": "WEAKENED",
      "reason": "The emissions reduction target changed from 40% to 30%.",
      "changed_fields": ["target"],
      "match_confidence": 0.99,
      "confidence": 0.96,
      "old_source": {"page_numbers": [10], "evidence": "..."},
      "new_source": {"page_numbers": [11], "evidence": "..."}
    }
  ],
  "warnings": []
}
```

Summary counts are calculated from the comparison list. They are not hardcoded.

## How chunking works

- Structured `COMMITMENT ID:` records are parsed from each page locally. This is free and keeps values exact.
- If a PDF has no such records, pages are chunked and sent to an LLM one chunk at a time. The full 27–40 page document is never one prompt.

## How duplicates are handled

The same commitment can appear in more than one chunk because of overlap.

Deduplication order:

1. `commitment_id` when present (for example `GOV-010`)
2. otherwise a normalized `policy_statement`
3. source page numbers are merged so evidence pages are not lost

## Evidence and page traceability

Every commitment includes `source.page_numbers` and a short `source.evidence` quote taken from the chunk. That is how a result such as GOV-010 can be checked against page 27 of the original PDF.

## Pytest

From the project root, with the virtual environment activated:

```bash
pytest tests/test_health.py tests/test_commitment_extractor.py tests/test_policy_comparator.py
```

Or:

```bash
pytest -q
```

Unit tests do not call the live OpenAI API. They cover PDF health, commitment parsing, matching, strengthened/reduced/weakened/unchanged/new/removed, ID matching, and evidence preservation.

Uploaded files are saved under `backend/uploads/`.


## Step 4 — Deterministic risk + ESG scoring

The core risk and score engine does not require an LLM.

`POST /api/risk-report` accepts `old_policy` and `new_policy`, extracts commitments, compares them using deterministic rules, then calculates:

- severity
- likelihood
- impact
- evidence quality
- risk score (0–100)
- LOW / MEDIUM / HIGH / CRITICAL level
- Environmental, Social and Governance scores
- overall ESG score

### Formula

```text
raw risk = (severity × likelihood × impact) / 125 × 100
evidence multiplier = 0.6 + (0.1 × evidence_quality)
final risk = raw risk × evidence multiplier
```

All four inputs use a 1–5 scale. The score is capped at 100.

ESG category score:

```text
category score = 100 - average risk score in that category
overall ESG = average(Environmental, Social, Governance)
```

Equal E/S/G weights are used. These assumptions are deterministic and visible in the API response.

## Step 5 — Recommendations

`POST /api/recommendations` runs the same extraction/comparison/risk pipeline and generates recommendations from the structured risk findings.

AI recommendations are optional and are attempted only when `HF_TOKEN` is configured. The core risk/ESG score never depends on the AI.

If no Hugging Face token is configured, the endpoint returns deterministic, evidence-based fallback recommendations instead of failing.

Optional `.env`:

```text
HF_TOKEN=your_token
HF_MODEL=Qwen/Qwen2.5-7B-Instruct
```

## One-call demo endpoint

For the final demo, use:

`POST /api/full-analysis`

Multipart fields:

- `old_policy`
- `new_policy`

Optional query parameter:

- `use_ai_recommendations=true` (default)

Example:

```bash
curl.exe -X POST "http://127.0.0.1:8000/api/full-analysis?use_ai_recommendations=false" -F "old_policy=@old_policy.pdf" -F "new_policy=@new_policy.pdf"
```

This returns:

```text
commitment extraction
→ comparison summary
→ detailed old/new evidence
→ deterministic risk findings
→ E/S/G + overall ESG scores
→ recommendations
```

Set `use_ai_recommendations=true` when `HF_TOKEN` is configured.

## Free/no-LLM demo note

The bundled 27-page Apex policy is a structured commitment register and is parsed locally without an API key.

The bundled older Apex policy in `backend/uploads/` is a 10-page compact commitment register and is also parsed locally. The extraction logic supports compact `ENV-001` / `SOC-001` / `GOV-001` register rows even when the full labeled fields are not present.

The uploaded project archive did not contain a 6-page policy; it contained a 10-page policy. The backend accepts any valid PDF, including a 6-page policy, as long as its commitments can be extracted.

If a narrative PDF has no structured commitment IDs/register rows, an LLM is still needed for that narrative extraction path.

## Standard-aligned methodology (Step 4 update)

The policy comparator and risk engine use documented, auditable rules rather than hidden scoring logic.

### Policy comparator

The comparison structure follows ESRS 2-style target attributes: target value, metric/unit, scope, baseline/base year, target period/deadline, milestones where available, and methodology/evidence. A commitment ID is a strong matching signal, but reused IDs are rejected when the policy statement, metric and target provide weak semantic support. Ambiguous changes are classified as `MODIFIED` instead of being guessed as stronger/weaker.

Classifications are `STRENGTHENED`, `WEAKENED`, `UNCHANGED`, `NEW`, `REMOVED`, and `MODIFIED`. For reduction metrics, a larger reduction percentage is stronger; an earlier deadline is stronger; wider scope and more frequent/stronger controls are strengthening signals. Generic first-number extraction is not used, preventing section numbers such as `4.6` from becoming targets.

### Risk engine

The risk workflow is aligned with ISO 31000:2018. The application uses a documented 5×5 matrix:

```text
Risk = Likelihood × Impact

1–4   Low
5–9   Moderate
10–16 High
17–25 Critical
```

Equivalent 0–100 display bands are 0–19.99 Low, 20–39.99 Moderate, 40–67.99 High and 68–100 Critical.

The API also exposes a 0–100 display score: `(Likelihood × Impact) / 25 × 100`. Likelihood and impact are 1–5. Evidence quality is reported separately and does not mathematically reduce risk.

**Important:** ISO 31000 provides the risk-management framework; it does not mandate this exact 5×5 numeric matrix or the application-specific classification mappings. Those operational criteria are documented in `METHODOLOGY.md` so they can be reviewed, tested and changed transparently.

See `METHODOLOGY.md` for the complete rules and rationale.
