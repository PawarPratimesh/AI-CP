(function(){
var app=document.getElementById("page-app");
if(!app)return;
var h="";
h+='<div id="pc-alert"></div>';
h+='<div class="grid-2" style="margin-bottom:16px">';
h+='<div class="card"><div class="section-head"><div><div class="eyebrow">OLD POLICY (BASELINE)</div><h2>Previous Policy</h2><p>Upload the baseline PDF.</p></div><span class="badge badge-neutral">Required</span></div><div class="file-drop" id="old-drop"><input type="file" id="old-file" accept=".pdf"><div style="font-size:22px;margin-bottom:6px">PDF</div><div class="small muted">PDF only</div><div class="file-name" id="old-name" style="margin-top:8px">No file selected</div><button class="btn btn-secondary" id="old-btn" style="margin-top:9px">Choose Previous Version</button></div></div>';
h+='<div class="card"><div class="section-head"><div><div class="eyebrow">NEW POLICY (PROPOSED)</div><h2>Current Policy</h2><p>Upload the proposed PDF.</p></div><span id="bs" class="badge badge-neutral">Checking...</span></div><div class="file-drop" id="new-drop"><input type="file" id="new-file" accept=".pdf"><div style="font-size:22px;margin-bottom:6px">PDF</div><div class="small muted">PDF only</div><div class="file-name" id="new-name" style="margin-top:8px">No file selected</div><button class="btn btn-secondary" id="new-btn" style="margin-top:9px">Choose Updated Version</button></div></div>';
h+='</div>';
h+='<div class="toolbar" style="margin-bottom:14px"><div class="legend"><span><i class="green-dot"></i>Strengthened</span><span><i class="red-dot"></i>Weakened</span><span><i class="amber-dot"></i>Modified</span><span><i class="blue-dot"></i>New</span></div><div class="spacer"></div><label style="font-size:11px;display:flex;align-items:center;gap:6px"><input type="checkbox" id="use-ai-rec" checked> AI Recommendations</label><button class="btn btn-primary" id="compare-btn">Compare Policies</button></div>';
h+='<div id="comparison-results"></div>';
app.innerHTML=h;
var oi=document.getElementById("old-file"),ni=document.getElementById("new-file");
document.getElementById("old-btn").onclick=function(){oi.click();};
document.getElementById("new-btn").onclick=function(){ni.click();};
oi.onchange=function(){document.getElementById("old-name").textContent=oi.files[0]?oi.files[0].name:"No file selected";};
ni.onchange=function(){document.getElementById("new-name").textContent=ni.files[0]?ni.files[0].name:"No file selected";};
["old","new"].forEach(function(s){
  var d=document.getElementById(s+"-drop"),inp=document.getElementById(s+"-file"),nm=document.getElementById(s+"-name");
  d.addEventListener("dragover",function(e){e.preventDefault();d.classList.add("drag");});
  d.addEventListener("dragleave",function(){d.classList.remove("drag");});
  d.addEventListener("drop",function(e){e.preventDefault();d.classList.remove("drag");var f=e.dataTransfer.files[0];if(f&&f.type==="application/pdf"){var dt=new DataTransfer();dt.items.add(f);inp.files=dt.files;nm.textContent=f.name;}});
});
function sa(t,m){var el=document.getElementById("pc-alert");el.innerHTML=m?'<div class="alert alert-'+t+'">'+escapeHtml(m)+'</div>':"";};
var bs=document.getElementById("bs");
ESGApi.health().then(function(){bs.className="badge badge-success";bs.textContent="Backend connected";}).catch(function(){bs.className="badge badge-high";bs.textContent="Backend offline (port 8000)";});
function gc(x){var r=String((x&&x.classification)||"").toUpperCase();if(r.indexOf("STRENGTH")>=0)return"STRENGTHENED";if(r.indexOf("WEAK")>=0||r.indexOf("REDUC")>=0)return"WEAKENED";if(r.indexOf("REMOV")>=0)return"REMOVED";if(r.indexOf("NEW")>=0)return"NEW";if(r.indexOf("MODIF")>=0)return"MODIFIED";return"UNCHANGED";}
function pct(v){var n=Number(v);return isFinite(n)?Math.round(n*100)+"%":"--";}
function dv(v){return(v==null||v==="")?"-":typeof v==="object"?JSON.stringify(v):String(v);}
function pg(s){var p=(s&&s.page_numbers)||[];return Array.isArray(p)?(p.join(",")||"-"):(p||"-");}
function tx(x,w){var s=(x&&x[w+"_source"])||{};return s.evidence||(x&&x[w+"_text"])||("No "+w+" text.");}
function card(x,i){
  var c=gc(x),lbl=c==="MODIFIED"?"MODIFIED/CHANGED":c,id=(x&&(x.new_commitment_id||x.old_commitment_id))||String(i+1);
  var os=(x&&x.old_source)||{},ns=(x&&x.new_source)||{};
  return'<article class="change-card"><div class="change-head"><div><b>'+escapeHtml(id)+'</b><span class="small muted"> &bull; '+escapeHtml((x&&x.category)||"Commitment")+'</span></div>'+badge(lbl)+'</div>'
  +'<div class="change-body"><div class="policy-pane"><div class="pane-label">OLD &bull; PAGES '+escapeHtml(pg(os))+'</div><div class="policy-text">'+escapeHtml(tx(x,"old"))+'</div></div>'
  +'<div class="policy-pane"><div class="pane-label">NEW &bull; PAGES '+escapeHtml(pg(ns))+'</div><div class="policy-text">'+escapeHtml(tx(x,"new"))+'</div></div></div>'
  +'<div class="change-foot"><div class="evidence"><div class="confidence">'+escapeHtml(lbl)+' CONF '+escapeHtml(pct(x&&x.confidence))+' MATCH '+escapeHtml(pct(x&&x.match_confidence))+'</div>'
  +'<div class="quote">'+escapeHtml((x&&x.reason)||"No reason.")+'</div></div></div></article>';
}
function risks(rep,sc){
  if(!rep||!rep.risks)return'<div class="empty-state">No risk data.</div>';
  var agg=rep.aggregate_risk||{};
  var ah=["overall","environmental","social","governance"].map(function(k){var it=agg[k]||{};return'<div class="metric"><div class="label">'+k+'</div><div class="value">'+dv(it.risk_score)+'</div><div class="small muted">'+dv(it.risk_level)+'</div></div>';}).join("");
  var sh=["environmental","social","governance","overall"].map(function(k){return'<div class="metric"><div class="label">'+k+' score</div><div class="value">'+dv(sc&&sc[k])+'</div></div>';}).join("");
  var tr=(rep.risks||[]).slice(0,5).map(function(r){return'<div class="recommendation-row"><div class="row-title">'+escapeHtml(r.commitment_id||"Risk")+' '+badge(r.risk_level||"")+'</div><div class="small muted">Score: '+dv(r.risk_score)+'</div><div class="small">'+escapeHtml(r.description||"")+'</div></div>';}).join("");
  return'<div class="grid-2" style="margin-bottom:10px">'+ah+'</div>'+(tr||'<div class="empty-state">No risks.</div>')+'<div class="small muted" style="margin-top:8px"><b>ESG Scores:</b><div class="grid-2">'+sh+'</div></div>';
}
function recs(re){
  if(!re||!re.length)return'<div class="empty-state">No recommendations.</div>';
  return re.slice(0,10).map(function(r){
    var t=typeof r==="string"?r:(r.title||"Recommendation");
    var d=typeof r==="string"?"":(r.action||r.description||"");
    var p=typeof r==="object"?(r.priority||""):"";
    return'<div class="recommendation-row"><div class="row-title">'+escapeHtml(t)+(p?" "+badge(p):"")+'</div>'+(d?'<div class="small muted" style="margin-top:5px">'+escapeHtml(d)+'</div>':"")+'</div>';
  }).join("");
}
function renderResult(data){
  var cs=data.comparisons||[],sm=data.comparison_summary||{},ri=data.risk_report||{},sc=ri.esg_scores||{},re=data.recommendations||[];
  var cnt=function(k){return Number(sm[k]||0);};
  var sb=[["NEW","new","badge-low"],["REMOVED","removed","badge-high"],["MODIFIED/CHANGED","modified","badge-medium"],["WEAKENED","weakened","badge-high"],["STRENGTHENED","strengthened","badge-low"],["UNCHANGED","unchanged","badge-neutral"]].map(function(t){return'<span class="badge '+t[2]+'">'+t[0]+': '+cnt(t[1])+'</span>';}).join(" ");
  document.getElementById("comparison-results").innerHTML=
    '<div class="card" style="margin-bottom:15px"><div class="section-head"><div><h2>Policy Changes Detected</h2><p>'+cs.length+' commitment(s) compared.</p></div></div><div class="toolbar" style="flex-wrap:wrap;gap:8px">'+sb+'</div></div>'
    +'<div style="margin-bottom:16px">'+(cs.length?cs.map(card).join(""):'<div class="empty-state">No items returned.</div>')+'</div>'
    +'<div class="grid-2"><section class="card"><div class="section-head"><div><h2>Risk &amp; ESG Scores</h2><p>ISO 31000-aligned.</p></div></div>'+risks(ri,sc)+'</section>'
    +'<section class="card"><div class="section-head"><div><h2>Recommendations</h2><p>AI-generated actions.</p></div></div>'+recs(re)+'</section></div>'
    +(data.warnings&&data.warnings.length?'<div class="alert alert-info" style="margin-top:12px">'+escapeHtml(data.warnings.join(" | "))+'</div>':"");
}
document.getElementById("compare-btn").onclick=function(){
  if(!oi.files[0]||!ni.files[0]){sa("error","Please select both PDFs first.");return;}
  var ai=document.getElementById("use-ai-rec").checked,btn=document.getElementById("compare-btn"),res=document.getElementById("comparison-results");
  sa("info","Uploading both policies and running full analysis...");btn.disabled=true;
  loading(res,"Extracting commitments, comparing, scoring risks...");
  ESGApi.fullAnalysis(oi.files[0],ni.files[0],ai)
    .then(function(data){renderResult(data);sa("success","Policy comparison completed.");toast("Policy comparison completed");})
    .catch(function(e){sa("error",e.message);res.innerHTML='<div class="empty-state"><b>Analysis failed:</b> '+escapeHtml(e.message)+'<div class="small muted" style="margin-top:5px">Ensure backend is running on port 8000.</div></div>';})
    .finally(function(){btn.disabled=false;});
};
})();