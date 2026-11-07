// ─── Document Intelligence — wrapped in IIFE to avoid variable collisions ────
(function () {
// ─── state ───────────────────────────────────────────────────────────────────
const uploadedDocs = [];   // { document_id, filename, chunks_created, uploaded }
let activeDocId = null;    // currently selected document for analysis / Q&A

// ─── root element ─────────────────────────────────────────────────────────────
const app = document.getElementById("page-app");

// ─── render shell ─────────────────────────────────────────────────────────────
function render() {
  app.innerHTML = `
  <!-- backend status bar -->
  <div class="toolbar" style="margin-bottom:14px">
    <span id="doc-backend-status" class="badge badge-neutral">Checking Document Intelligence backend…</span>
    <div class="spacer"></div>
    <span class="badge badge-processing">AI Document Intelligence</span>
  </div>

  <!-- upload card -->
  <div class="card" style="margin-bottom:16px">
    <div class="section-head">
      <div>
        <h2>Upload ESG Document</h2>
        <p>Upload a PDF to extract text, embed it and store it for AI-powered Q&amp;A and ESG analysis.</p>
      </div>
      <span class="badge badge-success">Live backend</span>
    </div>
    <div class="file-drop" id="doc-drop">
      <input type="file" id="doc-input" accept=".pdf">
      <div style="font-size:22px">↑</div>
      <div style="font-weight:750;margin-top:6px">Drop a PDF here</div>
      <div class="small muted" style="margin:4px 0 10px">or choose a file from your computer</div>
      <button class="btn btn-secondary" id="choose-doc">Choose PDF</button>
      <div class="file-name" id="doc-name"></div>
    </div>
    <div id="upload-alert" style="margin-top:12px"></div>
    <div style="margin-top:12px;display:flex;gap:10px;align-items:center">
      <button class="btn btn-primary" id="upload-btn" disabled>Upload &amp; Process</button>
      <span id="upload-progress" class="small muted"></span>
    </div>
  </div>

  <!-- uploaded docs this session -->
  <div class="card" style="margin-bottom:16px">
    <div class="section-head">
      <div><h2>Uploaded Documents</h2><p>Documents processed in this session. Select one to analyze or ask questions.</p></div>
      <div class="search-box"><span class="search-icon">⌕</span><input id="doc-search" placeholder="Filter by name…"></div>
    </div>
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Filename</th><th>Chunks</th><th>Uploaded</th><th>ESG Status</th><th>Actions</th></tr></thead>
        <tbody id="doc-body"></tbody>
      </table>
    </div>
  </div>

  <!-- ESG analysis panel -->
  <div class="card" id="analysis-panel" style="margin-bottom:16px;display:none">
    <div class="section-head">
      <div><h2 id="analysis-title">ESG Analysis</h2><p>Gemini batch-analyzes all chunks and extracts commitments, targets, baselines and risks.</p></div>
      <button class="btn btn-primary" id="run-analysis-btn">Run ESG Analysis</button>
    </div>
    <div id="analysis-alert"></div>
    <div id="analysis-results"></div>
  </div>

  <!-- Q&A panel -->
  <div class="card" id="qa-panel" style="display:none">
    <div class="section-head">
      <div><h2>Ask the Document</h2><p>Ask any question about the uploaded ESG documents. Gemini answers using retrieved context.</p></div>
      <span class="badge badge-success">RAG-powered</span>
    </div>
    <div style="display:flex;gap:10px;margin-bottom:12px">
      <input id="qa-input" class="field input" style="flex:1;border:1px solid #dfe5e2;border-radius:8px;padding:10px 11px;font:inherit"
             placeholder="e.g. What are the renewable energy targets? What ESG risks are mentioned?">
      <button class="btn btn-primary" id="qa-btn">Ask</button>
    </div>
    <div id="qa-alert"></div>
    <div id="qa-results"></div>
  </div>`;

  bindEvents();
  checkBackend();
  renderDocTable();
}

// ─── backend status ────────────────────────────────────────────────────────────
async function checkBackend() {
  const el = document.getElementById("doc-backend-status");
  try {
    await ESGApi.docHealth();
    el.className = "badge badge-success";
    el.textContent = "Document Intelligence backend connected";
  } catch {
    el.className = "badge badge-high";
    el.textContent = "Document Intelligence backend offline (start on port 8000)";
  }
}

// ─── document table ────────────────────────────────────────────────────────────
function renderDocTable(filter = "") {
  const body = document.getElementById("doc-body");
  if (!body) return;
  const filtered = uploadedDocs.filter(d =>
    d.filename.toLowerCase().includes(filter.toLowerCase())
  );
  if (!filtered.length) {
    body.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#78838e;padding:22px">No documents uploaded yet this session.</td></tr>`;
    return;
  }
  body.innerHTML = filtered.map(d => `
    <tr>
      <td><b>${escapeHtml(d.filename)}</b><div class="small muted">${escapeHtml(d.document_id)}</div></td>
      <td>${d.chunks_created}</td>
      <td>${escapeHtml(d.uploaded)}</td>
      <td id="esg-status-${escapeHtml(d.document_id)}">${badge(d.esgStatus || "Not analyzed")}</td>
      <td style="display:flex;gap:7px">
        <button class="btn btn-secondary" onclick="selectDoc('${escapeHtml(d.document_id)}')">Select</button>
      </td>
    </tr>`).join("");
}

// ─── select a document ─────────────────────────────────────────────────────────
window.selectDoc = function(docId) {
  activeDocId = docId;
  const doc = uploadedDocs.find(d => d.document_id === docId);
  const analysisPanel = document.getElementById("analysis-panel");
  const qaPanel = document.getElementById("qa-panel");
  const title = document.getElementById("analysis-title");
  analysisPanel.style.display = "";
  qaPanel.style.display = "";
  if (doc) title.textContent = `ESG Analysis — ${doc.filename}`;
  document.getElementById("analysis-results").innerHTML = "";
  document.getElementById("analysis-alert").innerHTML = "";
  document.getElementById("qa-results").innerHTML = "";
  analysisPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  toast(`Document selected: ${doc?.filename || docId}`);
};

// ─── bind events ──────────────────────────────────────────────────────────────
function bindEvents() {
  const input = document.getElementById("doc-input");
  const drop  = document.getElementById("doc-drop");
  const nameEl = document.getElementById("doc-name");
  const uploadBtn = document.getElementById("upload-btn");

  document.getElementById("choose-doc").onclick = () => input.click();
  document.getElementById("page-primary-action").onclick = () => input.click();

  input.onchange = () => {
    nameEl.textContent = input.files[0]?.name || "";
    uploadBtn.disabled = !input.files[0];
  };

  ["dragenter", "dragover"].forEach(e =>
    drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add("drag"); })
  );
  ["dragleave", "drop"].forEach(e =>
    drop.addEventListener(e, ev => {
      ev.preventDefault(); drop.classList.remove("drag");
      if (e === "drop" && ev.dataTransfer.files[0]) {
        // Only accept PDF via drag
        const f = ev.dataTransfer.files[0];
        if (f.type === "application/pdf") {
          const dt = new DataTransfer();
          dt.items.add(f);
          input.files = dt.files;
          nameEl.textContent = f.name;
          uploadBtn.disabled = false;
        } else {
          setAlert("upload-alert", "error", "Only PDF files are supported.");
        }
      }
    })
  );

  uploadBtn.onclick = handleUpload;

  document.getElementById("doc-search").oninput = e => renderDocTable(e.target.value);

  document.getElementById("run-analysis-btn").onclick = handleAnalysis;

  document.getElementById("qa-btn").onclick = handleAsk;
  document.getElementById("qa-input").onkeydown = e => {
    if (e.key === "Enter") handleAsk();
  };
}

