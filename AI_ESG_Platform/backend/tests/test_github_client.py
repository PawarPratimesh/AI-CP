"""Tests for the GitHub client (demo mode)."""

from app.green.github_client import GitHubClient, DEMO_USER, DEMO_REPOS


class TestGitHubClientDemo:
    """Demo mode tests — no real GitHub credentials needed."""

    def setup_method(self):
        self.client = GitHubClient(demo=True)

    def test_demo_flag_is_true(self):
        assert self.client.demo is True

    def test_get_user_returns_demo_user(self):
        user = self.client.get_user()
        assert user["login"] == DEMO_USER["login"]
        assert "avatar_url" in user
        assert "html_url" in user

    def test_list_repositories_returns_demo_repos(self):
        repos = self.client.list_repositories()
        assert len(repos) == len(DEMO_REPOS)
        assert repos[0]["full_name"] == "acme-global/esg-platform"
        assert repos[1]["full_name"] == "acme-global/data-services"

    def test_list_branches_returns_demo_branches(self):
        branches = self.client.list_branches("acme-global", "esg-platform")
        assert len(branches) >= 2
        assert any(b["name"] == "main" for b in branches)

    def test_list_pull_requests_returns_demo_prs(self):
        prs = self.client.list_pull_requests("acme-global", "esg-platform")
        assert len(prs) >= 1
        assert prs[0]["number"] == 42
        assert "title" in prs[0]

    def test_get_pull_request_returns_correct_pr(self):
        pr = self.client.get_pull_request("acme-global", "esg-platform", 42)
        assert pr["number"] == 42
        assert "Optimize" in pr["title"]

    def test_get_pr_files_returns_files_with_content(self):
        files = self.client.get_pr_files("acme-global", "esg-platform", 42)
        assert len(files) >= 3
        # Each file should have content for static analysis
        assert all("content" in f for f in files)
        # The report service file should contain repeated fetch calls
        report_files = [f for f in files if "reportService" in f.get("filename", "")]
        assert len(report_files) == 1
        assert "fetch(" in report_files[0]["content"]

    def test_get_pr_files_for_data_services(self):
        files = self.client.get_pr_files("acme-global", "data-services", 7)
        assert len(files) >= 1
        python_files = [f for f in files if f["filename"].endswith(".py")]
        assert len(python_files) >= 1
        assert "requests.get" in python_files[0]["content"]
