"""Static analysis engine for green-code findings.

Detects software inefficiencies through two layers:

1. **Built-in pattern detector** — regex rules that always run and need no
   external dependencies.  Covers repeated API calls, N+1 queries, missing
   caching, unnecessary computation, and wasteful CI/CD patterns.
2. **External linters** — Ruff (Python), ESLint (JS/TS), and Semgrep (any
   language) are invoked via subprocess *when available*.  If a tool is not
   installed it is silently skipped, and findings from installed tools are
   merged with the built-in results.

All findings are normalised to a common schema so the scorer and LLM
enrichment work regardless of which tool produced them.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

# ─── Language detection ────────────────────────────────────────────────────────

_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".yml": "yaml",
    ".yaml": "yaml",
}


def detect_language(file_path: str) -> str | None:
    _, ext = os.path.splitext(file_path)
    return _LANGUAGE_MAP.get(ext.lower())


# ─── Built-in patterns ─────────────────────────────────────────────────────────
# Each pattern is a dict with: id, category, severity, message, regex, languages.

_BUILTIN_PATTERNS: list[dict[str, Any]] = [
    # ── Network: repeated API calls in a loop ──────────────────────────────────
    {
        "id": "GREEN-NET-001",
        "category": "network",
        "severity": "high",
        "message": "Repeated API/network call inside a loop — each iteration triggers a separate request.",
        "regex": re.compile(
            r"(?:for\s+\w+\s+of\s+.+|for\s+\w+\s+in\s+.+|for\s+\(.+\))"  # loop start
            r"[\s\S]{0,300}?"  # up to 300 chars
            r"(?:await\s+fetch\s*\(|fetch\s*\(|axios\.\w+\s*\(|requests\.\w+\s*\(|httpx\.\w+\s*\()",
            re.IGNORECASE,
        ),
        "languages": {"javascript", "typescript", "python"},
    },
    # ── Network: repeated fetch to same base without caching ──────────────────
    {
        "id": "GREEN-NET-002",
        "category": "network",
        "severity": "medium",
        "message": "Network request without caching — repeated calls to the same endpoint will re-fetch unnecessarily.",
        "regex": re.compile(
            r"(?:await\s+)?(?:fetch|axios\.\w+|requests\.\w+|httpx\.\w+)\s*\([^)]*\)(?!.*cache)",
            re.IGNORECASE,
        ),
        "languages": {"javascript", "typescript", "python"},
    },
    # ── Database: N+1 query inside a loop ──────────────────────────────────────
    {
        "id": "GREEN-DB-001",
        "category": "database",
        "severity": "high",
        "message": "Database query inside a loop (N+1 pattern) — batch the query instead of per-iteration lookups.",
        "regex": re.compile(
            r"(?:for\s+\w+\s+of\s+.+|for\s+\w+\s+in\s+.+|for\s+\(.+\))"
            r"[\s\S]{0,300}?"
            r"(?:\.query\s*\(|\.execute\s*\(|\.find\s*\(|\.findOne\s*\(|SELECT\s+.*?FROM|INSERT\s+INTO|UPDATE\s+\w+)",
            re.IGNORECASE,
        ),
        "languages": {"javascript", "typescript", "python"},
    },
    # ── Database: SELECT * (over-fetching) ─────────────────────────────────────
    {
        "id": "GREEN-DB-002",
        "category": "database",
        "severity": "medium",
        "message": "SELECT * retrieves all columns — fetching only needed columns reduces data transfer and memory.",
        "regex": re.compile(r"SELECT\s+\*", re.IGNORECASE),
        "languages": {"python", "sql"},
    },
    # ── Caching: no caching indicator near expensive calls ─────────────────────
    {
        "id": "GREEN-CACHE-001",
        "category": "caching",
        "severity": "medium",
        "message": "Expensive operation or fetch without apparent caching or memoization.",
        "regex": re.compile(
            r"(?:async\s+)?function\s+\w+\s*\([^)]*\)\s*\{[^}]*(?:fetch|requests\.\w+|\.query\(|expensiveCalc|compute)[^}]*\}",
            re.IGNORECASE,
        ),
        "languages": {"javascript", "typescript", "python"},
    },
    # ── Compute: expensive deep clone ─────────────────────────────────────────
    {
        "id": "GREEN-CPU-001",
        "category": "compute",
        "severity": "medium",
        "message": "JSON.parse(JSON.stringify(...)) performs an expensive full deep clone — use structuredClone or a targeted copy.",
        "regex": re.compile(r"JSON\.parse\s*\(\s*JSON\.stringify\s*\("),
        "languages": {"javascript", "typescript"},
    },
    # ── Compute: deepcopy (Python) ────────────────────────────────────────────
    {
        "id": "GREEN-CPU-002",
        "category": "compute",
        "severity": "medium",
        "message": "copy.deepcopy copies the entire object graph — consider a shallow copy or targeted field selection.",
        "regex": re.compile(r"copy\.deepcopy\s*\("),
        "languages": {"python"},
    },
    # ── Compute: chained map/filter/map (double iteration) ─────────────────────
    {
        "id": "GREEN-CPU-003",
        "category": "compute",
        "severity": "low",
        "message": "Chained .map().filter().map() iterates multiple times — combine into a single pass when possible.",
        "regex": re.compile(r"\.map\s*\([^)]*\)\s*\.filter\s*\([^)]*\)\s*\.map\s*\("),
        "languages": {"javascript", "typescript"},
    },
    # ── CI/CD: npm install instead of npm ci ──────────────────────────────────
    {
        "id": "GREEN-CICD-001",
        "category": "cicd",
        "severity": "medium",
        "message": "Using 'npm install' in CI instead of 'npm ci' — 'npm ci' is faster and deterministic for CI.",
        "regex": re.compile(r"npm\s+install(?!\s+--(save|dev|global))", re.MULTILINE),
        "languages": {"yaml"},
    },
    # ── CI/CD: missing cache step in GitHub Actions ────────────────────────────
    {
        "id": "GREEN-CICD-002",
        "category": "cicd",
        "severity": "medium",
        "message": "CI workflow has no caching step — adding dependency/action caching reduces build time and compute waste.",
        "regex": re.compile(
            r"(?:name:\s*CI|on:\s*\[)", re.IGNORECASE,
        ),
        "languages": {"yaml"},
        # Special: only flags if no "cache:" keyword appears in the file
        "negative_condition": "cache",
    },
    # ── CI/CD: redundant build steps (build after test without caching) ────────
    {
        "id": "GREEN-CICD-003",
        "category": "cicd",
        "severity": "low",
        "message": "CI runs lint, test, and build sequentially without caching — cache intermediate results to avoid recomputation.",
        "regex": re.compile(r"(?:npm\s+run\s+lint|npm\s+run\s+test|npm\s+run\s+build)", re.MULTILINE),
        "languages": {"yaml"},
    },
]


# ─── Finding normalisation ────────────────────────────────────────────────────

def _line_number(content: str, pos: int) -> int:
    """Convert a character offset to a 1-based line number."""
    return content.count("\n", 0, pos) + 1


def _snippet(content: str, line: int, context: int = 2) -> str:
    """Return a short code snippet around the given line."""
    lines = content.splitlines()
    start = max(0, line - 1 - context)
    end = min(len(lines), line + context)
    return "\n".join(lines[start:end])


def _run_builtin(content: str, file_path: str, language: str) -> list[dict[str, Any]]:
    """Run built-in regex patterns against file content."""
    findings: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()

    for pat in _BUILTIN_PATTERNS:
        if language not in pat["languages"]:
            continue

        # Skip pattern if negative condition text is present in the file.
        neg = pat.get("negative_condition")
        if neg and neg in content:
            continue

        for match in pat["regex"].finditer(content):
            span = (match.start(), match.end())
            # Deduplicate overlapping matches of the same pattern.
            if any(abs(span[0] - s[0]) < 10 and abs(span[1] - s[1]) < 10 for s in seen_spans):
                continue
            seen_spans.add(span)

            line = _line_number(content, match.start())
            findings.append({
                "tool": "builtin",
                "rule_id": pat["id"],
                "severity": pat["severity"],
                "category": pat["category"],
                "file_path": file_path,
                "line_start": line,
                "line_end": _line_number(content, match.end()),
                "message": pat["message"],
                "code_snippet": _snippet(content, line),
            })
    return findings


# ─── External linters ─────────────────────────────────────────────────────────

def _is_available(tool: str) -> bool:
    return shutil.which(tool) is not None


def _run_ruff(content: str, file_path: str) -> list[dict[str, Any]]:
    """Run Ruff on Python files if installed."""
    if not _is_available("ruff"):
        return []
    # Write content to a temp file for analysis.
    import tempfile

    suffix = os.path.splitext(file_path)[1] or ".py"
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", "--select=PERF,C90,E", tmp_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode not in (0, 1):
            return []
        data = json.loads(result.stdout or "[]")
        findings = []
        for item in data:
            findings.append({
                "tool": "ruff",
                "rule_id": item.get("code"),
                "severity": "medium" if item.get("fix") else "low",
                "category": "code_quality",
                "file_path": file_path,
                "line_start": item.get("location", {}).get("row"),
                "line_end": item.get("end_location", {}).get("row"),
                "message": item.get("message", ""),
                "code_snippet": _snippet(content, item.get("location", {}).get("row", 1)),
            })
        return findings
    except Exception:
        return []
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _run_semgrep(content: str, file_path: str) -> list[dict[str, Any]]:
    """Run Semgrep if installed — focuses on performance rules."""
    if not _is_available("semgrep"):
        return []
    import tempfile

    suffix = os.path.splitext(file_path)[1] or ".txt"
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["semgrep", "--json", "--config=p/performance", tmp_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode not in (0, 1):
            return []
        data = json.loads(result.stdout or "{}")
        findings = []
        for item in data.get("results", []):
            findings.append({
                "tool": "semgrep",
                "rule_id": item.get("check_id"),
                "severity": "medium" if item.get("extra", {}).get("severity") == "ERROR" else "low",
                "category": "compute",
                "file_path": file_path,
                "line_start": item.get("start", {}).get("line"),
                "line_end": item.get("end", {}).get("line"),
                "message": item.get("extra", {}).get("message", ""),
                "code_snippet": item.get("extra", {}).get("lines", ""),
            })
        return findings
    except Exception:
        return []
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _run_eslint(content: str, file_path: str) -> list[dict[str, Any]]:
    """Run ESLint if Node + npx are available."""
    if not _is_available("npx"):
        return []
    import tempfile

    ext = os.path.splitext(file_path)[1] or ".js"
    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["npx", "--yes", "eslint", "--format", "json", tmp_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode not in (0, 1):
            return []
        data = json.loads(result.stdout or "[]")
        findings = []
        for file_result in data:
            for msg in file_result.get("messages", []):
                sev = msg.get("severity", 0)
                findings.append({
                    "tool": "eslint",
                    "rule_id": msg.get("ruleId"),
                    "severity": "high" if sev >= 2 else "low",
                    "category": "code_quality",
                    "file_path": file_path,
                    "line_start": msg.get("line"),
                    "line_end": msg.get("endLine"),
                    "message": msg.get("message", ""),
                    "code_snippet": _snippet(content, msg.get("line", 1)),
                })
        return findings
    except Exception:
        return []
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ─── Public API ───────────────────────────────────────────────────────────────

def analyze_files(files: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Run static analysis across a list of changed files.

    Each file dict should have ``filename`` and either ``content`` (full text)
    or ``patch`` (GitHub diff).  Returns a list of normalised finding dicts.
    """
    all_findings: list[dict[str, Any]] = []
    available_tools: list[str] = []

    # Detect which external tools are available (for reporting).
    for tool in ("ruff", "semgrep", "npx"):
        if _is_available(tool):
            available_tools.append(tool)

    for f in files:
        filename = f.get("filename") or f.get("file_path", "unknown")
        language = detect_language(filename)

        # Prefer full content; fall back to patch text.
        content = f.get("content") or ""
        if not content:
            # Extract added lines from the patch for a best-effort scan.
            patch = f.get("patch") or ""
            content = "\n".join(
                line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")
            )

        if not content.strip():
            continue

        # Always run built-in patterns.
        all_findings.extend(_run_builtin(content, filename, language or "text"))

        # Run external tools based on language.
        if language == "python":
            all_findings.extend(_run_ruff(content, filename))
            all_findings.extend(_run_semgrep(content, filename))
        elif language in ("javascript", "typescript"):
            all_findings.extend(_run_eslint(content, filename))
            all_findings.extend(_run_semgrep(content, filename))
        elif language == "yaml":
            # CI/CD files — built-in patterns handle these well.
            pass

    # Deduplicate findings with the same tool + rule + file + line.
    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    for f in all_findings:
        key = (f["tool"], f.get("rule_id", ""), f["file_path"], f.get("line_start", 0))
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique, available_tools
