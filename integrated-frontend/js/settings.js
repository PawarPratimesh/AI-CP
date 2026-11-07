const app = document.getElementById("page-app");
const current    = localStorage.getItem("esg_api_base")     || "http://localhost:8000";
const currentDoc = localStorage.getItem("esg_doc_api_base") || "http://localhost:8001";

app.innerHTML = `
<div class="grid-2">
  <section class="card">
    <div class="section-head"><div><h2>Organization</h2><p>Workspace identity and reporting context.</p></div></div>
    <div class="form-grid">
      <div class="field full"><label>Company Name</label><input value="Acme Global Logistics Corp"></div>
      <div class="field"><label>Industry</label><select><option>Logistics & Transportation</option><option>Manufacturing</option><option>Technology</option></select></div>
      <div class="field"><label>Reporting Period</label><select><option>FY 2025–26</option><option>FY 2024–25</option></select></div>
    </div>
  </section>

  <section class="card">
    <div class="section-head"><div><h2>Backend Connections</h2><p>Both backends must be running for full functionality.</p></div></div>
    <div class="field">
      <label>Policy Checker Backend URL <span class="badge badge-neutral" style="margin-left:6px">port 8000</span></label>
      <input id="api-url" value="${escapeHtml(current)}">
      <div class="small muted">Used by Policy Checker page. Start: <code>uvicorn main:app --reload --app-dir backend</code> in esg-cr/</div>
    </div>
    <div class="field" style="margin-top:14px">
      <label>Document Intelligence Backend URL <span class="badge badge-neutral" style="margin-left:6px">port 8001</span></label>
      <input id="doc-api-url" value="${escapeHtml(currentDoc)}">
      <div class="small muted">Used by Document Center and <b>Green Code</b> pages. Start: <code>uvicorn app.main:app --reload --port 8001</code> in AI_ESG_Platform/backend/</div>
    </div>
    <div class="toolbar" style="margin-top:14px">
      <button class="btn btn-primary" id="save-api">Save</button>
      <button class="btn btn-secondary" id="test-policy">Test Policy Backend</button>
      <button class="btn btn-secondary" id="test-doc">Test Document Backend</button>
      <span id="api-result"></span>
    </div>
  </section>

  <section class="card">
    <div class="section-head"><div><h2>ESG Configuration</h2><p>Risk thresholds and scoring weights.</p></div></div>
    <div class="form-grid">
      <div class="field"><label>High Risk Threshold</label><input value="70"></div>
      <div class="field"><label>Medium Risk Threshold</label><input value="40"></div>
      <div class="field"><label>Environmental Weight</label><input value="40%"></div>
      <div class="field"><label>Social Weight</label><input value="30%"></div>
      <div class="field"><label>Governance Weight</label><input value="30%"></div>
    </div>
  </section>

  <section class="card">
    <div class="section-head"><div><h2>Account</h2><p>Current workspace administrator.</p></div></div>
    <div style="display:flex;align-items:center;gap:11px">
      <div class="avatar">PS</div>
      <div><b>Pragati Sahu</b><div class="small muted">Project Admin</div></div>
    </div>
    <button class="btn btn-danger" style="margin-top:15px" data-toast="Logout is disabled in this demo">Logout</button>
  </section>
</div>

<div class="card" style="margin-top:16px">
  <div class="section-head"><div><h2>Quick Start Guide</h2><p>How to run the integrated platform.</p></div></div>
  <div class="grid-2">
    <div class="evidence">
      <div class="confidence">POLICY CHECKER BACKEND (port 8000)</div>
      <div class="quote" style="margin-top:8px">
        <code>cd "esg-enterprise-frontend-complete (2)/esg-enterprise-frontend-complete/esg-cr/backend"</code><br>
        <code>..\\.venv\\Scripts\\python.exe -m uvicorn main:app --reload --port 8000</code>
      </div>
    </div>
    <div class="evidence">
      <div class="confidence">DOCUMENT INTELLIGENCE BACKEND (port 8001)</div>
      <div class="quote" style="margin-top:8px">
        <code>cd AI_ESG_Platform/backend</code><br>
        <code>.venv\\Scripts\\activate</code><br>
        <code>uvicorn app.main:app --reload --port 8001</code>
      </div>
    </div>
  </div>
</div>`;

document.getElementById("save-api").onclick = () => {
  localStorage.setItem("esg_api_base",     document.getElementById("api-url").value.replace(/\/$/, ""));
  localStorage.setItem("esg_doc_api_base", document.getElementById("doc-api-url").value.replace(/\/$/, ""));
  toast("Backend URLs saved");
};

document.getElementById("test-policy").onclick = async () => {
  const r = document.getElementById("api-result");
  r.innerHTML = `<span class="small muted">Testing…</span>`;
  try { await ESGApi.health(); r.innerHTML = badge("Policy: Connected"); }
  catch { r.innerHTML = badge("Policy: Offline"); }
};

document.getElementById("test-doc").onclick = async () => {
  const r = document.getElementById("api-result");
  r.innerHTML = `<span class="small muted">Testing…</span>`;
  try { await ESGApi.docHealth(); r.innerHTML = badge("Docs: Connected"); }
  catch { r.innerHTML = badge("Docs: Offline"); }
};
