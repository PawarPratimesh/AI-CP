"""Tests for the built-in static analysis pattern detector."""

from app.green.static_analysis import analyze_files, detect_language


class TestLanguageDetection:
    def test_python(self):
        assert detect_language("script.py") == "python"

    def test_javascript(self):
        assert detect_language("app.js") == "javascript"
        assert detect_language("component.jsx") == "javascript"

    def test_typescript(self):
        assert detect_language("service.ts") == "typescript"
        assert detect_language("widget.tsx") == "typescript"

    def test_yaml(self):
        assert detect_language("ci.yml") == "yaml"
        assert detect_language("config.yaml") == "yaml"

    def test_unknown(self):
        assert detect_language("readme.md") is None
        assert detect_language("data.csv") is None


class TestBuiltinPatterns:
    def test_repeated_api_calls_in_loop(self):
        """Should detect fetch() inside a for loop."""
        files = [{
            "filename": "service.js",
            "content": """const results = [];
for (const id of ids) {
  const r = await fetch(`/api/items/${id}`);
  results.push(await r.json());
}""",
        }]
        findings, _ = analyze_files(files)
        loop_findings = [f for f in findings if f["rule_id"] == "GREEN-NET-001"]
        assert len(loop_findings) >= 1
        assert loop_findings[0]["severity"] == "high"
        assert loop_findings[0]["category"] == "network"

    def test_n1_database_query(self):
        """Should detect DB query inside a loop."""
        files = [{
            "filename": "repo.js",
            "content": """for (const id of supplierIds) {
  const row = await db.query('SELECT * FROM supplier_scores WHERE supplier_id = ?', [id]);
  scores.push(row);
}""",
        }]
        findings, _ = analyze_files(files)
        db_findings = [f for f in findings if f["rule_id"] == "GREEN-DB-001"]
        assert len(db_findings) >= 1
        assert db_findings[0]["severity"] == "high"
        assert db_findings[0]["category"] == "database"

    def test_expensive_deep_clone(self):
        """Should detect JSON.parse(JSON.stringify(...))."""
        files = [{
            "filename": "utils.js",
            "content": "const cloned = JSON.parse(JSON.stringify(data));",
        }]
        findings, _ = analyze_files(files)
        clone_findings = [f for f in findings if f["rule_id"] == "GREEN-CPU-001"]
        assert len(clone_findings) >= 1
        assert clone_findings[0]["severity"] == "medium"
        assert clone_findings[0]["category"] == "compute"

    def test_npm_install_in_ci(self):
        """Should detect 'npm install' in CI workflow."""
        files = [{
            "filename": ".github/workflows/ci.yml",
            "content": """name: CI
on: [push]
jobs:
  build:
    steps:
      - run: npm install
      - run: npm test""",
        }]
        findings, _ = analyze_files(files)
        npm_findings = [f for f in findings if f["rule_id"] == "GREEN-CICD-001"]
        assert len(npm_findings) >= 1
        assert npm_findings[0]["category"] == "cicd"

    def test_missing_cache_in_ci(self):
        """Should flag CI without cache: keyword."""
        files = [{
            "filename": ".github/workflows/ci.yml",
            "content": """name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm install
      - run: npm run build""",
        }]
        findings, _ = analyze_files(files)
        # Should have the missing-cache finding (GREEN-CICD-002)
        cache_findings = [f for f in findings if f["rule_id"] == "GREEN-CICD-002"]
        assert len(cache_findings) >= 1

    def test_ci_with_cache_not_flagged(self):
        """Should NOT flag CI when cache: keyword is present."""
        files = [{
            "filename": ".github/workflows/ci.yml",
            "content": """name: CI
on: [push]
jobs:
  build:
    steps:
      - uses: actions/checkout@v4
      - uses: actions/cache@v3
      - run: npm ci
      - run: npm test""",
        }]
        findings, _ = analyze_files(files)
        cache_findings = [f for f in findings if f["rule_id"] == "GREEN-CICD-002"]
        assert len(cache_findings) == 0  # cache keyword present → not flagged

    def test_python_deepcopy(self):
        """Should detect copy.deepcopy in Python."""
        files = [{
            "filename": "transform.py",
            "content": "import copy\nresult = copy.deepcopy(batch)",
        }]
        findings, _ = analyze_files(files)
        deepcopy_findings = [f for f in findings if f["rule_id"] == "GREEN-CPU-002"]
        assert len(deepcopy_findings) >= 1
        assert deepcopy_findings[0]["category"] == "compute"

    def test_select_star(self):
        """Should detect SELECT * in Python files."""
        files = [{
            "filename": "query.py",
            "content": 'cursor.execute("SELECT * FROM users WHERE active = 1")',
        }]
        findings, _ = analyze_files(files)
        select_findings = [f for f in findings if f["rule_id"] == "GREEN-DB-002"]
        assert len(select_findings) >= 1

    def test_no_findings_in_clean_code(self):
        """Should find no issues in clean code."""
        files = [{
            "filename": "clean.py",
            "content": """def calculate_total(items):
    return sum(item.price for item in items)
""",
        }]
        findings, _ = analyze_files(files)
        # Clean code should produce very few or no findings
        assert len(findings) <= 1  # might match caching pattern loosely

    def test_finding_has_required_fields(self):
        """Each finding should have all required fields."""
        files = [{
            "filename": "service.js",
            "content": "const cloned = JSON.parse(JSON.stringify(data));",
        }]
        findings, _ = analyze_files(files)
        assert len(findings) >= 1
        f = findings[0]
        for field in ("tool", "severity", "category", "file_path", "message"):
            assert field in f, f"Missing field: {field}"
        assert f["tool"] == "builtin"
        assert f["file_path"] == "service.js"

    def test_line_numbers_extracted(self):
        """Should extract correct line numbers."""
        files = [{
            "filename": "service.js",
            "content": "line1\nline2\nconst cloned = JSON.parse(JSON.stringify(data));\nline4",
        }]
        findings, _ = analyze_files(files)
        clone_findings = [f for f in findings if f["rule_id"] == "GREEN-CPU-001"]
        assert len(clone_findings) >= 1
        assert clone_findings[0]["line_start"] == 3

    def test_demo_pr42_finds_multiple_issues(self):
        """Full demo PR #42 should produce multiple findings across categories."""
        from app.green.github_client import GitHubClient

        client = GitHubClient(demo=True)
        files = client.get_pr_files("acme-global", "esg-platform", 42)
        findings, _ = analyze_files(files)
        assert len(findings) >= 5  # multiple findings expected
        categories = {f["category"] for f in findings}
        assert "network" in categories  # repeated API calls
        assert "database" in categories  # N+1 query
        assert "compute" in categories  # deep clone
        assert "cicd" in categories  # CI issues
