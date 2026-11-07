/**
 * Green Code Intelligence — Full Frontend Module
 *
 * Flow:
 *  1. Show connected GitHub accounts (or prompt to connect).
 *  2. Account selected → load repositories.
 *  3. Repo selected → load pull requests.
 *  4. PR selected → show detail view with [Analyze] button.
 *  5. Analysis complete → render Green Code Score + findings.
 *
 * All state is held in a plain object; every transition re-renders the
 * relevant section rather than replacing the whole page.
 */

(function () {
  "use strict";

  /* ─── Constants ─────────────────────────────────────────────────────────── */

  const GREEN_BASE = () =>
    (localStorage.getItem("esg_api_base") || "http://localhost:8000").replace(/\/$/, "");

  /* ─── State ─────────────────────────────────────────────────────────────── */

  const S = {
    accounts: [],
    selectedAccount: null,
    repos: [],
    selectedRepo: null,
    prs: [],
    selectedPr: null,
    prFilter: "open",
    analysisResult: null,
    loadingAccounts: false,
    loadingRepos: false,
    loadingPRs: false,
    analyzing: false,
    error: null,
    scores: [], // history
  };

  /* ─── DOM roots ─────────────────────────────────────────────────────────── */

  const root = document.getElementById("page-app");
  const primaryBtn = document.getElementById("page-primary-action");
  if (primaryBtn) primaryBtn.onclick = () => openConnectModal();

  /* ─── API helpers ────────────────────────────────────────────────────────── */

  async function api(path, opts = {}) {
    const url = GREEN_BASE() + path;
    let res;
    try {
      res = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
        ...opts,
      });
    } catch (e) {
      throw new Error("Network error: " + e.message);
    }
    let data = null;
    try {
      data = await res.json();
    } catch (_) {}
    if (!res.ok) {
      throw new Error(
        (data && (data.detail || data.message)) || "Request failed (" + res.status + ")"
      );
    }
    return data;
  }

  const GreenAPI = {
    connect: (token, demo) =>
      api("/green/github/connect", {
        method: "POST",
        body: JSON.stringify({ token: token || null, demo: !!demo }),
      }),
    listAccounts: () => api("/green/github/accounts"),
    deleteAccount: (id) => api("/green/github/accounts/" + id, { method: "DELETE" }),
    listRepos: (accountId) => api("/green/github/accounts/" + accountId + "/repositories"),
    listBranches: (repoId) => api("/green/github/repositories/" + repoId + "/branches"),
    listPRs: (repoId, state) =>
      api("/green/github/repositories/" + repoId + "/pulls?state=" + (state || "open")),
    getPR: (repoId, prNum) =>
      api("/green/github/repositories/" + repoId + "/pulls/" + prNum),
    analyze: (repositoryId, prNumber, enrich) =>
      api("/green/analysis/analyze" + (enrich ? "?enrich=true" : ""), {
        method: "POST",
        body: JSON.stringify({ repository_id: repositoryId, pr_number: prNumber }),
      }),
    getResults: (prId) => api("/green/analysis/results/" + prId),
    listScores: () => api("/green/analysis/scores"),
    health: () => api("/green/health"),
  };

  /* ─── Utilities ──────────────────────────────────────────────────────────── */

  function esc(s) {
    return String(s ?? "").replace(
      /[&<>"']/g,
      (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[m])
    );
  }

  function severityBadge(s) {
    const cls =
      s === "high"
        ? "badge-high"
        : s === "medium"
        ? "badge-medium"
        : s === "low"
        ? "badge-low"
        : "badge-neutral";
    return `<span class="badge ${cls}">${esc(s?.toUpperCase())}</span>`;
  }

  function categoryBadge(c) {
    const icons = {
      network: "⇄",
      database: "▤",
      compute: "⚙",
      caching: "⊛",
      cicd: "⌁",
      code_quality: "✓",
    };
    return `<span class="badge badge-neutral">${icons[c] || "•"} ${esc(c)}</span>`;
  }

  function scoreColor(v) {
    if (v >= 80) return "#2b9a67";
    if (v >= 60) return "#e6a817";
    return "#c84a3a";
  }

  function scoreBg(v) {
    if (v >= 80) return "#edf9f3";
    if (v >= 60) return "#fff8e6";
    return "#fdf1f0";
  }

  function scoreLabel(v) {
    if (v >= 80) return "Good";
    if (v >= 60) return "Fair";
    return "Poor";
  }

  function loading(el, msg) {
    el.innerHTML = `<div class="loading-state"><div class="spinner"></div><div class="muted">${esc(msg || "Loading…")}</div></div>`;
  }

  function errorBox(msg) {
    return `<div class="alert alert-error">${esc(msg)}</div>`;
  }

  function emptyState(msg, sub) {
    return `<div class="empty-state"><div style="font-size:28px;margin-bottom:8px">◌</div><b>${esc(msg)}</b>${sub ? `<div class="muted" style="margin-top:5px;font-size:11px">${esc(sub)}</div>` : ""}</div>`;
  }

  /* ─── Score ring SVG ─────────────────────────────────────────────────────── */

  function scoreRing(value, size = 100) {
    const r = 40;
    const circ = 2 * Math.PI * r;
    const offset = circ - (value / 100) * circ;
    const color = scoreColor(value);
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="${r}" fill="none" stroke="#e8ede9" stroke-width="10"/>
        <circle cx="50" cy="50" r="${r}" fill="none" stroke="${color}" stroke-width="10"
          stroke-dasharray="${circ}" stroke-dashoffset="${offset}"
          stroke-linecap="round" transform="rotate(-90 50 50)"
          style="transition:stroke-dashoffset .6s ease"/>
        <text x="50" y="46" text-anchor="middle" font-size="18" font-weight="800" fill="${color}">${Math.round(value)}</text>
        <text x="50" y="59" text-anchor="middle" font-size="9" fill="#8a9490">${scoreLabel(value)}</text>
      </svg>`;
  }

  /* ─── Dimension bar ──────────────────────────────────────────────────────── */

  function dimBar(label, value) {
    const color = scoreColor(value);
    return `
      <div style="margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px">
          <span style="color:#5e6b67;text-transform:capitalize">${esc(label.replace("_", " "))}</span>
          <span style="font-weight:800;color:${color}">${Math.round(value)}</span>
        </div>
        <div class="progress">
          <span style="width:${value}%;background:${color};transition:width .5s ease"></span>
        </div>
      </div>`;
  }

  /* ─── Main render ────────────────────────────────────────────────────────── */

  function render() {
    root.innerHTML = `
      <div id="gc-accounts-section"></div>
      <div id="gc-repos-section" style="${S.selectedAccount ? "" : "display:none"}"></div>
      <div id="gc-prs-section" style="${S.selectedRepo ? "" : "display:none"}"></div>
      <div id="gc-analysis-section"></div>
      <div id="gc-history-section"></div>
    `;
    renderAccounts();
    if (S.selectedAccount) renderRepos();
    if (S.selectedRepo) renderPRs();
    renderAnalysis();
    renderHistory();
  }

  /* ─── Accounts section ───────────────────────────────────────────────────── */

  function renderAccounts() {
    const el = document.getElementById("gc-accounts-section");
    if (!el) return;

    if (S.loadingAccounts) {
      el.innerHTML = `<div class="card" style="margin-bottom:14px">${loading(el, "Loading accounts…")}</div>`;
      return;
    }

    const accounts = S.accounts;
    el.innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="section-head">
          <div>
            <h2>GitHub Accounts</h2>
            <p>Connect your GitHub account to start analysing repositories for green-code patterns.</p>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <button class="btn btn-ghost" id="gc-refresh-accounts" style="font-size:11px">↻ Refresh</button>
            <button class="btn btn-primary" id="gc-connect-btn">+ Connect Account</button>
          </div>
        </div>
        <div id="gc-accounts-list">
          ${
            accounts.length === 0
              ? emptyState(
                  "No GitHub accounts connected",
                  "Click "+ Connect Account" or "Use Demo" to get started."
                )
              : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
              ${accounts
                .map(
                  (a) => `
                <div class="gc-account-card ${S.selectedAccount?.id === a.id ? "gc-account-selected" : ""}"
                     data-id="${a.id}" style="border:1.5px solid ${S.selectedAccount?.id === a.id ? "#2b8c69" : "#e4e9e6"};border-radius:10px;padding:14px;cursor:pointer;background:${S.selectedAccount?.id === a.id ? "#f0faf6" : "#fff"};transition:.15s">
                  <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
                    ${a.avatar_url ? `<img src="${esc(a.avatar_url)}" style="width:32px;height:32px;border-radius:50%;object-fit:cover" alt="">` : `<div style="width:32px;height:32px;border-radius:50%;background:#2b8c69;display:grid;place-items:center;color:white;font-weight:800;font-size:13px">${esc((a.username || "?")[0].toUpperCase())}</div>`}
                    <div>
                      <div style="font-weight:750;font-size:12px">${esc(a.display_name || a.username)}</div>
                      <div class="muted" style="font-size:10px">@${esc(a.username)}</div>
                    </div>
                    ${a.is_demo ? '<span class="badge badge-processing" style="margin-left:auto">DEMO</span>' : ""}
                  </div>
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <a href="${esc(a.html_url || "#")}" target="_blank" class="muted" style="font-size:10px">View on GitHub ↗</a>
                    <button class="btn btn-danger gc-disconnect-btn" data-id="${a.id}" style="font-size:10px;padding:5px 9px">Disconnect</button>
                  </div>
                </div>`
                )
                .join("")}
            </div>`
          }
        </div>
        ${
          accounts.length === 0
            ? `<div style="margin-top:12px;display:flex;gap:9px">
              <button class="btn btn-primary" id="gc-demo-btn">⚡ Use Demo Mode</button>
            </div>`
            : ""
        }
      </div>`;

    // Wire up buttons
    el.querySelector("#gc-connect-btn")?.addEventListener("click", openConnectModal);
    el.querySelector("#gc-refresh-accounts")?.addEventListener("click", loadAccounts);
    el.querySelector("#gc-demo-btn")?.addEventListener("click", connectDemo);

    el.querySelectorAll(".gc-account-card").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest(".gc-disconnect-btn")) return;
        const id = parseInt(card.dataset.id);
        S.selectedAccount = S.accounts.find((a) => a.id === id) || null;
        S.selectedRepo = null;
        S.prs = [];
        S.selectedPr = null;
        S.analysisResult = null;
        loadRepos();
      });
    });

    el.querySelectorAll(".gc-disconnect-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = parseInt(btn.dataset.id);
        if (!confirm("Disconnect this GitHub account?")) return;
        try {
          await GreenAPI.deleteAccount(id);
          if (S.selectedAccount?.id === id) {
            S.selectedAccount = null;
            S.selectedRepo = null;
            S.prs = [];
            S.selectedPr = null;
            S.analysisResult = null;
          }
          await loadAccounts();
        } catch (err) {
          toast("Error: " + err.message);
        }
      });
    });
  }

  /* ─── Repos section ──────────────────────────────────────────────────────── */

  function renderRepos() {
    const el = document.getElementById("gc-repos-section");
    if (!el) return;
    el.style.display = "";

    if (S.loadingRepos) {
      el.innerHTML = `<div class="card" style="margin-bottom:14px"><div class="loading-state"><div class="spinner"></div><div class="muted">Loading repositories…</div></div></div>`;
      return;
    }

    const repos = S.repos;
    el.innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="section-head">
          <div>
            <h2>Repositories</h2>
            <p>Select a repository to browse pull requests.</p>
          </div>
          <button class="btn btn-ghost" id="gc-refresh-repos" style="font-size:11px">↻ Refresh</button>
        </div>
        ${S.error ? errorBox(S.error) : ""}
        ${
          repos.length === 0
            ? emptyState("No repositories found", "Make sure your token has repository access.")
            : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px">
            ${repos
              .map(
                (r) => `
              <div class="gc-repo-card ${S.selectedRepo?.id === r.id ? "gc-repo-selected" : ""}"
                   data-id="${r.id}"
                   style="border:1.5px solid ${S.selectedRepo?.id === r.id ? "#2b8c69" : "#e4e9e6"};border-radius:10px;padding:13px;cursor:pointer;background:${S.selectedRepo?.id === r.id ? "#f0faf6" : "#fafcfb"};transition:.15s">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:5px">
                  <div style="font-weight:750;font-size:12px">${esc(r.name || r.full_name)}</div>
                  ${r.private ? '<span class="badge badge-neutral" style="font-size:9px">Private</span>' : ""}
                </div>
                <div class="muted" style="font-size:10px;margin-bottom:7px">${esc(r.full_name)}</div>
                ${r.description ? `<div style="font-size:10px;color:#64716d;margin-bottom:7px;line-height:1.4">${esc(r.description.slice(0, 80))}${r.description.length > 80 ? "…" : ""}</div>` : ""}
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                  ${r.language ? `<span class="badge badge-neutral" style="font-size:9px">⚙ ${esc(r.language)}</span>` : ""}
                  ${r.default_branch ? `<span class="badge badge-neutral" style="font-size:9px">⎇ ${esc(r.default_branch)}</span>` : ""}
                </div>
              </div>`
              )
              .join("")}
          </div>`
        }
      </div>`;

    el.querySelector("#gc-refresh-repos")?.addEventListener("click", loadRepos);
    el.querySelectorAll(".gc-repo-card").forEach((card) => {
      card.addEventListener("click", () => {
        const id = parseInt(card.dataset.id);
        S.selectedRepo = S.repos.find((r) => r.id === id) || null;
        S.prs = [];
        S.selectedPr = null;
        S.analysisResult = null;
        loadPRs();
      });
    });
  }

  /* ─── PRs section ────────────────────────────────────────────────────────── */

  function renderPRs() {
    const el = document.getElementById("gc-prs-section");
    if (!el) return;
    el.style.display = "";

    if (S.loadingPRs) {
      el.innerHTML = `<div class="card" style="margin-bottom:14px"><div class="loading-state"><div class="spinner"></div><div class="muted">Loading pull requests…</div></div></div>`;
      return;
    }

    const prs = S.prs;
    el.innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="section-head">
          <div>
            <h2>Pull Requests — <span style="color:#2b8c69">${esc(S.selectedRepo?.full_name || "")}</span></h2>
            <p>Select a pull request to analyse for green-code issues.</p>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <select id="gc-pr-filter" class="mini-select">
              <option value="open" ${S.prFilter === "open" ? "selected" : ""}>Open</option>
              <option value="closed" ${S.prFilter === "closed" ? "selected" : ""}>Closed</option>
              <option value="all" ${S.prFilter === "all" ? "selected" : ""}>All</option>
            </select>
            <button class="btn btn-ghost" id="gc-refresh-prs" style="font-size:11px">↻ Refresh</button>
          </div>
        </div>
        ${
          prs.length === 0
            ? emptyState("No pull requests found", "Try changing the filter or check your repository.")
            : `<div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Title</th>
                    <th>Author</th>
                    <th>Branch</th>
                    <th>Changed Files</th>
                    <th>Status</th>
                    <th>Analysed</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  ${prs
                    .map(
                      (pr) => `
                    <tr class="gc-pr-row ${S.selectedPr?.id === pr.id ? "gc-pr-selected" : ""}"
                        data-id="${pr.id}" data-num="${pr.pr_number}"
                        style="cursor:pointer${S.selectedPr?.id === pr.id ? ";background:#f0faf6" : ""}">
                      <td style="font-weight:700;color:#2b8c69">#${esc(String(pr.pr_number))}</td>
                      <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                        <a href="${esc(pr.html_url || "#")}" target="_blank" style="color:#163b52;font-weight:600" onclick="event.stopPropagation()">
                          ${esc(pr.title || "Untitled PR")}
                        </a>
                      </td>
                      <td class="muted">${esc(pr.author || "—")}</td>
                      <td><span class="badge badge-neutral" style="font-size:9px">⎇ ${esc(pr.head_branch || "—")}</span></td>
                      <td style="text-align:center">${esc(String(pr.changed_files_count || 0))}</td>
                      <td>${severityBadge(pr.state === "open" ? null : pr.state === "merged" ? "low" : "medium") /* abuse badge colours for state */ || `<span class="badge badge-neutral">${esc(pr.state)}</span>`}</td>
                      <td>${pr.analyzed ? '<span class="badge badge-success">✓ Yes</span>' : '<span class="badge badge-neutral">—</span>'}</td>
                      <td>
                        <button class="btn btn-primary gc-analyze-quick" data-id="${pr.id}" data-num="${pr.pr_number}" style="font-size:10px;padding:6px 10px">
                          Analyse →
                        </button>
                      </td>
                    </tr>`
                    )
                    .join("")}
                </tbody>
              </table>
            </div>`
        }
      </div>`;

    el.querySelector("#gc-pr-filter")?.addEventListener("change", (e) => {
      S.prFilter = e.target.value;
      loadPRs();
    });
    el.querySelector("#gc-refresh-prs")?.addEventListener("click", loadPRs);

    el.querySelectorAll(".gc-pr-row").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest(".gc-analyze-quick")) return;
        const id = parseInt(row.dataset.id);
        const num = parseInt(row.dataset.num);
        S.selectedPr = S.prs.find((p) => p.id === id) || { id, pr_number: num };
        S.analysisResult = null;
        render();
      });
    });

    el.querySelectorAll(".gc-analyze-quick").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const num = parseInt(btn.dataset.num);
        const id = parseInt(btn.dataset.id);
        S.selectedPr = S.prs.find((p) => p.id === id) || { id, pr_number: num };
        S.analysisResult = null;
        render();
        await runAnalysis();
      });
    });
  }

  /* ─── Analysis section ───────────────────────────────────────────────────── */

  function renderAnalysis() {
    const el = document.getElementById("gc-analysis-section");
    if (!el) return;

    if (!S.selectedPr) {
      el.innerHTML = "";
      return;
    }

    const pr = S.selectedPr;
    const res = S.analysisResult;

    el.innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="section-head">
          <div>
            <h2>PR Analysis — <span style="color:#2b8c69">#${esc(String(pr.pr_number))}</span>
              ${pr.title ? `<span style="font-weight:400;color:#74808b"> ${esc(pr.title)}</span>` : ""}</h2>
            <p>Green-code analysis: static patterns + LLM recommendations + ESG impact scoring.</p>
          </div>
          <div style="display:flex;gap:8px">
            ${res ? `<button class="btn btn-ghost" id="gc-reanalyze" style="font-size:11px">↻ Re-analyse</button>` : ""}
            <label style="font-size:11px;display:flex;align-items:center;gap:5px;cursor:pointer" title="Use Gemini LLM to explain findings and suggest fixes">
              <input type="checkbox" id="gc-use-enrich"> AI Enrichment
            </label>
            <button class="btn btn-primary" id="gc-run-analysis" ${S.analyzing ? "disabled" : ""}>
              ${S.analyzing ? "<span class='spinner' style='display:inline-block;width:14px;height:14px;margin-right:6px'></span> Analysing…" : "▶ Analyse PR"}
            </button>
          </div>
        </div>

        ${
          S.analyzing
            ? `<div class="loading-state" style="padding:36px">
                <div class="spinner"></div>
                <div class="muted" style="margin-top:10px">Running static analysis + LLM enrichment…</div>
                <div class="muted" style="font-size:10px;margin-top:4px">This may take 10–30 seconds</div>
              </div>`
            : res
            ? renderAnalysisResult(res)
            : `<div class="empty-state">
                <div style="font-size:28px;margin-bottom:8px">⌘</div>
                <b>Ready to analyse</b>
                <div class="muted" style="margin-top:5px;font-size:11px">Click "Analyse PR" to run static analysis and get LLM-powered green-code recommendations.</div>
              </div>`
        }
      </div>`;

    el.querySelector("#gc-run-analysis")?.addEventListener("click", runAnalysis);
    el.querySelector("#gc-reanalyze")?.addEventListener("click", runAnalysis);
  }

  function renderAnalysisResult(res) {
    const score = res.score;
    const findings = res.findings || [];
    const dims = score?.dimensions || {};

    const dimOrder = ["network", "database", "compute", "caching", "cicd", "code_quality"];

    // KPI strip
    const kpis = [
      {
        label: "Green Code Score",
        value: score ? Math.round(score.overall_score) + "/100" : "—",
        note: score ? scoreLabel(score.overall_score) : "",
        color: score ? scoreColor(score.overall_score) : "#2b8c69",
      },
      {
        label: "Findings",
        value: res.finding_count ?? findings.length,
        note: "total issues detected",
        color: "#4a7ec5",
      },
      {
        label: "High Priority",
        value: res.high_priority_count ?? 0,
        note: "require immediate action",
        color: "#c84a3a",
      },
      {
        label: "Repository",
        value: (res.repository_full_name || "").split("/")[1] || res.repository_full_name || "—",
        note: res.repository_full_name || "",
        color: "#2b8c69",
        small: true,
      },
    ];

    return `
      <!-- KPI strip -->
      <div class="kpi-strip" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px">
        ${kpis
          .map(
            (k) => `
          <div style="background:#fafcfb;border:1px solid #e4e9e6;border-radius:10px;padding:15px 16px">
            <div style="font-size:11px;color:#78838e;margin-bottom:6px">${esc(k.label)}</div>
            <div style="font-size:${k.small ? "15px" : "26px"};font-weight:800;color:${k.color};${k.small ? "margin-top:8px" : ""}">${esc(String(k.value))}</div>
            <div style="font-size:10px;color:#8a9490;margin-top:4px">${esc(k.note)}</div>
          </div>`
          )
          .join("")}
      </div>

      <!-- Score + dimensions -->
      ${
        score
          ? `<div style="display:grid;grid-template-columns:auto 1fr;gap:20px;margin-bottom:20px;align-items:center">
              <div style="text-align:center">
                ${scoreRing(score.overall_score, 120)}
                <div style="font-size:10px;color:#7a8480;margin-top:6px">Overall Green Score</div>
              </div>
              <div>
                <div style="font-size:11px;font-weight:750;color:#58656d;margin-bottom:10px">EFFICIENCY DIMENSIONS</div>
                ${dimOrder.map((d) => dimBar(d, dims[d] ?? 100)).join("")}
              </div>
            </div>`
          : ""
      }

      <!-- Findings -->
      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <div style="font-size:13px;font-weight:750">Code Findings <span style="font-size:11px;color:#78838e;font-weight:400">(${findings.length})</span></div>
          <div style="display:flex;gap:7px">
            <button class="btn btn-ghost gc-filter-btn active-filter" data-sev="all" style="font-size:10px;padding:5px 9px">All</button>
            <button class="btn btn-ghost gc-filter-btn" data-sev="high" style="font-size:10px;padding:5px 9px;color:#c84a3a">High</button>
            <button class="btn btn-ghost gc-filter-btn" data-sev="medium" style="font-size:10px;padding:5px 9px;color:#e6a817">Medium</button>
            <button class="btn btn-ghost gc-filter-btn" data-sev="low" style="font-size:10px;padding:5px 9px;color:#2b9a67">Low</button>
          </div>
        </div>

        <div id="gc-findings-list">
          ${findings.length === 0 ? emptyState("No findings detected", "This PR looks clean — no green-code issues found.") : renderFindings(findings)}
        </div>
      </div>
    `;
  }

  function renderFindings(findings, filter = "all") {
    const filtered = filter === "all" ? findings : findings.filter((f) => f.severity === filter);
    if (filtered.length === 0) {
      return `<div class="empty-state" style="padding:24px">No ${filter === "all" ? "" : filter + " "}findings to show.</div>`;
    }
    return filtered
      .map(
        (f, i) => `
      <div class="change-card gc-finding" style="border:1px solid #e4e9e6;border-radius:10px;margin-bottom:10px;overflow:hidden">
        <div class="change-head" style="padding:13px 15px;border-bottom:1px solid #f0f4f2;display:flex;align-items:flex-start;gap:10px">
          <div style="flex:1;min-width:0">
            <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:5px">
              ${severityBadge(f.severity)}
              ${categoryBadge(f.category)}
              ${f.tool !== "builtin" ? `<span class="badge badge-processing" style="font-size:9px">${esc(f.tool)}</span>` : ""}
              ${f.rule_id ? `<span class="muted" style="font-size:9px;font-family:monospace">${esc(f.rule_id)}</span>` : ""}
            </div>
            <div style="font-weight:700;font-size:12px;margin-bottom:3px">${esc(f.message)}</div>
            <div class="muted" style="font-size:10px">
              📄 ${esc(f.file_path)}
              ${f.line_start ? ` • line ${esc(String(f.line_start))}${f.line_end && f.line_end !== f.line_start ? "–" + esc(String(f.line_end)) : ""}` : ""}
            </div>
          </div>
          <button class="btn btn-ghost gc-toggle-detail" data-idx="${i}" style="font-size:18px;padding:2px 7px;color:#8a9490">⌄</button>
        </div>
        <div class="gc-finding-detail" id="gc-detail-${i}" style="display:none;padding:14px 15px;background:#fafcfb">
          ${
            f.code_snippet
              ? `<div class="code-block" style="margin-bottom:12px;font-size:10px;line-height:1.6">${esc(f.code_snippet)}</div>`
              : ""
          }
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
            <div>
              <div style="font-size:10px;font-weight:750;color:#58656d;margin-bottom:6px">🔍 EXPLANATION</div>
              <div style="font-size:11px;line-height:1.6;color:#384640">${esc(f.explanation || f.message)}</div>
            </div>
            <div>
              <div style="font-size:10px;font-weight:750;color:#58656d;margin-bottom:6px">✅ RECOMMENDATION</div>
              <div style="font-size:11px;line-height:1.6;color:#1e4d35" class="green-text">${esc(f.recommendation || "Review and optimise this code pattern.")}</div>
            </div>
          </div>
          ${
            f.esg_impact
              ? `<div style="margin-top:12px;background:#fff8e6;border:1px solid #f0dfbb;border-radius:8px;padding:11px 13px">
                  <div style="font-size:10px;font-weight:750;color:#7a5c1e;margin-bottom:4px">🌱 ESG IMPACT</div>
                  <div style="font-size:11px;line-height:1.6;color:#635011">${esc(f.esg_impact)}</div>
                </div>`
              : ""
          }
        </div>
      </div>`
      )
      .join("");
  }

  /* ─── History section ────────────────────────────────────────────────────── */

  function renderHistory() {
    const el = document.getElementById("gc-history-section");
    if (!el) return;
    if (!S.scores || S.scores.length === 0) {
      el.innerHTML = "";
      return;
    }

    el.innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="section-head">
          <div><h2>Analysis History</h2><p>Previously analysed pull requests with their Green Code Scores.</p></div>
          <button class="btn btn-ghost" id="gc-refresh-history" style="font-size:11px">↻ Refresh</button>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>PR</th><th>Title</th><th>Repository</th><th>Score</th><th>Findings</th><th>High</th><th>Analysed</th><th></th></tr>
            </thead>
            <tbody>
              ${S.scores
                .map(
                  (s) => `
                <tr>
                  <td style="font-weight:700;color:#2b8c69">#${esc(String(s.pr_number))}</td>
                  <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.title || "—")}</td>
                  <td class="muted">${esc(s.repository || "—")}</td>
                  <td>
                    <span style="font-weight:800;color:${scoreColor(s.overall_score)};background:${scoreBg(s.overall_score)};padding:3px 8px;border-radius:6px;font-size:11px">
                      ${Math.round(s.overall_score)}/100
                    </span>
                  </td>
                  <td style="text-align:center">${esc(String(s.finding_count || 0))}</td>
                  <td style="text-align:center;color:#c84a3a;font-weight:700">${esc(String(s.high_priority_count || 0))}</td>
                  <td class="muted" style="font-size:10px">${s.analyzed_at ? new Date(s.analyzed_at).toLocaleString() : "—"}</td>
                  <td>
                    <button class="btn btn-ghost gc-view-history" data-pr-id="${s.pull_request_id}" style="font-size:10px;padding:5px 9px">View →</button>
                  </td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </div>`;

    el.querySelector("#gc-refresh-history")?.addEventListener("click", loadHistory);
    el.querySelectorAll(".gc-view-history").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const prId = parseInt(btn.dataset.prId);
        try {
          const res = await GreenAPI.getResults(prId);
          S.analysisResult = res;
          S.selectedPr = { id: prId, pr_number: res.pr_number, title: res.title };
          render();
        } catch (err) {
          toast("Could not load results: " + err.message);
        }
      });
    });
  }

  /* ─── Connect modal ──────────────────────────────────────────────────────── */

  function openConnectModal() {
    let modal = document.getElementById("gc-connect-modal");
    if (modal) { modal.classList.add("open"); return; }

    modal = document.createElement("div");
    modal.id = "gc-connect-modal";
    modal.className = "modal-backdrop open";
    modal.innerHTML = `
      <div class="modal" style="max-width:480px">
        <div class="modal-head">
          <div>
            <div style="font-weight:800;font-size:14px">Connect GitHub Account</div>
            <div class="muted" style="font-size:11px;margin-top:3px">Enter a Personal Access Token or use Demo Mode</div>
          </div>
          <button id="gc-modal-close" class="btn btn-ghost" style="font-size:20px;padding:0 6px;color:#999">×</button>
        </div>
        <div class="modal-body">
          <div id="gc-modal-error"></div>
          <div class="field" style="margin-bottom:14px">
            <label>GitHub Personal Access Token</label>
            <input id="gc-token-input" type="password" placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
              style="font-family:monospace;letter-spacing:.04em">
            <div class="muted" style="font-size:10px;margin-top:4px">
              Needs <b>repo</b> and <b>read:user</b> scopes.
              <a href="https://github.com/settings/tokens/new" target="_blank" style="color:#2b8c69">Generate token ↗</a>
            </div>
          </div>
          <div style="display:flex;gap:10px">
            <button class="btn btn-primary" id="gc-modal-connect" style="flex:1">Connect with Token</button>
            <button class="btn btn-secondary" id="gc-modal-demo">⚡ Demo Mode</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);

    modal.querySelector("#gc-modal-close").onclick = () => modal.classList.remove("open");
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.remove("open"); });

    modal.querySelector("#gc-modal-connect").onclick = async () => {
      const token = modal.querySelector("#gc-token-input").value.trim();
      if (!token) {
        modal.querySelector("#gc-modal-error").innerHTML = errorBox("Please enter a token.");
        return;
      }
      await doConnect(token, false, modal);
    };

    modal.querySelector("#gc-modal-demo").onclick = async () => {
      await doConnect(null, true, modal);
    };
  }

  async function doConnect(token, demo, modal) {
    const errEl = modal?.querySelector("#gc-modal-error");
    const connectBtn = modal?.querySelector("#gc-modal-connect");
    const demoBtn = modal?.querySelector("#gc-modal-demo");
    if (connectBtn) connectBtn.disabled = true;
    if (demoBtn) demoBtn.disabled = true;
    if (errEl) errEl.innerHTML = "";

    try {
      await GreenAPI.connect(token, demo);
      modal?.classList.remove("open");
      toast("GitHub account connected!");
      await loadAccounts();
    } catch (err) {
      let msg = err.message;
      if (msg.toLowerCase().includes("network error") || msg.toLowerCase().includes("failed to fetch")) {
        msg = "Cannot reach the backend server (localhost:8000). Please make sure the backend is running and try again.";
      }
      if (errEl) errEl.innerHTML = errorBox(msg);
      else toast("Connection failed: " + msg);
    } finally {
      if (connectBtn) connectBtn.disabled = false;
      if (demoBtn) demoBtn.disabled = false;
    }
  }

  async function connectDemo() {
    try {
      await GreenAPI.connect(null, true);
      toast("Demo account connected!");
      await loadAccounts();
    } catch (err) {
      toast("Error: " + err.message);
    }
  }

  /* ─── Data loading ───────────────────────────────────────────────────────── */

  async function loadAccounts() {
    S.loadingAccounts = true;
    S.error = null;
    render();
    try {
      S.accounts = await GreenAPI.listAccounts();
      // If there's only one account auto-select it
      if (S.accounts.length === 1 && !S.selectedAccount) {
        S.selectedAccount = S.accounts[0];
        await loadRepos();
        return;
      }
    } catch (err) {
      S.error = err.message;
    } finally {
      S.loadingAccounts = false;
    }
    render();
    await loadHistory();
  }

  async function loadRepos() {
    if (!S.selectedAccount) return;
    S.loadingRepos = true;
    S.error = null;
    render();
    try {
      S.repos = await GreenAPI.listRepos(S.selectedAccount.id);
    } catch (err) {
      S.error = err.message;
      S.repos = [];
    } finally {
      S.loadingRepos = false;
    }
    render();
  }

  async function loadPRs() {
    if (!S.selectedRepo) return;
    S.loadingPRs = true;
    S.error = null;
    render();
    try {
      S.prs = await GreenAPI.listPRs(S.selectedRepo.id, S.prFilter);
    } catch (err) {
      S.error = err.message;
      S.prs = [];
    } finally {
      S.loadingPRs = false;
    }
    render();
  }

  async function runAnalysis() {
    if (!S.selectedRepo || !S.selectedPr) {
      toast("Select a repository and pull request first.");
      return;
    }
    S.analyzing = true;
    S.analysisResult = null;
    renderAnalysis();

    try {
      const enrich = document.getElementById("gc-use-enrich")?.checked || false;
      const res = await GreenAPI.analyze(S.selectedRepo.id, S.selectedPr.pr_number, enrich);
      S.analysisResult = res;
      // Mark PR as analysed in the list
      const pr = S.prs.find((p) => p.pr_number === S.selectedPr.pr_number);
      if (pr) pr.analyzed = true;
      toast("Analysis complete — " + (res.finding_count || 0) + " finding(s) found.");
      await loadHistory();
    } catch (err) {
      toast("Analysis failed: " + err.message);
    } finally {
      S.analyzing = false;
    }
    renderAnalysis();
    renderPRs();
  }

  async function loadHistory() {
    try {
      S.scores = await GreenAPI.listScores();
    } catch (_) {
      S.scores = [];
    }
    renderHistory();
  }

  /* ─── Finding filter / toggle wiring (event delegation) ─────────────────── */

  root.addEventListener("click", (e) => {
    // Filter buttons
    const filterBtn = e.target.closest(".gc-filter-btn");
    if (filterBtn) {
      const sev = filterBtn.dataset.sev;
      const findings = S.analysisResult?.findings || [];
      const listEl = document.getElementById("gc-findings-list");
      if (listEl) listEl.innerHTML = renderFindings(findings, sev);
      root.querySelectorAll(".gc-filter-btn").forEach((b) => b.classList.remove("active-filter"));
      filterBtn.classList.add("active-filter");
      // Re-wire toggles in the new list
      wireToggleDetails();
      return;
    }

    // Toggle detail panel
    const toggleBtn = e.target.closest(".gc-toggle-detail");
    if (toggleBtn) {
      const idx = toggleBtn.dataset.idx;
      const detail = document.getElementById("gc-detail-" + idx);
      if (detail) {
        const open = detail.style.display === "block";
        detail.style.display = open ? "none" : "block";
        toggleBtn.textContent = open ? "⌄" : "⌃";
      }
    }
  });

  function wireToggleDetails() {
    // Event delegation already handles this via root listener
  }

  /* ─── Bootstrap ──────────────────────────────────────────────────────────── */

  render();
  loadAccounts();
})();