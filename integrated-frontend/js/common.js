(function(){
const nav=[
 ["index.html","Dashboard","▦",""],
 ["documents.html","Document Center","▤",""],
 ["policy-checker.html","Policy Checker","⌁","v2 vs v1"],
 ["suppliers.html","Suppliers","♧","120"],
 ["green-code.html","Green Code","⌘","3"],
 ["cloud-carbon.html","Cloud & Carbon","◌","3"],
 ["risks.html","ESG Risk Center","△","5"],
 ["insights.html","AI Insights","✦","5 recs"],
 ["reports.html","ESG Reports","▥",""],
 ["settings.html","Settings","⚙",""]
];
const page=document.body.dataset.page||"dashboard";
const activeFile=page==="dashboard"?"index.html":page+".html";
document.getElementById("app-shell").innerHTML=`
<aside class="app-sidebar" id="sidebar">
 <div class="brand"><div class="brand-mark">E</div><div class="brand-title">ESG Intelligence</div><div class="brand-sub">Enterprise Sustainability Platform</div></div>
 <div class="nav-label">NAVIGATION</div><nav class="side-nav">${nav.map(n=>`<a class="nav-item ${n[0]===activeFile?'active':''}" href="${n[0]}"><span class="nav-icon">${n[2]}</span><span>${n[1]}</span>${n[3]?`<span class="nav-badge ${n[1]==='ESG Risk Center'?'red':''}">${n[3]}</span>`:''}</a>`).join("")}</nav>
 <div class="sidebar-bottom"><div class="profile-mini"><div class="avatar">PS</div><div><div class="name">Pragati Sahu</div><div class="role">Project Admin</div></div></div></div>
</aside><div class="sidebar-overlay" id="sidebar-overlay"></div>`;
const titleMap={dashboard:"ESG Dashboard",documents:"Document Center","policy-checker":"Policy Intelligence & Checker",suppliers:"Supplier Intelligence","green-code":"Green Code","cloud-carbon":"Cloud & Carbon",risks:"ESG Risk Center",insights:"AI Insights",reports:"ESG Reports",settings:"Settings"};
document.getElementById("topbar").innerHTML=`
<header class="topbar"><button class="top-icon mobile-menu" id="mobile-menu">☰</button><div class="top-title">${titleMap[page]||"ESG Intelligence"}</div>
<div class="org-select">Acme Global Logistics Corp <span class="muted">⌄</span></div>
<div class="top-actions"><div class="search-box"><span class="search-icon">⌕</span><input id="global-search" placeholder="Search ESG data..."></div><button class="top-icon" data-toast="No new notifications">♢</button><button class="top-icon" data-toast="Workspace synced">↻</button><div class="top-avatar">PS</div></div></header>`;
const side=document.getElementById("sidebar"), overlay=document.getElementById("sidebar-overlay"), menu=document.getElementById("mobile-menu");
if(menu)menu.onclick=()=>{side.classList.toggle("open");overlay.classList.toggle("open")};
if(overlay)overlay.onclick=()=>{side.classList.remove("open");overlay.classList.remove("open")};
document.querySelectorAll("[data-toast]").forEach(el=>el.addEventListener("click",()=>toast(el.dataset.toast)));
window.toast=function(msg){let c=document.querySelector(".toast-container");if(!c){c=document.createElement("div");c.className="toast-container";document.body.appendChild(c)}let t=document.createElement("div");t.className="toast";t.textContent=msg;c.appendChild(t);setTimeout(()=>t.remove(),2600)};
window.escapeHtml=function(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))};
window.badge=function(v){const x=String(v||"").toLowerCase();const cls=x.includes("high")||x.includes("error")||x.includes("weakened")||x.includes("removed")?"badge-high":x.includes("medium")||x.includes("warning")||x.includes("changed")||x.includes("modified")?"badge-medium":x.includes("low")||x.includes("success")||x.includes("strengthened")||x.includes("added")?"badge-low":"badge-neutral";return `<span class="badge ${cls}">${escapeHtml(v)}</span>`};
window.loading=function(el,msg="Loading..."){el.innerHTML=`<div class="loading-state"><div class="spinner"></div><div class="muted">${escapeHtml(msg)}</div></div>`};
window.apiBase=function(){return localStorage.getItem("esg_api_base")||"http://localhost:8000"};
})();