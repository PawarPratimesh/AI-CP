"""Integration tests for the Green Software API endpoints.

Uses FastAPI's TestClient against a minimal app containing only the green
router, with an isolated SQLite database per test session.
"""

import pytest


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/green/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["module"] == "green_software"


class TestConnect:
    def test_connect_demo_mode(self, client):
        resp = client.post("/green/github/connect", json={"demo": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "acme-global"
        assert data["is_demo"] is True
        assert "id" in data

    def test_connect_requires_token_or_demo(self, client):
        resp = client.post("/green/github/connect", json={})
        assert resp.status_code == 400

    def test_list_accounts_after_connect(self, client):
        # Connect first
        client.post("/green/github/connect", json={"demo": True})
        # Then list
        resp = client.get("/green/github/accounts")
        assert resp.status_code == 200
        accounts = resp.json()
        assert len(accounts) >= 1
        assert accounts[0]["username"] == "acme-global"


class TestRepositories:
    def test_list_repositories(self, client):
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        resp = client.get(f"/green/github/accounts/{account_id}/repositories")
        assert resp.status_code == 200
        repos = resp.json()
        assert len(repos) >= 2
        assert repos[0]["full_name"] == "acme-global/esg-platform"

    def test_list_branches(self, client):
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        repos = client.get(f"/green/github/accounts/{account_id}/repositories").json()
        repo_id = repos[0]["id"]
        resp = client.get(f"/green/github/repositories/{repo_id}/branches")
        assert resp.status_code == 200
        branches = resp.json()
        assert len(branches) >= 1
        assert any(b["name"] == "main" for b in branches)

    def test_repositories_for_nonexistent_account(self, client):
        resp = client.get("/green/github/accounts/99999/repositories")
        assert resp.status_code == 404


class TestPullRequests:
    def test_list_pull_requests(self, client):
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        repos = client.get(f"/green/github/accounts/{account_id}/repositories").json()
        repo_id = repos[0]["id"]
        resp = client.get(f"/green/github/repositories/{repo_id}/pulls?state=open")
        assert resp.status_code == 200
        prs = resp.json()
        assert len(prs) >= 1
        assert prs[0]["pr_number"] == 42

    def test_get_pr_detail(self, client):
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        repos = client.get(f"/green/github/accounts/{account_id}/repositories").json()
        repo_id = repos[0]["id"]
        resp = client.get(f"/green/github/repositories/{repo_id}/pulls/42")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pr_number"] == 42
        assert len(data["changed_files"]) >= 3


class TestAnalysis:
    def test_analyze_pr_without_enrich(self, client):
        """Full analysis flow: connect → repos → PRs → analyze."""
        # Connect
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        # Get repos
        repos = client.get(f"/green/github/accounts/{account_id}/repositories").json()
        repo_id = repos[0]["id"]
        # Analyze PR #42 (enrich=false by default)
        resp = client.post("/green/analysis/analyze", json={
            "repository_id": repo_id,
            "pr_number": 42,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["pr_number"] == 42
        assert data["finding_count"] >= 5
        assert data["score"] is not None
        assert data["score"]["overall_score"] < 100.0  # issues found → < 100
        # Check that findings have the expected fields
        findings = data["findings"]
        assert len(findings) >= 5
        assert "severity" in findings[0]
        assert "category" in findings[0]
        assert "file_path" in findings[0]
        assert "message" in findings[0]

    def test_analyze_pr_finds_network_issues(self, client):
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        repos = client.get(f"/green/github/accounts/{account_id}/repositories").json()
        repo_id = repos[0]["id"]
        resp = client.post("/green/analysis/analyze", json={
            "repository_id": repo_id,
            "pr_number": 42,
        })
        data = resp.json()
        categories = {f["category"] for f in data["findings"]}
        assert "network" in categories

    def test_analyze_pr_finds_database_issues(self, client):
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        repos = client.get(f"/green/github/accounts/{account_id}/repositories").json()
        repo_id = repos[0]["id"]
        resp = client.post("/green/analysis/analyze", json={
            "repository_id": repo_id,
            "pr_number": 42,
        })
        data = resp.json()
        categories = {f["category"] for f in data["findings"]}
        assert "database" in categories

    def test_get_results_after_analysis(self, client):
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        repos = client.get(f"/green/github/accounts/{account_id}/repositories").json()
        repo_id = repos[0]["id"]
        # Analyze
        analyze_resp = client.post("/green/analysis/analyze", json={
            "repository_id": repo_id,
            "pr_number": 42,
        })
        pr_id = analyze_resp.json()["pull_request_id"]
        # Get results
        resp = client.get(f"/green/analysis/results/{pr_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pr_number"] == 42
        assert len(data["findings"]) >= 5

    def test_list_scores(self, client):
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        repos = client.get(f"/green/github/accounts/{account_id}/repositories").json()
        repo_id = repos[0]["id"]
        # Analyze to create a score
        client.post("/green/analysis/analyze", json={
            "repository_id": repo_id,
            "pr_number": 42,
        })
        # List scores
        resp = client.get("/green/analysis/scores")
        assert resp.status_code == 200
        scores = resp.json()
        assert len(scores) >= 1
        assert scores[0]["pr_number"] == 42
        assert "overall_score" in scores[0]

    def test_analyze_nonexistent_repo(self, client):
        resp = client.post("/green/analysis/analyze", json={
            "repository_id": 99999,
            "pr_number": 1,
        })
        assert resp.status_code == 404


class TestDisconnect:
    def test_disconnect_account(self, client):
        connect = client.post("/green/github/connect", json={"demo": True})
        account_id = connect.json()["id"]
        resp = client.delete(f"/green/github/accounts/{account_id}")
        assert resp.status_code == 200
        # Verify it's gone
        accounts = client.get("/green/github/accounts").json()
        assert len(accounts) == 0

    def test_disconnect_nonexistent(self, client):
        resp = client.delete("/green/github/accounts/99999")
        assert resp.status_code == 404
