window.ESGApi=(function(){
var BASE=function(){return(localStorage.getItem("esg_api_base")||"http://localhost:8000").replace(/\/$/,"");};
var DOC_BASE=function(){return BASE();};  // Documents API runs on same backend as Green API
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
return{
  base:BASE,docBase:DOC_BASE,
  health:health,fullAnalysis:fullAnalysis,
  docHealth:docHealth,uploadDocument:uploadDocument,analyzeESG:analyzeESG,askDocument:askDocument,searchDocuments:searchDocuments,
  greenHealth:greenHealth,greenConnect:greenConnect,greenListAccounts:greenListAccounts,
  greenDeleteAccount:greenDeleteAccount,greenListRepos:greenListRepos,greenListBranches:greenListBranches,
  greenListPRs:greenListPRs,greenGetPR:greenGetPR,greenAnalyze:greenAnalyze,
  greenGetResults:greenGetResults,greenListScores:greenListScores
};
})();