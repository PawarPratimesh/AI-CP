window.ESGApi=(function(){
var BASE=function(){return(localStorage.getItem("esg_api_base")||"http://localhost:8000").replace(/\/$/,"");};
var DOC_BASE=function(){return(localStorage.getItem("esg_doc_api_base")||"http://localhost:8001").replace(/\/$/,"");};
async function request(path,opts,baseUrl){
  var url=(baseUrl||BASE())+path;var res;
  try{res=await fetch(url,opts||{});}catch(err){throw new Error("Network error: "+err.message);}
  var data=null;try{data=await res.json();}catch(_){}
  if(!res.ok)throw new Error((data&&(data.detail||data.message))||"Request failed ("+res.status+")");
  return data;
}
function health(){return request("/health");}
function fullAnalysis(oldFile,newFile,useAI){
  var fd=new FormData();fd.append("old_policy",oldFile);fd.append("new_policy",newFile);
  return request("/api/full-analysis?use_ai_recommendations="+(useAI===false?"false":"true"),{method:"POST",body:fd});
}
function docHealth(){return request("/health",{},DOC_BASE());}
function uploadDocument(file){var fd=new FormData();fd.append("file",file);return request("/documents/upload",{method:"POST",body:fd},DOC_BASE());}
function analyzeESG(document_id){return request("/documents/analyze-esg",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({document_id:document_id})},DOC_BASE());}
function askDocument(query,n_results){return request("/documents/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,n_results:n_results||3})},DOC_BASE());}
function searchDocuments(query,n_results){return request("/documents/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,n_results:n_results||3})},DOC_BASE());}
/* ── Green Software Intelligence ── */
var j=function(b){return{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)};};
function greenHealth(){return request("/green/health");}
function greenConnect(token,demo){return request("/green/github/connect",j({token:token||null,demo:!!demo}));}
function greenListAccounts(){return request("/green/github/accounts");}
function greenDeleteAccount(id){return request("/green/github/accounts/"+id,{method:"DELETE"});}
function greenListRepos(accountId){return request("/green/github/accounts/"+accountId+"/repositories");}
function greenListBranches(repoId){return request("/green/github/repositories/"+repoId+"/branches");}
function greenListPRs(repoId,state){return request("/green/github/repositories/"+repoId+"/pulls?state="+(state||"open"));}
function greenGetPR(repoId,prNum){return request("/green/github/repositories/"+repoId+"/pulls/"+prNum);}
function greenAnalyze(repositoryId,prNumber){return request("/green/analysis/analyze",j({repository_id:repositoryId,pr_number:prNumber}));}
function greenGetResults(prId){return request("/green/analysis/results/"+prId);}
function greenListScores(){return request("/green/analysis/scores");}
/* ── Cloud & Carbon Module (Member 4) ── */
function cloudCarbonHealth(){return request("/api/cloud-carbon/health",{},DOC_BASE());}
function cloudCarbonUpload(file){
  var fd=new FormData();
  fd.append("file",file);
  return request("/api/cloud-carbon/upload",{method:"POST",body:fd},DOC_BASE());
}
function cloudCarbonPreview(uploadId){
  return request("/api/cloud-carbon/preview/"+uploadId,{},DOC_BASE());
}
function cloudCarbonConfirmMapping(uploadId,mapping){
  return request("/api/cloud-carbon/confirm-mapping/"+uploadId,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({mapping:mapping})
  },DOC_BASE());
}
function cloudCarbonAnomalyDetection(uploadId,opts){
  return request("/api/cloud-carbon/anomaly-detection/"+uploadId,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(opts||{})
  },DOC_BASE());
}
function cloudCarbonEstimateEmissions(uploadId,opts){
  return request("/api/cloud-carbon/estimate-emissions/"+uploadId,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(opts||{})
  },DOC_BASE());
}
function cloudCarbonAnalyze(uploadId,anomalyOpts,emissionsOpts){
  return request("/api/cloud-carbon/analyze/"+uploadId,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      anomaly_req: anomalyOpts||null,
      emissions_req: emissionsOpts||null
    })
  },DOC_BASE());
}
function cloudCarbonGetAnalysis(uploadId){
  return request("/api/cloud-carbon/analysis/"+uploadId,{},DOC_BASE());
}
function cloudCarbonGetRecommendations(uploadId){
  return request("/api/cloud-carbon/recommendations/"+uploadId,{},DOC_BASE());
}
function cloudCarbonGenerateRecommendations(uploadId,forceRuleBased){
  var q=forceRuleBased?"?force_rule_based=true":"";
  return request("/api/cloud-carbon/recommendations/"+uploadId+q,{method:"POST"},DOC_BASE());
}
return{
  base:BASE,docBase:DOC_BASE,
  health:health,fullAnalysis:fullAnalysis,
  docHealth:docHealth,uploadDocument:uploadDocument,analyzeESG:analyzeESG,askDocument:askDocument,searchDocuments:searchDocuments,
  greenHealth:greenHealth,greenConnect:greenConnect,greenListAccounts:greenListAccounts,
  greenDeleteAccount:greenDeleteAccount,greenListRepos:greenListRepos,greenListBranches:greenListBranches,
  greenListPRs:greenListPRs,greenGetPR:greenGetPR,greenAnalyze:greenAnalyze,
  greenGetResults:greenGetResults,greenListScores:greenListScores,
  cloudCarbonHealth:cloudCarbonHealth,cloudCarbonUpload:cloudCarbonUpload,
  cloudCarbonPreview:cloudCarbonPreview,cloudCarbonConfirmMapping:cloudCarbonConfirmMapping,
  cloudCarbonAnomalyDetection:cloudCarbonAnomalyDetection,
  cloudCarbonEstimateEmissions:cloudCarbonEstimateEmissions,
  cloudCarbonAnalyze:cloudCarbonAnalyze,
  cloudCarbonGetAnalysis:cloudCarbonGetAnalysis,
  cloudCarbonGetRecommendations:cloudCarbonGetRecommendations,
  cloudCarbonGenerateRecommendations:cloudCarbonGenerateRecommendations
};
})();