// ─── upload ────────────────────────────────────────────────────────────────────
async function handleUpload() {
  const input = document.getElementById("doc-input");
  const file  = input.files[0];
  if (!file) return;

  const btn      = document.getElementById("upload-btn");
  const progress = document.getElementById("upload-progress");
  btn.disabled = true;
  progress.textContent = "Uploading and processing…";
  setAlert("upload-alert", "info", "Uploading PDF, extracting text, chunking and embedding. This may take a moment…");

  try {
    const result = await ESGApi.uploadDocument(file);
    const doc = {
      document_id:    result.document_id,
      filename:       result.filename,
      chunks_created: result.chunks_created,
      uploaded:       new Date().toLocaleString(),
      esgStatus:      "Not analyzed"
    };
    uploadedDocs.unshift(doc);
    renderDocTable();
    setAlert("upload-alert", "success",
      `"${result.filename}" uploaded. ${result.chunks_created} chunks created and embedded.`);
    progress.textContent = "";
    // clear input
    input.value = "";
    document.getElementById("doc-name").textContent = "";
    btn.disabled = true;
    toast("Document uploaded and processed");
  } catch (e) {
    setAlert("upload-alert", "error", e.message);
    progress.textContent = "";
    btn.disabled = false;
  }
}

// ─── ESG analysis ──────────────────────────────────────────────────────────────
async function handleAnalysis() {
  if (!activeDocId) { toast("Select a document first"); return; }

  const btn     = document.getElementById("run-analysis-btn");
  const results = document.getElementById("analysis-results");
  btn.disabled  = true;
  setAlert("analysis-alert", "info", "Running Gemini ESG analysis across all document chunks…");
  loading(results, "Analyzing ESG commitments…");

  try {
    const data = await ESGApi.analyzeESG(activeDocId);
    setAlert("analysis-alert", "success",
      `ESG analysis complete. ${data.chunks_analyzed} chunks analyzed, ${data.chunks_updated} updated.`);
    // mark doc as analyzed
    const doc = uploadedDocs.find(d => d.document_id === activeDocId);
    if (doc) {
      doc.esgStatus = "Analyzed";
      const statusEl = document.getElementById(`esg-status-${activeDocId}`);
      if (statusEl) statusEl.innerHTML = badge("Analyzed");
    }
    results.innerHTML = `
      <div class="alert alert-success" style="margin-top:10px">
        <b>${data.chunks_analyzed}</b> chunks analyzed by Gemini in one batch request.
        ESG commitments, targets, baselines and risks have been extracted and stored.
        Use the Q&amp;A panel below to query the document.
      </div>`;
    toast("ESG analysis complete");
  } catch (e) {
    setAlert("analysis-alert", "error", e.message);
    results.innerHTML = "";
  } finally {
    btn.disabled = false;
  }
}

