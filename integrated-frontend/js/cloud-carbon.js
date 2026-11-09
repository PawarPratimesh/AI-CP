/**
 * Cloud & Carbon Module — Member 4
 *
 * Infrastructure Sustainability + Cloud/Carbon Intelligence + ML
 * Phase 3: ML Anomaly Detection (Isolation Forest) + Energy & Carbon Footprint Modeling
 *
 * 5-Section Architecture:
 *  1. Data Upload (Real CSV/JSON upload to FastAPI backend + mapping confirmation)
 *  2. Infrastructure Overview (6 summary KPI cards + empirical modeling disclaimer)
 *  3. Resource Analytics (Dynamic metric-aware charts based on active/uploaded data)
 *  4. Infrastructure Findings (ML Isolation Forest Anomalies + Resource Inventory with Energy/Carbon)
 *  5. Optimization Recommendations (Compact, readable recommendations table)
 */

(function () {
  "use strict";

  /* ──────────────────────────────────────────────────────────────────────────
     1. DATA STRUCTURES & BENCHMARK BASELINES
     ────────────────────────────────────────────────────────────────────────── */

  const DEMO_DATA = {
    overview: {
      cpuUtil: { label: "Fleet CPU Utilization", value: "64.2%", note: "Fleet average across active instances" },
      memUtil: { label: "Avg Memory Allocation", value: "58.7%", note: "Within target capacity window" },
      energyKWh: { label: "Estimated Energy", value: "1,284.00 kWh", note: "SPECpower linear model (PUE 1.15)" },
      carbonKg: { label: "Estimated Carbon", value: "487.90 kg CO₂e", note: "Scope 2 location-based proxy" },
      anomalies: { label: "Detected Anomalies", value: "4", note: "Flagged by Isolation Forest" },
      underutilized: { label: "Underutilized Resources", value: "3", note: "Instances with average CPU < 15%" }
    },

    defaultTimeSeries: {
      "24h": {
        labels: ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"],
        cpu: [42, 38, 55, 84, 76, 68, 51],
        memory: [48, 49, 53, 71, 65, 62, 55],
        network_in: [120, 95, 210, 480, 410, 320, 180],
        network_out: [85, 70, 160, 390, 320, 240, 140],
        network: [120, 95, 210, 480, 410, 320, 180],
        storage: [64.1, 64.1, 64.2, 64.4, 64.7, 64.9, 65.0]
      },
      "7d": {
        labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        cpu: [58, 62, 71, 82, 68, 44, 41],
        memory: [54, 57, 63, 69, 64, 50, 48],
        network_in: [280, 310, 440, 520, 390, 190, 160],
        network_out: [190, 220, 320, 410, 280, 140, 120],
        network: [280, 310, 440, 520, 390, 190, 160],
        storage: [62.8, 63.2, 63.6, 64.1, 64.5, 64.8, 65.0]
      },
      "30d": {
        labels: ["Week 1", "Week 2", "Week 3", "Week 4"],
        cpu: [52, 59, 68, 64],
        memory: [51, 56, 62, 59],
        network_in: [240, 320, 410, 360],
        network_out: [170, 230, 310, 260],
        network: [240, 320, 410, 360],
        storage: [59.4, 61.2, 63.1, 65.0]
      }
    },

    defaultAnomalies: [
      {
        record_index: 4,
        resource_id: "prod-api-cluster-01",
        timestamp: "2026-11-08T12:00:00Z",
        status: "Anomaly",
        is_anomaly: true,
        anomaly_score: 0.884,
        contributing_metrics: ["cpu_utilization_pct: 94.8% (baseline median: 45.0%, deviation: +49.8)"],
        raw_metrics: { cpu_utilization_pct: 94.8 }
      },
      {
        record_index: 8,
        resource_id: "analytics-worker-c4",
        timestamp: "2026-11-08T09:15:00Z",
        status: "Anomaly",
        is_anomaly: true,
        anomaly_score: 0.812,
        contributing_metrics: ["cpu_utilization_pct: 3.8% (baseline median: 45.0%, deviation: -41.2)"],
        raw_metrics: { cpu_utilization_pct: 3.8 }
      },
      {
        record_index: 12,
        resource_id: "data-pipeline-app-eu",
        timestamp: "2026-11-07T22:40:00Z",
        status: "Anomaly",
        is_anomaly: true,
        anomaly_score: 0.745,
        contributing_metrics: ["memory_utilization_pct: 89.4% (baseline median: 55.0%, deviation: +34.4)"],
        raw_metrics: { memory_utilization_pct: 89.4 }
      },
      {
        record_index: 15,
        resource_id: "backup-log-storage",
        timestamp: "2026-11-06T14:10:00Z",
        status: "Anomaly",
        is_anomaly: true,
        anomaly_score: 0.710,
        contributing_metrics: ["network_out: 480000000.0 (baseline median: 95000000.0, deviation: +385000000.0)"],
        raw_metrics: { network_out: 480000000.0 }
      }
    ],

    defaultResources: [
      { resource_id: "prod-api-cluster-01", provider: "AWS", region: "us-east-1", observation_count: 7, estimated_energy_kwh: 312.4, grid_intensity_factor_kg_per_kwh: 0.379, estimated_carbon_kg: 118.4, carbon_status: "ESTIMATED" },
      { resource_id: "analytics-worker-c4", provider: "AWS", region: "us-east-1", observation_count: 7, estimated_energy_kwh: 84.2, grid_intensity_factor_kg_per_kwh: 0.379, estimated_carbon_kg: 31.9, carbon_status: "ESTIMATED" },
      { resource_id: "customer-db-primary", provider: "AWS", region: "eu-west-1", observation_count: 7, estimated_energy_kwh: 262.1, grid_intensity_factor_kg_per_kwh: 0.285, estimated_carbon_kg: 74.7, carbon_status: "ESTIMATED" },
      { resource_id: "data-pipeline-app-eu", provider: "Azure", region: "westeurope", observation_count: 7, estimated_energy_kwh: 137.2, grid_intensity_factor_kg_per_kwh: 0.320, estimated_carbon_kg: 43.9, carbon_status: "ESTIMATED" },
      { resource_id: "ml-inference-gateway", provider: "AWS", region: "us-west-2", observation_count: 7, estimated_energy_kwh: 488.1, grid_intensity_factor_kg_per_kwh: 0.198, estimated_carbon_kg: 96.6, carbon_status: "ESTIMATED" }
    ],

    recommendations: [
      {
        title: "Mitigate Peak Compute Saturation",
        resource: "prod-api-cluster-01",
        issue: "Peak CPU utilization sustained over 90% during core business hours.",
        action: "Deploy horizontal pod autoscaling or upgrade to a compute-optimized instance specification.",
        priority: "High"
      },
      {
        title: "Review Underutilized Worker Node",
        resource: "analytics-worker-c4",
        issue: "The instance consistently operates at low CPU utilization averaging under 5%.",
        action: "Review workload requirements and consider rightsizing or replacing with a scheduled task.",
        priority: "High"
      },
      {
        title: "Tune Application Memory Allocation",
        resource: "data-pipeline-app-eu",
        issue: "Memory allocation rises continuously without regular garbage collection recovery.",
        action: "Profile application heap allocations and configure cache retention limits.",
        priority: "Medium"
      },
      {
        title: "Evaluate Regional Decarbonization",
        resource: "Fleet-wide",
        issue: "Workloads operate in regional grid zones with elevated carbon intensity.",
        action: "Evaluate lower-carbon deployment regions while verifying network latency and data residency requirements.",
        priority: "Medium"
      },
      {
        title: "Configure Storage Lifecycle Archival",
        resource: "backup-log-storage",
        issue: "Uncompressed cold log files remain on standard primary storage volumes.",
        action: "Configure automated lifecycle rules to transition objects older than 30 days to archive tiers.",
        priority: "Low"
      }
    ]
  };

  /* ──────────────────────────────────────────────────────────────────────────
     2. APPLICATION STATE
     ────────────────────────────────────────────────────────────────────────── */

  const State = {
    cloudProvider: "all",
    timeRange: "24h",
    anomalyFilter: "anomalies", // "anomalies", "high", "all"
    resourceSearch: "",
    selectedFile: null,
    uploadResult: null,          // Live UploadInspectionResponse from backend
    analysisResult: null,        // Live UnifiedAnalysisResponse from Phase 3 backend
    activePreviewRecords: [],    // Preprocessed CanonicalRecord items
    availableMetrics: ["cpu", "memory", "network", "storage"], // Dynamic metric list
    timeSeriesData: DEMO_DATA.defaultTimeSeries,
    recommendationsResult: null, // Live CloudCarbonRecommendationsResponse from Phase 4
    recommendationsLoading: false
  };

  /* ──────────────────────────────────────────────────────────────────────────
     3. RENDER SHELL (5 EXACT SECTIONS)
     ────────────────────────────────────────────────────────────────────────── */

  const app = document.getElementById("page-app");
  if (!app) return;

  function renderLayout() {
    // PART 1: Clean topbar for standalone Cloud & Carbon module
    const topbar = document.getElementById("topbar");
    if (topbar) {
      topbar.innerHTML = `
        <header class="topbar">
          <button class="top-icon mobile-menu" id="mobile-menu">☰</button>
          <div class="top-title" style="font-weight:700">Cloud &amp; Carbon</div>
        </header>
      `;
      const side = document.getElementById("sidebar");
      const overlay = document.getElementById("sidebar-overlay");
      const menu = document.getElementById("mobile-menu");
      if (menu && side && overlay) {
        menu.onclick = () => { side.classList.toggle("open"); overlay.classList.toggle("open"); };
      }
    }

    app.innerHTML = `
      <!-- Section 1: Data Upload -->
      <section class="card" id="upload-section" style="margin-bottom:24px;border:1px solid #e1e7e4;border-radius:8px;padding:20px 24px">
        <div class="section-head" style="margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f0f4f2">
          <div>
            <h2 style="font-size:16px;font-weight:700;color:#1a2e26;margin:0 0 4px 0">Data Upload</h2>
            <p style="font-size:12px;color:#607268;margin:0">Upload infrastructure metrics to analyze resource utilization, detect anomalies and estimate cloud carbon emissions.</p>
          </div>
        </div>

        <div class="file-drop" id="metric-drop-zone" style="padding:22px 18px;border:2px dashed #c8d7d0;border-radius:8px;text-align:center;background:#fbfdfc">
          <input type="file" id="metric-file-input" accept=".csv,.json">
          <div style="font-weight:700;font-size:13px;color:#244033">Drag and drop your metric file here (.csv or .json), or <button type="button" class="btn btn-secondary" id="btn-browse-file" style="padding:4px 12px;font-size:11px;margin-left:6px">Browse Files</button></div>
          <div class="small muted" style="margin-top:6px;font-size:11.5px">Accepted: AWS CloudWatch, Azure Monitor, or custom server logs (Max 25 MB)</div>
          <div id="file-preview-area" style="display:none;margin-top:14px"></div>
        </div>

        <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;margin-top:16px">
          <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px">
            <span class="small muted" style="font-size:11.5px;font-weight:600;color:#506259">Sample datasets:</span>
            <button type="button" class="sample-chip" data-sample="aws">AWS CloudWatch</button>
            <button type="button" class="sample-chip" data-sample="azure">Azure Monitor</button>
            <button type="button" class="sample-chip" data-sample="custom">Custom BareMetal</button>
            <button type="button" class="sample-chip" data-sample="manual">Manual Test (t3.medium)</button>
          </div>
          <button class="btn btn-primary" id="btn-upload-analyze" disabled style="padding:8px 18px;font-size:12px;font-weight:600">
            Upload &amp; Analyze
          </button>
        </div>
        <div id="upload-alert" style="margin-top:12px"></div>
        <div id="mapping-confirmation-card" style="display:none;margin-top:14px"></div>
      </section>

      <!-- Section 2: Infrastructure Overview -->
      <section class="card" id="overview-section" style="margin-bottom:24px;border:1px solid #e1e7e4;border-radius:8px;padding:20px 24px">
        <div class="section-head" style="margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f0f4f2;display:flex;justify-content:space-between;align-items:center">
          <div>
            <h2 style="font-size:16px;font-weight:700;color:#1a2e26;margin:0 0 4px 0">Infrastructure Overview</h2>
            <p style="font-size:12px;color:#607268;margin:0">Summary of resource utilization, modeled energy, carbon emissions and efficiency opportunities.</p>
          </div>
          <span class="badge badge-neutral" id="overview-badge" style="font-size:11px">Demo Benchmark</span>
        </div>
        <div class="kpi-strip-6" id="kpi-container" style="margin-bottom:16px"></div>
        <div class="alert alert-info" style="margin-bottom:0;padding:10px 14px;font-size:11.5px;line-height:1.45;background:#f3f7f5;border:1px solid #d4e2db;color:#244033">
          <b>Note:</b> Energy consumption and carbon emissions are estimates based on resource usage assumptions and emission factors, not direct meter readings.
        </div>
      </section>

      <!-- Section 3: Resource Analytics (Dynamic Metric-Aware Charts) -->
      <section class="card" id="analytics-section" style="margin-bottom:24px;border:1px solid #e1e7e4;border-radius:8px;padding:20px 24px">
        <div class="section-head" style="margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f0f4f2;display:flex;justify-content:space-between;align-items:center">
          <div>
            <h2 style="font-size:16px;font-weight:700;color:#1a2e26;margin:0 0 4px 0">Resource Analytics</h2>
            <p id="analytics-subtitle" style="font-size:12px;color:#607268;margin:0">Displays charts dynamically based on metrics available in the active dataset.</p>
          </div>
          <div class="tabs" style="margin-bottom:0;border-bottom:0">
            <button class="tab active" data-range="24h" style="font-size:11px;padding:4px 10px">Chronological Observations</button>
          </div>
        </div>
        <div class="chart-grid" id="chart-grid"></div>
        <div id="metrics-availability-note" class="small muted" style="margin-top:12px;font-size:11.5px"></div>
      </section>

      <!-- Section 4: Infrastructure Findings (Anomalies + Normalized Resource Inventory) -->
      <section class="card" id="findings-section" style="margin-bottom:24px;border:1px solid #e1e7e4;border-radius:8px;padding:20px 24px">
        <div class="section-head" style="margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f0f4f2">
          <div>
            <h2 style="font-size:16px;font-weight:700;color:#1a2e26;margin:0 0 4px 0">Infrastructure Findings</h2>
            <p style="font-size:12px;color:#607268;margin:0">Detected operational anomalies and cloud resource inventory with carbon emissions.</p>
          </div>
        </div>

        <!-- Part A: ML Anomaly Detection -->
        <div style="margin-bottom:24px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <h3 style="font-size:12px;font-weight:750;text-transform:uppercase;letter-spacing:0.04em;color:#495852;margin:0" id="anomalies-heading">
              Detected Anomalies (Isolation Forest)
            </h3>
            <div class="toolbar" style="gap:4px" id="anomaly-filter-bar">
              <button class="btn btn-secondary" data-sev="anomalies" style="padding:3px 8px;font-size:10px">Anomalies Only</button>
              <button class="btn btn-ghost" data-sev="high" style="padding:3px 8px;font-size:10px">High Score (&ge;0.7)</button>
              <button class="btn btn-ghost" data-sev="all" style="padding:3px 8px;font-size:10px">All Observations</button>
            </div>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th style="width:7%">#</th>
                  <th style="width:18%">Resource ID</th>
                  <th style="width:18%">Timestamp (UTC)</th>
                  <th style="width:12%">Status</th>
                  <th style="width:13%">Anomaly Score</th>
                  <th style="width:32%">Contributing Metrics (Heuristic Deviation)</th>
                </tr>
              </thead>
              <tbody id="anomaly-table-body"></tbody>
            </table>
          </div>
          <div id="anomaly-attribution-note" class="small muted" style="margin-top:8px;font-size:10.5px"></div>
        </div>

        <div class="divider" style="margin:20px 0;border-top:1px solid #edf2ef"></div>

        <!-- Part B: Cloud Resource Inventory & Carbon Footprint -->
        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <h3 style="font-size:12px;font-weight:750;text-transform:uppercase;letter-spacing:0.04em;color:#495852;margin:0" id="inventory-heading">
              Cloud Resource Inventory &amp; Emissions
            </h3>
            <div class="search-box">
              <span class="search-icon">⌕</span>
              <input id="resource-search" placeholder="Search resources…" style="width:200px;padding:6px 10px 6px 28px;font-size:11px">
            </div>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Resource ID</th>
                  <th>Provider &amp; Region</th>
                  <th>Observations</th>
                  <th>Estimated Energy</th>
                  <th>Grid Carbon Intensity</th>
                  <th>Estimated CO₂e</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody id="inventory-table-body"></tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- Section 5: Optimization Recommendations & AI Insights -->
      <section class="card" id="recommendations-section" style="margin-bottom:24px;border:1px solid #e1e7e4;border-radius:8px;padding:20px 24px">
        <div class="section-head" style="margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f0f4f2;display:flex;justify-content:space-between;align-items:center">
          <div>
            <h2 id="recommendations-heading" style="font-size:16px;font-weight:700;color:#1a2e26;margin:0 0 4px 0">Optimization Recommendations &amp; AI Insights</h2>
            <p id="recommendations-subtitle" style="font-size:12px;color:#607268;margin:0">Actionable efficiency and decarbonization opportunities identified from infrastructure data.</p>
          </div>
          <div id="recommendations-badges" style="display:flex;gap:6px;align-items:center">
            <span class="badge badge-success" id="recommendations-count-badge" style="font-size:10px">5 Recommendations</span>
          </div>
        </div>
        <div id="recommendations-container"></div>
      </section>
    `;

    bindEvents();
    renderOverview();
    renderAnalyticsCharts();
    renderAnomalies(State.anomalyFilter);
    renderInventory();
    renderRecommendations();
  }

  /* ──────────────────────────────────────────────────────────────────────────
     4. COMPONENT RENDERERS
     ────────────────────────────────────────────────────────────────────────── */

  // Helper: Format carbon emission values with exactly 2 decimal places
  function formatCarbonKg(val) {
    if (val === null || val === undefined || isNaN(val)) {
      return "Factor Unavailable";
    }
    const num = Number(val);
    return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " kg CO₂e";
  }

  // Section 2: Render 6 summary KPI cards with real calculations
  function renderOverview() {
    const container = document.getElementById("kpi-container");
    if (!container) return;

    let cards = [];

    if (State.analysisResult) {
      const an = State.analysisResult.anomaly_detection;
      const em = State.analysisResult.emissions_estimation;
      const recs = State.activePreviewRecords || [];

      // Average CPU
      const cpus = recs.map(r => r.cpu_utilization_pct).filter(v => v != null);
      const avgCpu = cpus.length ? (cpus.reduce((a, b) => a + b, 0) / cpus.length).toFixed(1) + "%" : "—";

      // Average Memory
      const mems = recs.map(r => r.memory_utilization_pct).filter(v => v != null);
      const avgMem = mems.length ? (mems.reduce((a, b) => a + b, 0) / mems.length).toFixed(1) + "%" : "—";

      // Energy (2 decimal precision: e.g. 0.38 kWh)
      const energyStr = em.total_energy_kwh.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " kWh";

      // Carbon (2 decimal precision)
      let carbonStr = "Factor Unavailable";
      let carbonNote = "Missing regional grid factor";
      if (em.total_carbon_kgco2e != null) {
        carbonStr = formatCarbonKg(em.total_carbon_kgco2e);
        carbonNote = em.status === "PARTIAL_CALCULATION" ? "Partial regional coverage" : "Modeled Scope 2 location-based";
      }

      // Underutilized Resources (<15% average CPU)
      const underutilizedCount = (em.resources_breakdown || []).filter(r => {
        const rRecs = recs.filter(x => x.resource_id === r.resource_id && x.cpu_utilization_pct != null);
        if (!rRecs.length) return false;
        const rAvg = rRecs.reduce((a, b) => a + b.cpu_utilization_pct, 0) / rRecs.length;
        return rAvg < 15.0;
      }).length;

      cards = [
        { label: "Fleet CPU Utilization", val: avgCpu, note: `Fleet average (${cpus.length} observations)` },
        { label: "Avg Memory Allocation", val: avgMem, note: mems.length ? `Average across ${mems.length} observations` : "Metric omitted from dataset" },
        { label: "Estimated Energy", val: energyStr, note: `SPECpower linear model (PUE ${em.assumptions.pue})` },
        { label: "Estimated Carbon", val: carbonStr, note: carbonNote },
        { label: "Detected Anomalies", val: `${an.anomalies_detected}`, note: `Isolation Forest (${an.anomaly_percentage}% flagged)` },
        { label: "Underutilized Resources", val: `${underutilizedCount}`, note: "Instances with average CPU < 15%" }
      ];
    } else {
      const ov = DEMO_DATA.overview;
      cards = [
        { label: ov.cpuUtil.label, val: ov.cpuUtil.value, note: ov.cpuUtil.note },
        { label: ov.memUtil.label, val: ov.memUtil.value, note: ov.memUtil.note },
        { label: ov.energyKWh.label, val: ov.energyKWh.value, note: ov.energyKWh.note },
        { label: ov.carbonKg.label, val: ov.carbonKg.value, note: ov.carbonKg.note },
        { label: ov.anomalies.label, val: ov.anomalies.value, note: ov.anomalies.note },
        { label: ov.underutilized.label, val: ov.underutilized.value, note: ov.underutilized.note }
      ];
    }

    container.innerHTML = cards.map(c => `
      <div class="kpi">
        <div class="kpi-label">${escapeHtml(c.label)}</div>
        <div class="kpi-value">${escapeHtml(c.val)}</div>
        <div class="kpi-note">${escapeHtml(c.note)}</div>
      </div>
    `).join("");
  }

  // Section 3: Dynamic Metric-Aware Resource Analytics from real uploaded records
  function renderAnalyticsCharts() {
    const container = document.getElementById("chart-grid");
    const noteEl = document.getElementById("metrics-availability-note");
    if (!container) return;

    const availableMetrics = State.availableMetrics || [];
    const timeData = (State.timeSeriesData && (State.timeSeriesData[State.timeRange] || State.timeSeriesData["24h"])) || null;

    if (!timeData || !timeData.labels || timeData.labels.length < 2) {
      container.innerHTML = `
        <div class="full" style="grid-column:1/-1">
          <div class="chart-unavailable">
            <div style="font-size:20px;margin-bottom:6px">⏳</div>
            <b>Insufficient Timestamped Observations</b>
            <span class="small muted" style="margin-top:4px">At least 2 chronological observations are required to render historical trend analytics.</span>
          </div>
        </div>
      `;
      if (noteEl) noteEl.textContent = "Data points: 0. Historical trend unavailable.";
      return;
    }

    const labels = timeData.labels;
    const cardsHtml = [];

    // Chart 1: CPU Utilization
    if (availableMetrics.includes("cpu") && timeData.cpu) {
      cardsHtml.push(`
        <div class="metric" style="padding:14px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <b>CPU Utilization (%)</b>
            <span class="badge badge-low">Available</span>
          </div>
          <div class="line-chart" style="height:170px">
            ${generateSvgChart(timeData.cpu, labels, "%", 0, 100, 80, "#2b8c69", "#d86666")}
          </div>
          <div class="legend" style="margin-top:4px">
            <span><i class="green-dot"></i>Utilization</span>
            <span><i class="red-dot"></i>Threshold (&gt;80%)</span>
          </div>
        </div>
      `);
    }

    // Chart 2: Memory Utilization
    if (availableMetrics.includes("memory") && timeData.memory) {
      cardsHtml.push(`
        <div class="metric" style="padding:14px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <b>Memory Allocation (%)</b>
            <span class="badge badge-processing">Available</span>
          </div>
          <div class="line-chart" style="height:170px">
            ${generateSvgChart(timeData.memory, labels, "%", 0, 100, null, "#4f7fa3", null)}
          </div>
          <div class="legend" style="margin-top:4px">
            <span><i class="blue-dot"></i>RAM footprint</span>
          </div>
        </div>
      `);
    }

    // Chart 3: Network Usage (Dual Series: Inbound & Outbound in Source Units)
    const hasNetIn = timeData.network_in && timeData.network_in.some(v => v !== null);
    const hasNetOut = timeData.network_out && timeData.network_out.some(v => v !== null);
    const hasNetSingle = timeData.network && timeData.network.some(v => v !== null);

    if (availableMetrics.includes("network") && (hasNetIn || hasNetOut || hasNetSingle)) {
      const netSeries = [];
      if (hasNetIn) {
        netSeries.push({ name: "Inbound", values: timeData.network_in, color: "#2b8c69" });
      }
      if (hasNetOut) {
        netSeries.push({ name: "Outbound", values: timeData.network_out, color: "#4f7fa3" });
      }
      if (!netSeries.length && hasNetSingle) {
        netSeries.push({ name: "Traffic", values: timeData.network, color: "#2b8c69" });
      }

      cardsHtml.push(`
        <div class="metric" style="padding:14px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <b>Network Traffic (Source Units)</b>
            <span class="badge badge-neutral">Available</span>
          </div>
          <div class="line-chart" style="height:170px">
            ${generateSvgMultiSeriesChart(netSeries, labels, "")}
          </div>
          <div class="legend" style="margin-top:4px;gap:12px">
            ${hasNetIn ? '<span><i class="green-dot"></i>Inbound (network_in)</span>' : ''}
            ${hasNetOut ? '<span><i class="blue-dot" style="background:#4f7fa3"></i>Outbound (network_out)</span>' : ''}
            ${!hasNetIn && !hasNetOut ? '<span><i class="green-dot"></i>Data transfer</span>' : ''}
          </div>
        </div>
      `);
    }

    // Chart 4: Storage Utilization
    if (availableMetrics.includes("storage") && timeData.storage) {
      const minStor = Math.min(...timeData.storage) * 0.9;
      const maxStor = Math.max(...timeData.storage) * 1.1;
      cardsHtml.push(`
        <div class="metric" style="padding:14px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <b>Storage Growth</b>
            <span class="badge badge-neutral">Available</span>
          </div>
          <div class="line-chart" style="height:170px">
            ${generateSvgChart(timeData.storage, labels, " GB", minStor, maxStor, null, "#c68a28", null)}
          </div>
          <div class="legend" style="margin-top:4px">
            <span><i class="amber-dot"></i>Allocated volume</span>
          </div>
        </div>
      `);
    }

    container.innerHTML = cardsHtml.length ? cardsHtml.join("") : `
      <div class="full" style="grid-column:1/-1">
        <div class="chart-unavailable">
          <b>No supported chart metrics found in dataset</b>
          <span class="small muted">Uploaded dataset must contain CPU, memory, network or storage observations.</span>
        </div>
      </div>
    `;

    // Omitted metric notice
    const allMetrics = ["cpu", "memory", "network", "storage"];
    const omitted = allMetrics.filter(m => !availableMetrics.includes(m));
    if (noteEl) {
      if (omitted.length > 0) {
        const formattedOmitted = omitted.map(m => m.charAt(0).toUpperCase() + m.slice(1)).join(", ");
        const formattedPresent = availableMetrics.map(m => m.charAt(0).toUpperCase() + m.slice(1)).join(", ");
        noteEl.innerHTML = `Active metrics in dataset: <b>${formattedPresent || "None"}</b> &bull; Omitted (not in dataset): <span style="color:#8a9691">${formattedOmitted}</span>`;
      } else {
        noteEl.innerHTML = `Active metrics: <b>CPU, Memory, Network, Storage</b> (All standard dimensions present)`;
      }
    }
  }

  // Pure SVG Line Chart Generator
  function generateSvgChart(values, labels, unit, minVal, maxVal, threshold, strokeColor, anomalyColor) {
    const W = 540;
    const H = 155;
    const p = { l: 28, r: 12, t: 12, b: 20 };

    const min = minVal !== null ? minVal : Math.min(...values) * 0.9;
    const max = maxVal !== null ? maxVal : Math.max(...values) * 1.1;
    const range = max - min || 1;

    const x = i => p.l + (i * (W - p.l - p.r)) / Math.max(1, values.length - 1);
    const y = v => p.t + ((max - v) * (H - p.t - p.b)) / range;

    let grid = "";
    for (let i = 0; i < 3; i++) {
      const lineY = p.t + (i * (H - p.t - p.b)) / 2;
      const valLabel = Math.round(max - (i * range) / 2);
      grid += `<line x1="${p.l}" y1="${lineY}" x2="${W - p.r}" y2="${lineY}" stroke="#eef2f0" stroke-width="1"/>`;
      grid += `<text x="${p.l - 4}" y="${lineY + 3}" text-anchor="end" font-size="8" fill="#919d97">${valLabel}</text>`;
    }

    let thresholdLine = "";
    if (threshold !== null && threshold >= min && threshold <= max) {
      const ty = y(threshold);
      thresholdLine = `<line x1="${p.l}" y1="${ty}" x2="${W - p.r}" y2="${ty}" stroke="#e27373" stroke-width="1" stroke-dasharray="3,3"/>`;
    }

    const points = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    let dots = "";
    values.forEach((v, i) => {
      const isAnomaly = threshold !== null && v >= threshold;
      const dotColor = isAnomaly && anomalyColor ? anomalyColor : strokeColor;
      const radius = isAnomaly ? 4.5 : 3;
      dots += `<circle cx="${x(i)}" cy="${y(v)}" r="${radius}" fill="#fff" stroke="${dotColor}" stroke-width="2"><title>${labels[i]}: ${v}${unit}</title></circle>`;
    });

    const xLabels = labels.map((lbl, i) => `
      <text x="${x(i)}" y="${H - 4}" text-anchor="middle" font-size="8" fill="#889690">${escapeHtml(lbl)}</text>
    `).join("");

    return `
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <g>${grid}</g>
        ${thresholdLine}
        <polyline points="${points}" fill="none" stroke="${strokeColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        ${dots}
        <g>${xLabels}</g>
      </svg>
    `;
  }

  // Multi-Series SVG Line Chart Generator (Supports dual inbound & outbound series in source units)
  function generateSvgMultiSeriesChart(seriesList, labels, unit, minVal, maxVal) {
    const W = 540;
    const H = 155;
    const p = { l: 38, r: 12, t: 12, b: 20 };

    const allVals = (seriesList || []).flatMap(s => (s.values || []).filter(v => v !== null && !isNaN(v)));
    if (!allVals.length) {
      return `<div class="chart-unavailable"><b>No network observations available</b></div>`;
    }

    const min = minVal !== null && minVal !== undefined ? minVal : Math.min(0, Math.min(...allVals));
    const peak = Math.max(...allVals);
    const max = maxVal !== null && maxVal !== undefined ? maxVal : (peak > 0 ? peak * 1.15 : 10);
    const range = (max - min) || 1;

    const x = i => p.l + (i * (W - p.l - p.r)) / Math.max(1, labels.length - 1);
    const y = v => p.t + ((max - v) * (H - p.t - p.b)) / range;

    let grid = "";
    for (let i = 0; i < 3; i++) {
      const lineY = p.t + (i * (H - p.t - p.b)) / 2;
      const rawVal = max - (i * range) / 2;
      let valLabel = "";
      if (Math.abs(rawVal) >= 1e6) {
        valLabel = (rawVal / 1e6).toFixed(1) + "M";
      } else if (Math.abs(rawVal) >= 1e3) {
        valLabel = (rawVal / 1e3).toFixed(1) + "k";
      } else {
        valLabel = (Math.round(rawVal * 10) / 10).toString();
      }
      grid += `<line x1="${p.l}" y1="${lineY}" x2="${W - p.r}" y2="${lineY}" stroke="#eef2f0" stroke-width="1"/>`;
      grid += `<text x="${p.l - 4}" y="${lineY + 3}" text-anchor="end" font-size="8" fill="#919d97">${valLabel}</text>`;
    }

    let paths = "";
    let dots = "";

    seriesList.forEach(series => {
      const color = series.color || "#2b8c69";
      const name = series.name || "";
      const segments = [];
      let currentSeg = [];

      (series.values || []).forEach((v, i) => {
        if (v !== null && !isNaN(v)) {
          currentSeg.push({ x: x(i), y: y(v), val: v, label: labels[i] });
        } else if (currentSeg.length > 0) {
          segments.push(currentSeg);
          currentSeg = [];
        }
      });
      if (currentSeg.length > 0) segments.push(currentSeg);

      segments.forEach(seg => {
        const pts = seg.map(pt => `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(" ");
        paths += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
        seg.forEach(pt => {
          dots += `<circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="3" fill="#fff" stroke="${color}" stroke-width="2"><title>${name ? name + ': ' : ''}${pt.label} — ${pt.val}${unit}</title></circle>`;
        });
      });
    });

    const xLabels = labels.map((lbl, i) => `
      <text x="${x(i).toFixed(1)}" y="${H - 4}" text-anchor="middle" font-size="8" fill="#889690">${escapeHtml(lbl)}</text>
    `).join("");

    return `
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <g>${grid}</g>
        ${paths}
        ${dots}
        <g>${xLabels}</g>
      </svg>
    `;
  }

  // Build real time-series from uploaded canonical records (Preserves source units and both in/out metrics)
  function buildTimeSeriesFromRecords(records) {
    if (!records || records.length < 2) return null;

    const sorted = [...records].sort((a, b) => (a.timestamp > b.timestamp ? 1 : -1));
    const groups = {};

    sorted.forEach(r => {
      const ts = r.timestamp;
      if (!groups[ts]) {
        groups[ts] = { cpu: [], mem: [], net_in: [], net_out: [], storage: [] };
      }
      if (r.cpu_utilization_pct != null) groups[ts].cpu.push(r.cpu_utilization_pct);
      if (r.memory_utilization_pct != null) groups[ts].mem.push(r.memory_utilization_pct);
      // Preserve source network values without dividing by 1e6
      if (r.network_in != null) groups[ts].net_in.push(r.network_in);
      if (r.network_out != null) groups[ts].net_out.push(r.network_out);
      if (r.storage_used != null) groups[ts].storage.push(r.storage_used);
    });

    const timestamps = Object.keys(groups);
    if (timestamps.length < 2) return null;

    const labels = timestamps.map(ts => {
      const match = ts.match(/T(\d{2}:\d{2})/);
      return match ? match[1] : ts.slice(5, 16);
    });

    const avg = arr => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null);

    const cpuVals = timestamps.map(ts => {
      const v = avg(groups[ts].cpu);
      return v !== null ? Math.round(v * 10) / 10 : null;
    });
    const memVals = timestamps.map(ts => {
      const v = avg(groups[ts].mem);
      return v !== null ? Math.round(v * 10) / 10 : null;
    });
    const netInVals = timestamps.map(ts => {
      const v = avg(groups[ts].net_in);
      return v !== null ? (Math.round(v * 100) / 100) : null;
    });
    const netOutVals = timestamps.map(ts => {
      const v = avg(groups[ts].net_out);
      return v !== null ? (Math.round(v * 100) / 100) : null;
    });
    const storVals = timestamps.map(ts => {
      const v = avg(groups[ts].storage);
      return v !== null ? Math.round(v * 10) / 10 : null;
    });

    const hasNetIn = netInVals.some(v => v !== null);
    const hasNetOut = netOutVals.some(v => v !== null);

    return {
      labels: labels,
      cpu: cpuVals.some(v => v !== null) ? cpuVals : null,
      memory: memVals.some(v => v !== null) ? memVals : null,
      network_in: hasNetIn ? netInVals : null,
      network_out: hasNetOut ? netOutVals : null,
      network: hasNetIn ? netInVals : (hasNetOut ? netOutVals : null),
      storage: storVals.some(v => v !== null) ? storVals : null
    };
  }

  // Section 4 Part A: Anomaly Detection Table (Isolation Forest)
  function renderAnomalies(filter) {
    const tbody = document.getElementById("anomaly-table-body");
    const heading = document.getElementById("anomalies-heading");
    const noteEl = document.getElementById("anomaly-attribution-note");
    if (!tbody) return;

    let items = [];

    if (State.analysisResult && State.analysisResult.anomaly_detection) {
      const an = State.analysisResult.anomaly_detection;
      items = an.anomalies || [];

      if (heading) {
        heading.textContent = `Detected Anomalies (Isolation Forest: ${an.anomalies_detected} flagged, ${an.anomaly_percentage}%)`;
      }

      if (filter === "anomalies") {
        items = items.filter(a => a.is_anomaly);
      } else if (filter === "high") {
        items = items.filter(a => a.anomaly_score >= 0.7);
      } // "all" displays both normal and anomaly

      if (noteEl) {
        noteEl.innerHTML = `<b>Attribution Methodology:</b> ${escapeHtml(an.attribution_note)}`;
      }

      if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state" style="padding:18px">No observations matching "${escapeHtml(filter)}" filter. (Total anomalies: ${an.anomalies_detected})</div></td></tr>`;
        return;
      }

      tbody.innerHTML = items.map(a => `
        <tr>
          <td><span class="small muted">#${a.record_index}</span></td>
          <td><b>${escapeHtml(a.resource_id)}</b></td>
          <td class="small muted">${escapeHtml(a.timestamp)}</td>
          <td>
            <span class="badge ${a.is_anomaly ? 'badge-danger' : 'badge-low'}">
              ${escapeHtml(a.status)}
            </span>
          </td>
          <td>
            <b style="font-family:monospace;color:${a.anomaly_score >= 0.7 ? '#c23934' : a.is_anomaly ? '#c68a28' : '#2b8c69'}">
              ${a.anomaly_score.toFixed(3)}
            </b>
          </td>
          <td style="font-size:11px">
            ${a.contributing_metrics && a.contributing_metrics.length
              ? a.contributing_metrics.map(cm => `<div style="color:#b33d3d;margin-bottom:2px">&bull; ${escapeHtml(cm)}</div>`).join("")
              : `<span class="muted">${a.is_anomaly ? 'Multi-metric interaction' : 'Within normal variance'}</span>`
            }
          </td>
        </tr>
      `).join("");

    } else {
      // Demo baseline fallback
      items = DEMO_DATA.defaultAnomalies;
      if (filter === "high") {
        items = items.filter(a => a.anomaly_score >= 0.75);
      }

      if (noteEl) {
        noteEl.innerHTML = "<b>Attribution Methodology:</b> Benchmark observations evaluated using Isolation Forest and heuristic deviation.";
      }

      tbody.innerHTML = items.map(a => `
        <tr>
          <td><span class="small muted">#${a.record_index}</span></td>
          <td><b>${escapeHtml(a.resource_id)}</b></td>
          <td class="small muted">${escapeHtml(a.timestamp)}</td>
          <td><span class="badge badge-danger">${escapeHtml(a.status)}</span></td>
          <td><b style="font-family:monospace;color:#c23934">${a.anomaly_score.toFixed(3)}</b></td>
          <td style="font-size:11px">
            ${a.contributing_metrics.map(cm => `<div style="color:#b33d3d">&bull; ${escapeHtml(cm)}</div>`).join("")}
          </td>
        </tr>
      `).join("");
    }

    document.querySelectorAll("#anomaly-filter-bar button").forEach(btn => {
      btn.className = (btn.dataset.sev === filter) ? "btn btn-secondary" : "btn btn-ghost";
    });
  }

  // Section 4 Part B: Cloud Resource Inventory & Carbon Footprint
  function renderInventory() {
    const tbody = document.getElementById("inventory-table-body");
    const heading = document.getElementById("inventory-heading");
    if (!tbody) return;

    let list = [];

    if (State.analysisResult && State.analysisResult.emissions_estimation) {
      const em = State.analysisResult.emissions_estimation;
      list = em.resources_breakdown || [];

      if (heading) {
        heading.textContent = `Cloud Resource Inventory & Carbon Footprint (${list.length} instances modeled)`;
      }

      const q = (State.resourceSearch || "").trim().toLowerCase();
      if (q) {
        list = list.filter(r =>
          r.resource_id.toLowerCase().includes(q) ||
          (r.region && r.region.toLowerCase().includes(q)) ||
          r.provider.toLowerCase().includes(q)
        );
      }

      if (!list.length) {
        tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state" style="padding:18px">No resources match "${escapeHtml(q)}".</div></td></tr>`;
        return;
      }

      tbody.innerHTML = list.map(r => `
        <tr>
          <td><b>${escapeHtml(r.resource_id)}</b></td>
          <td>
            <span class="badge badge-neutral">${escapeHtml(r.provider)}</span>
            <span class="small muted">${escapeHtml(r.region || "Unspecified")}</span>
          </td>
          <td>${r.observation_count}</td>
          <td><b>${r.estimated_energy_kwh.toFixed(2)} kWh</b></td>
          <td class="muted">
            ${r.grid_intensity_factor_kg_per_kwh != null
              ? `${r.grid_intensity_factor_kg_per_kwh.toFixed(3)} kg/kWh`
              : '<span class="badge badge-warning" title="Regional grid emission factor not in catalog">Unavailable</span>'
            }
          </td>
          <td>
            ${r.estimated_carbon_kg != null
              ? `<b class="danger-text">${formatCarbonKg(r.estimated_carbon_kg)}</b>`
              : '<span class="small muted" title="Grid intensity factor unavailable for region">Factor Unavailable</span>'
            }
          </td>
          <td>
            <span class="badge ${r.carbon_status === 'ESTIMATED' ? 'badge-low' : 'badge-warning'}">
              ${r.carbon_status === 'ESTIMATED' ? 'Modeled' : 'Missing Factor'}
            </span>
          </td>
        </tr>
      `).join("");

    } else {
      // Demo baseline fallback
      list = DEMO_DATA.defaultResources;
      if (heading) heading.textContent = "Cloud Resource Inventory & Emissions (Demo Baseline)";

      const q = (State.resourceSearch || "").trim().toLowerCase();
      if (q) {
        list = list.filter(r =>
          r.resource_id.toLowerCase().includes(q) ||
          r.provider.toLowerCase().includes(q) ||
          (r.region && r.region.toLowerCase().includes(q))
        );
      }

      tbody.innerHTML = list.map(r => `
        <tr>
          <td><b>${escapeHtml(r.resource_id)}</b></td>
          <td><span class="badge badge-neutral">${escapeHtml(r.provider)}</span> <span class="small muted">${escapeHtml(r.region)}</span></td>
          <td>${r.observation_count}</td>
          <td><b>${r.estimated_energy_kwh.toFixed(1)} kWh</b></td>
          <td class="muted">${r.grid_intensity_factor_kg_per_kwh.toFixed(3)} kg/kWh</td>
          <td>${r.estimated_carbon_kg != null ? `<b class="danger-text">${formatCarbonKg(r.estimated_carbon_kg)}</b>` : '<span class="small muted">Factor Unavailable</span>'}</td>
          <td><span class="badge badge-low">Modeled</span></td>
        </tr>
      `).join("");
    }
  }

  // Helper: Truncate text cleanly to a maximum number of complete sentences and words without breaking decimals
  function limitSentences(text, maxSentences = 2, maxWords = 30) {
    if (!text) return "";
    const str = String(text).replace(/\s+/g, " ").trim();
    // Split only on sentence-ending punctuation preceded by letters, closing quotes/parens, or percent signs,
    // followed by whitespace + capital letter or end of string. This preserves decimals like 3.8% and 0.379 kg CO₂e/kWh.
    const tokens = str.split(/(?<=[a-zA-Z%)\'\"])([.!?])(?=\s+[A-Z]|\s*$)/);
    const sentences = [];
    let current = "";
    for (let i = 0; i < tokens.length; i++) {
      const t = tokens[i];
      if (t === "." || t === "!" || t === "?") {
        current += t;
        sentences.push(current.trim());
        current = "";
      } else {
        current += t;
      }
    }
    if (current.trim()) sentences.push(current.trim());
    const clean = sentences.filter(Boolean);
    let selected = clean.slice(0, maxSentences).join(" ");
    if (!selected) selected = str;

    const words = selected.split(/\s+/);
    if (words.length > maxWords) {
      let trimmed = words.slice(0, maxWords).join(" ").replace(/[,;:-]+$/, "");
      if (!/[.!?]$/.test(trimmed)) trimmed += ".";
      return trimmed;
    }
    if (selected && !/[.!?]$/.test(selected)) selected += ".";
    return selected;
  }

  // Helper: Truncate title cleanly to a maximum number of words
  function limitTitle(title, maxWords = 8) {
    if (!title) return "Infrastructure Recommendation";
    const words = String(title).trim().split(/\s+/);
    if (words.length > maxWords) {
      return words.slice(0, maxWords).join(" ");
    }
    return title.trim();
  }

  // Field validation and quality sanitization for recommendations
  function sanitizeRecommendation(r) {
    if (!r) return r;
    let title = limitTitle(r.title || "Infrastructure Recommendation", 8);
    let target = r.target_resource || r.resource || "Fleet-wide";
    if (target === "null" || target === "unknown") target = "Fleet-wide";

    let obs = r.observation || r.issue || "";
    // Fix incomplete fragments such as standalone "8%" or text lacking metric context
    if (/^\s*\(?\d+(\.\d+)?%\)?\.?\s*$/.test(obs) || obs.split(/\s+/).length < 4) {
      obs = `Resource ${target} consistently operates at very low average CPU utilization.`;
    }
    // Remove contradictory statements claiming low/zero CPU contributes significant carbon
    obs = obs.replace(/,?\s*contributing significant carbon[^\.]*/gi, "").trim();
    // Ensure carbon intensity has correct format and units (0.379 kg CO₂e/kWh)
    obs = obs.replace(/\b(\d{3})\s*kg(?:CO2e?)?\/(?:kwh|kWh)\b/g, "0.$1 kg CO₂e/kWh");
    obs = obs.replace(/\b(0\.\d+)\s*kg\s*\/\s*kWh\b/g, "$1 kg CO₂e/kWh");
    obs = obs.replace(/kgCO2e/g, "kg CO₂e");

    let act = r.action || "";
    const isUnderutil = /underutil|downsize|rightsize/i.test(title + " " + (r.category || ""));
    if (isUnderutil && !/standby|failover|peak/i.test(act)) {
      act = "Verify standby, failover and peak-demand requirements before rightsizing this resource or consolidating idle workloads.";
    }
    act = act.replace(/\(Save\s+[^)]+\)/g, "").trim();
    act = act.replace(/\bup to \d+%\s*(?:carbon|energy)?\s*reduction\b/gi, "potential carbon reduction");

    let benefit = String(r.expected_benefit || r.priority || "Medium").toLowerCase();
    benefit = benefit.charAt(0).toUpperCase() + benefit.slice(1);
    if (!["High", "Medium", "Low"].includes(benefit)) benefit = "Medium";

    return {
      ...r,
      title: title,
      target_resource: target,
      observation: limitSentences(obs, 2, 25),
      action: limitSentences(act, 2, 30),
      expected_benefit: benefit
    };
  }

  // Section 5: Optimization Recommendations & AI Insights
  function renderRecommendations() {
    const container = document.getElementById("recommendations-container");
    if (!container) return;

    const heading = document.getElementById("recommendations-heading");
    const badgesContainer = document.getElementById("recommendations-badges");

    // 1. Loading state
    if (State.recommendationsLoading) {
      if (badgesContainer) {
        badgesContainer.innerHTML = '<span class="badge badge-warning" style="font-size:10px">Generating Insights…</span>';
      }
      container.innerHTML = `
        <div class="empty-state" style="padding:28px 16px;text-align:center">
          <div class="spinner" style="margin:0 auto 10px;width:24px;height:24px;border:3px solid #d8e2dc;border-top-color:#1b6348;border-radius:50%;animation:spin 0.8s linear infinite"></div>
          <div style="font-weight:750;font-size:12px;color:var(--text);margin-bottom:4px">
            Analyzing Infrastructure Telemetry &amp; Formulating Recommendations…
          </div>
          <p class="small muted" style="margin:0">
            Evaluating multi-metric distributions, synthesizing anomaly explanations, and querying Gemini for prioritized optimization opportunities.
          </p>
        </div>
      `;
      return;
    }

    // 2. Live recommendations available
    if (State.recommendationsResult) {
      const res = State.recommendationsResult;
      const isGemini = res.generation_method === "GEMINI";

      if (heading) heading.textContent = "Optimization Recommendations & AI Insights";
      if (badgesContainer) {
        badgesContainer.innerHTML = `
          <span class="badge ${isGemini ? 'badge-primary' : 'badge-neutral'}" style="font-size:10px;font-weight:500" title="${isGemini ? 'Generated using Google Gemini API' : 'Generated via deterministic rule-based analysis engine'}">
            ${isGemini ? '✨ Gemini AI' : '📋 Rule-Based Analysis'}
          </span>
          <span class="badge badge-success" style="font-size:10px">${res.recommendations.length} Recommendations</span>
        `;
      }

      // PART 3: Simplified Operational Anomaly Explanations (Clean Cards, 5 Key Elements)
      const explanationsHtml = (res.anomaly_explanations && res.anomaly_explanations.length > 0)
        ? `
          <div style="margin-bottom:20px">
            <div style="font-weight:700;font-size:12.5px;color:#1e382b;margin-bottom:10px;display:flex;align-items:center;gap:8px">
              <span>🔍 Operational Anomaly Explanations</span>
              <span class="badge badge-warning" style="font-size:10px">${res.anomaly_explanations.length} Detected</span>
            </div>
            <div style="display:flex;flex-direction:column;gap:10px">
              ${res.anomaly_explanations.map(ae => {
                const obsValStr = ae.observed_value != null ? String(ae.observed_value) : '';
                return `
                <div style="background:#fcfdfd;border:1px solid #e1e7e4;border-radius:6px;padding:12px 14px">
                  <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;margin-bottom:8px;gap:6px">
                    <div style="font-size:12px">
                      <b>Resource:</b> <span style="color:#1b6348;font-weight:700">${escapeHtml(ae.resource_id)}</span>
                      <span class="small muted" style="margin-left:8px">${escapeHtml(ae.timestamp)}</span>
                    </div>
                    <span class="badge badge-warning" style="font-size:10.5px">
                      ${escapeHtml(ae.metric)}${obsValStr ? ` — ${escapeHtml(obsValStr)}` : ''}
                    </span>
                  </div>
                  <div style="font-size:11.5px;color:#2b3a33;line-height:1.45;margin-bottom:4px">
                    <b>What happened:</b> ${escapeHtml(limitSentences(ae.explanation, 2))}
                  </div>
                  <div style="font-size:11.5px;color:#5a6b63;line-height:1.45;margin-bottom:4px">
                    <b>Possible cause:</b> ${escapeHtml(limitSentences(ae.possible_causes, 1))}
                  </div>
                  <div style="font-size:11.5px;color:#1e5338;line-height:1.45">
                    <b>Recommended action:</b> ${escapeHtml(limitSentences(ae.investigation_steps, 1))}
                  </div>
                </div>
              `;}).join("")}
            </div>
          </div>
        `
        : `
          <div style="background:#f4f9f6;border:1px solid #d4ebd9;border-radius:6px;padding:10px 14px;font-size:11.5px;color:#226038;margin-bottom:16px">
            ✅ <b>No Operational Anomalies Detected:</b> All monitored telemetry metrics across instances operated within normal statistical baseline bounds.
          </div>
        `;

      // PART 4: Simplified Optimization Recommendations (Compact Cards, 5 Key Elements)
      const recommendationsHtml = (res.recommendations && res.recommendations.length > 0)
        ? `
          <div>
            <div style="font-weight:700;font-size:12.5px;color:#1e382b;margin-bottom:10px">
              💡 Prioritized Infrastructure Optimization Recommendations
            </div>
            <div style="display:flex;flex-direction:column;gap:10px">
              ${res.recommendations.map(rawR => {
                const r = sanitizeRecommendation(rawR);
                return `
                <div style="background:#fcfdfd;border:1px solid #e1e7e4;border-radius:6px;padding:12px 14px">
                  <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-start;margin-bottom:8px;gap:6px">
                    <div>
                      <div style="font-weight:700;font-size:12.5px;color:#1e382b;margin-bottom:2px">${escapeHtml(r.title)}</div>
                      <div class="small muted" style="font-size:11px">Target: <b style="color:#2b3a33">${escapeHtml(r.target_resource)}</b></div>
                    </div>
                    <div>
                      ${badge(r.expected_benefit)}
                    </div>
                  </div>
                  <div style="font-size:11.5px;color:#2b3a33;line-height:1.45;margin-bottom:4px">
                    <b>Issue:</b> ${escapeHtml(r.observation)}
                  </div>
                  <div style="font-size:11.5px;color:#1e5338;line-height:1.45">
                    <b>Action:</b> ${escapeHtml(r.action)}
                  </div>
                </div>
              `;}).join("")}
            </div>
          </div>
        `
        : `
          <div class="empty-state" style="padding:18px">No actionable recommendations identified for this dataset.</div>
        `;

      container.innerHTML = `
        <div class="alert alert-info" style="margin-bottom:16px;padding:10px 14px;font-size:12px;line-height:1.5;background:#f3f7f5;border:1px solid #d4e2db;color:#244033">
          <b>Fleet Assessment:</b> ${escapeHtml(limitSentences(res.summary, 3))}
          ${res.warning_or_limitation ? `<div class="small muted" style="margin-top:4px"><em>Note: ${escapeHtml(res.warning_or_limitation)}</em></div>` : ''}
        </div>
        ${explanationsHtml}
        ${recommendationsHtml}
      `;
      return;
    }

    // 3. Fallback demo baseline (Compact Cards)
    if (heading) heading.textContent = "Optimization Recommendations (Demo Baseline)";
    if (badgesContainer) {
      badgesContainer.innerHTML = `
        <span class="badge badge-neutral" style="font-size:10px">Demo Baseline</span>
        <span class="badge badge-success" style="font-size:10px">5 Recommendations</span>
      `;
    }

    container.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:10px">
        ${DEMO_DATA.recommendations.map(rawR => {
          const r = sanitizeRecommendation(rawR);
          return `
          <div style="background:#fcfdfd;border:1px solid #e1e7e4;border-radius:6px;padding:12px 14px">
            <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-start;margin-bottom:8px;gap:6px">
              <div>
                <div style="font-weight:700;font-size:12.5px;color:#1e382b;margin-bottom:2px">${escapeHtml(r.title)}</div>
                <div class="small muted" style="font-size:11px">Target: <b style="color:#2b3a33">${escapeHtml(r.target_resource)}</b></div>
              </div>
              <div>
                ${badge(r.expected_benefit)}
              </div>
            </div>
            <div style="font-size:11.5px;color:#2b3a33;line-height:1.45;margin-bottom:4px">
              <b>Issue:</b> ${escapeHtml(r.observation)}
            </div>
            <div style="font-size:11.5px;color:#1e5338;line-height:1.45">
              <b>Action:</b> ${escapeHtml(r.action)}
            </div>
          </div>
        `;}).join("")}
      </div>
    `;
  }

  /* ──────────────────────────────────────────────────────────────────────────
     5. EVENT HANDLERS & API INTEGRATION
     ────────────────────────────────────────────────────────────────────────── */

  function bindEvents() {
    // Header navigation triggers
    const ingestTrigger = document.getElementById("btn-ingest-trigger");
    if (ingestTrigger) {
      ingestTrigger.onclick = () => {
        const uploadSec = document.getElementById("upload-section");
        if (uploadSec) uploadSec.scrollIntoView({ behavior: "smooth" });
      };
    }

    const headerProvider = document.getElementById("header-provider-select");
    const ingestProvider = document.getElementById("ingest-provider-select");
    if (headerProvider && ingestProvider) {
      headerProvider.onchange = () => {
        ingestProvider.value = headerProvider.value;
        State.cloudProvider = headerProvider.value;
      };
      ingestProvider.onchange = () => {
        headerProvider.value = ingestProvider.value;
        State.cloudProvider = ingestProvider.value;
      };
    }

    // Drag and drop file ingestion
    const dropZone = document.getElementById("metric-drop-zone");
    const fileInput = document.getElementById("metric-file-input");
    const browseBtn = document.getElementById("btn-browse-file");
    const previewArea = document.getElementById("file-preview-area");
    const uploadBtn = document.getElementById("btn-upload-analyze");
    const alertArea = document.getElementById("upload-alert");
    const mappingCard = document.getElementById("mapping-confirmation-card");

    if (browseBtn && fileInput) browseBtn.onclick = () => fileInput.click();

    if (dropZone) {
      dropZone.ondragover = e => { e.preventDefault(); dropZone.classList.add("dragover"); };
      dropZone.ondragleave = () => dropZone.classList.remove("dragover");
      dropZone.ondrop = e => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          handleFile(e.dataTransfer.files[0]);
        }
      };
    }

    if (fileInput) {
      fileInput.onchange = () => {
        if (fileInput.files && fileInput.files[0]) handleFile(fileInput.files[0]);
      };
    }

    function handleFile(file) {
      const ext = file.name.split(".").pop().toLowerCase();
      if (ext !== "csv" && ext !== "json") {
        showAlert("error", "Unsupported file format. Please upload a .csv or .json file.");
        return;
      }

      State.selectedFile = file;
      renderFilePreview(file.name, (file.size / 1024).toFixed(1) + " KB", ext.toUpperCase());
      showAlert("info", `File "${escapeHtml(file.name)}" ready for upload. Click "Upload & Analyze" below.`);
      if (uploadBtn) uploadBtn.disabled = false;
    }

    function renderFilePreview(name, sizeStr, ext) {
      previewArea.style.display = "block";
      previewArea.innerHTML = `
        <div class="file-preview-card" style="padding:8px 12px">
          <div class="file-info" style="gap:8px">
            <span class="badge badge-neutral" style="font-size:10px">${escapeHtml(ext)}</span>
            <b style="font-size:11px">${escapeHtml(name)}</b>
            <span class="small muted">(${sizeStr})</span>
          </div>
          <button type="button" class="btn btn-ghost" id="btn-remove-file" style="color:#b33d3d;font-size:10px;padding:2px 6px">
            ✕ Remove
          </button>
        </div>
      `;
      const removeBtn = document.getElementById("btn-remove-file");
      if (removeBtn) {
        removeBtn.onclick = () => {
          State.selectedFile = null;
          State.uploadResult = null;
          State.analysisResult = null;
          fileInput.value = "";
          previewArea.style.display = "none";
          previewArea.innerHTML = "";
          if (uploadBtn) uploadBtn.disabled = true;
          alertArea.innerHTML = "";
          if (mappingCard) mappingCard.style.display = "none";
          renderOverview();
          renderAnomalies("anomalies");
          renderInventory();
          window.toast("File selection cleared");
        };
      }
    }

    // Load actual sample files from /samples/
    document.querySelectorAll(".sample-chip").forEach(chip => {
      chip.onclick = async () => {
        const type = chip.dataset.sample;
        const sampleMap = {
          aws: { file: "samples/aws_cloudwatch_sample.csv", name: "aws_cloudwatch_sample.csv", type: "text/csv" },
          azure: { file: "samples/azure_monitor_sample.json", name: "azure_monitor_sample.json", type: "application/json" },
          custom: { file: "samples/custom_baremetal_sample.csv", name: "custom_baremetal_sample.csv", type: "text/csv" },
          manual: { file: "samples/cloud_carbon_manual_test_dataset.csv", name: "cloud_carbon_manual_test_dataset.csv", type: "text/csv" }
        };
        const sample = sampleMap[type] || sampleMap.aws;

        try {
          const resp = await fetch(sample.file);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const blob = await resp.blob();
          const fileObj = new File([blob], sample.name, { type: sample.type });
          handleFile(fileObj);
        } catch (err) {
          showAlert("error", `Could not load sample file: ${err.message}`);
        }
      };
    });

    // Real Backend Upload & Immediate Phase 3 ML Analysis
    if (uploadBtn) {
      uploadBtn.onclick = async () => {
        if (!State.selectedFile) return;

        uploadBtn.disabled = true;
        uploadBtn.textContent = "Ingesting & Analyzing…";
        showAlert("info", `Step 1/2: Ingesting "${escapeHtml(State.selectedFile.name)}" to Cloud & Carbon backend...`);
        if (mappingCard) mappingCard.style.display = "none";

        try {
          const data = await ESGApi.cloudCarbonUpload(State.selectedFile);
          State.uploadResult = data;
          State.activePreviewRecords = data.preview_records || [];
          State.availableMetrics = data.available_metrics || [];

          // Handle ambiguous mappings
          if (data.processing_status === "REQUIRES_CONFIRMATION" && data.ambiguous_columns && data.ambiguous_columns.length > 0) {
            renderMappingConfirmation(data);
            showAlert("warning", `Upload processed with ${data.ambiguous_columns.length} ambiguous column(s). Please confirm mappings below.`);
          } else {
            showAlert("info", `Step 2/2: Ingestion complete (${data.accepted_records} records). Running ML Isolation Forest & Carbon Footprint analysis...`);

            // Phase 3: Run real ML anomaly detection and energy/carbon estimation
            const analysis = await ESGApi.cloudCarbonAnalyze(data.upload_id);
            State.analysisResult = analysis;

            const an = analysis.anomaly_detection;
            const em = analysis.emissions_estimation;
            const carbonDisplay = em.total_carbon_kgco2e != null
              ? formatCarbonKg(em.total_carbon_kgco2e)
              : `Factor Unavailable (${em.missing_factor_regions.join(", ")})`;

            showAlert(
              "success",
              `<b>Analysis Complete:</b> Format: ${data.file_format} | Provider: ${data.detected_provider} | ` +
              `ML Anomalies: <b>${an.anomalies_detected} flagged (${an.anomaly_percentage}%)</b> | ` +
              `Modeled Energy: <b>${em.total_energy_kwh.toFixed(2)} kWh</b> | Modeled Carbon: <b>${carbonDisplay}</b>.`
            );
            window.toast("ML Anomaly Detection and Carbon Footprint analysis completed.");

            // Build real time series for charts
            const liveSeries = buildTimeSeriesFromRecords(State.activePreviewRecords);
            if (liveSeries) {
              State.timeSeriesData = {
                "24h": liveSeries,
                "7d": liveSeries,
                "30d": liveSeries
              };
            }

            // Update Overview badge & Findings table
            const ovBadge = document.getElementById("overview-badge");
            if (ovBadge) ovBadge.textContent = `${data.detected_provider} Analyzed (${data.accepted_records} records)`;

            renderOverview();
            renderAnalyticsCharts();
            renderAnomalies(State.anomalyFilter);
            renderInventory();

            // Trigger Phase 4 AI Insights & Recommendations
            State.recommendationsLoading = true;
            renderRecommendations();

            try {
              const recs = await ESGApi.cloudCarbonGetRecommendations(data.upload_id);
              State.recommendationsResult = recs;
            } catch (recErr) {
              console.warn("Could not retrieve recommendations:", recErr);
            } finally {
              State.recommendationsLoading = false;
              renderRecommendations();
            }
          }

        } catch (err) {
          showAlert("error", `Backend processing failed: ${err.message}. Ensure backend is running on port 8001.`);
        } finally {
          uploadBtn.disabled = false;
          uploadBtn.textContent = "Upload & Analyze";
        }
      };
    }

    function renderMappingConfirmation(data) {
      if (!mappingCard) return;
      mappingCard.style.display = "block";

      const canonicalOptions = [
        "timestamp", "resource_id", "resource_type", "provider", "region",
        "cpu_utilization_pct", "memory_utilization_pct", "network_in", "network_out",
        "storage_used", "storage_capacity", "unmapped"
      ];

      mappingCard.innerHTML = `
        <div class="card" style="background:#fffcf5;border:1px solid #f0dfbb;padding:14px">
          <div style="font-weight:750;font-size:12px;color:#9b6819;margin-bottom:6px">
            ⚠️ Ambiguous Columns Detected — Confirm Target Mapping
          </div>
          <p class="small muted" style="margin-bottom:10px">
            The parser identified ambiguous column names in this dataset. Please map each to its canonical target field:
          </p>
          <div style="display:grid;gap:8px" id="mapping-fields-list">
            ${data.ambiguous_columns.map(ac => `
              <div style="display:flex;align-items:center;gap:10px">
                <span style="font-size:11px;font-weight:700;min-width:140px"><code>${escapeHtml(ac.source_column)}</code> &rarr;</span>
                <select class="filter mapping-target-select" data-source="${escapeHtml(ac.source_column)}" style="font-size:11px;padding:4px 8px">
                  ${canonicalOptions.map(opt => `<option value="${opt}" ${ac.candidate_fields.includes(opt) ? 'selected' : ''}>${opt}</option>`).join("")}
                </select>
              </div>
            `).join("")}
          </div>
          <button class="btn btn-primary" id="btn-submit-mapping" style="margin-top:12px;padding:5px 12px;font-size:11px">
            Confirm Mapping &amp; Run Analysis
          </button>
        </div>
      `;

      const submitBtn = document.getElementById("btn-submit-mapping");
      if (submitBtn) {
        submitBtn.onclick = async () => {
          submitBtn.disabled = true;
          submitBtn.textContent = "Reprocessing & Analyzing…";

          const confirmedMap = {};
          mappingCard.querySelectorAll(".mapping-target-select").forEach(sel => {
            confirmedMap[sel.dataset.source] = sel.value;
          });

          try {
            const reprocessed = await ESGApi.cloudCarbonConfirmMapping(data.upload_id, confirmedMap);
            State.uploadResult = reprocessed;
            State.activePreviewRecords = reprocessed.preview_records || [];
            State.availableMetrics = reprocessed.available_metrics || [];

            mappingCard.style.display = "none";

            // Run Phase 3 analysis after confirmation
            const analysis = await ESGApi.cloudCarbonAnalyze(data.upload_id);
            State.analysisResult = analysis;

            showAlert("success", `Mapping confirmed! ML Isolation Forest & Carbon modeling complete for ${reprocessed.accepted_records} records.`);
            window.toast("Mapping updated and analysis completed.");

            const liveSeries = buildTimeSeriesFromRecords(State.activePreviewRecords);
            if (liveSeries) {
              State.timeSeriesData = { "24h": liveSeries, "7d": liveSeries, "30d": liveSeries };
            }

            renderOverview();
            renderAnalyticsCharts();
            renderAnomalies(State.anomalyFilter);
            renderInventory();

            // Trigger Phase 4 AI Insights & Recommendations
            State.recommendationsLoading = true;
            renderRecommendations();

            try {
              const recs = await ESGApi.cloudCarbonGetRecommendations(data.upload_id);
              State.recommendationsResult = recs;
            } catch (recErr) {
              console.warn("Could not retrieve recommendations:", recErr);
            } finally {
              State.recommendationsLoading = false;
              renderRecommendations();
            }
          } catch (err) {
            showAlert("error", `Confirmation failed: ${err.message}`);
          } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = "Confirm Mapping & Run Analysis";
          }
        };
      }
    }

    function showAlert(type, msg) {
      alertArea.innerHTML = `<div class="alert alert-${type}" style="margin-bottom:0;padding:7px 11px;font-size:11px">${msg}</div>`;
    }

    // Anomaly filter buttons
    document.querySelectorAll("#anomaly-filter-bar button").forEach(btn => {
      btn.onclick = () => {
        State.anomalyFilter = btn.dataset.sev;
        renderAnomalies(State.anomalyFilter);
      };
    });

    // Resource search filter input
    const searchInput = document.getElementById("resource-search");
    if (searchInput) {
      searchInput.oninput = () => {
        State.resourceSearch = searchInput.value;
        renderInventory();
      };
    }
  }

  // Initialize
  renderLayout();

})();