// ─── Q&A ──────────────────────────────────────────────────────────────────────
async function handleAsk() {
  const input = document.getElementById("qa-input");
  const query = input.value.trim();
  if (!query) return;

  const btn     = document.getElementById("qa-btn");
  const results = document.getElementById("qa-results");
  btn.disabled  = true;
  setAlert("qa-alert", "info", "Searching document and generating answer…");
  loading(results, "Retrieving context and asking Gemini…");

  try {
    const data = await ESGApi.askDocument(query);
    setAlert("qa-alert", "");
    results.innerHTML = renderQAResult(data);
    toast("Answer generated");
  } catch (e) {
    setAlert("qa-alert", "error", e.message);
    results.innerHTML = "";
  } finally {
    btn.disabled = false;
  }
}

// ─── render Q&A result ────────────────────────────────────────────────────────
function renderQAResult(data) {
  const sources = data.sources || [];
  const sourcesHtml = sources.map((s, i) => {
    const commitments = s.esg_analysis?.commitments || [];
    const commitmentHtml = commitments.length
      ? commitments.map(c => renderCommitmentCard(c)).join("")
      : `<div class="small muted" style="padding:8px 0">No ESG commitments extracted from this chunk yet. Run ESG Analysis first.</div>`;

    return `
      <div class="change-card" style="margin-top:10px">
        <div class="change-head">
          <div>
            <b>Source ${i + 1}</b>
            <span class="small muted"> • ${escapeHtml(s.filename)} • Page ${escapeHtml(String(s.page))}</span>
          </div>
          <span class="small muted">Similarity distance: ${Number(s.distance).toFixed(4)}</span>
        </div>
        <div style="padding:12px 15px">
          <div class="evidence">
            <div class="confidence">RETRIEVED CHUNK</div>
            <div class="quote" style="margin-top:6px">${escapeHtml(s.content)}</div>
          </div>
          ${commitments.length ? `<div style="margin-top:12px"><div class="small" style="font-weight:750;margin-bottom:8px">ESG COMMITMENTS IN THIS CHUNK</div>${commitmentHtml}</div>` : commitmentHtml}
        </div>
      </div>`;
  }).join("");

  return `
    <div class="evidence" style="margin-bottom:14px">
      <div class="confidence">QUESTION</div>
      <div class="quote" style="margin-top:5px;font-weight:750">${escapeHtml(data.question)}</div>
    </div>
    <div class="card" style="padding:15px;margin-bottom:14px;background:#f0faf4;border-color:#cfe7d9">
      <div class="eyebrow" style="color:#287954;margin-bottom:7px">GEMINI ANSWER</div>
      <div style="font-size:13px;line-height:1.7;white-space:pre-wrap">${escapeHtml(data.answer)}</div>
    </div>
    <div>
      <div class="small" style="font-weight:750;margin-bottom:4px">RETRIEVED SOURCES (${sources.length})</div>
      ${sourcesHtml}
    </div>`;
}

// ─── render one ESG commitment card ──────────────────────────────────────────
function renderCommitmentCard(c) {
  const measurableBadge = c.measurable
    ? `<span class="badge badge-low">Measurable</span>`
    : `<span class="badge badge-medium">Not measurable</span>`;
  const catCls = (c.category || "").toLowerCase().includes("envir") ? "badge-low"
    : (c.category || "").toLowerCase().includes("soc") ? "badge-medium"
    : "badge-neutral";

  return `
    <div style="border:1px solid #e3e9e6;border-radius:9px;padding:11px 13px;margin-bottom:9px">
      <div class="toolbar" style="margin-bottom:7px">
        <span class="badge ${catCls}">${escapeHtml(c.category || "—")}</span>
        <span class="badge badge-neutral">${escapeHtml(c.topic || "—")}</span>
        ${measurableBadge}
      </div>
      <div class="small" style="font-weight:750;margin-bottom:5px">${escapeHtml(c.commitment || "—")}</div>
      <div class="grid-2" style="gap:8px;margin-top:7px">
        ${c.target   ? `<div class="metric" style="padding:9px"><div class="label">Target</div><div style="font-size:13px;font-weight:800;margin-top:3px">${escapeHtml(c.target)}</div></div>` : ""}
        ${c.baseline ? `<div class="metric" style="padding:9px"><div class="label">Baseline</div><div style="font-size:13px;font-weight:800;margin-top:3px">${escapeHtml(c.baseline)}</div></div>` : ""}
        ${c.deadline ? `<div class="metric" style="padding:9px"><div class="label">Deadline</div><div style="font-size:13px;font-weight:800;margin-top:3px">${escapeHtml(c.deadline)}</div></div>` : ""}
      </div>
      ${c.risk ? `<div class="alert alert-error" style="margin-top:9px;font-size:11px"><b>Risk:</b> ${escapeHtml(c.risk)}</div>` : ""}
    </div>`;
}

// ─── alert helper ─────────────────────────────────────────────────────────────
function setAlert(id, type, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = msg
    ? `<div class="alert alert-${type}">${escapeHtml(msg)}</div>`
    : "";
}

// ─── init ─────────────────────────────────────────────────────────────────────
render();

})(); // end IIFE
