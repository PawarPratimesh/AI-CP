window.MOCK={
scores:[
 {label:"Overall ESG",value:82,trend:"+4.2%",dir:"up",note:"vs previous period"},
 {label:"Environmental",value:85,trend:"+5.1%",dir:"up",note:"vs previous period"},
 {label:"Social",value:76,trend:"+2.8%",dir:"up",note:"vs previous period"},
 {label:"Governance",value:88,trend:"+1.6%",dir:"up",note:"vs previous period"}
],
riskCounts:{High:2,Medium:3,Low:4},
findings:[
 {title:"Supplier labour certificate expired",category:"Social",severity:"High",source:"Supplier Intelligence",confidence:93,description:"A required labour-compliance certificate is past its validity date."},
 {title:"Measurable energy-efficiency target missing",category:"Environmental",severity:"Medium",source:"Documents",confidence:91,description:"Current evidence describes an ambition without a measurable target."},
 {title:"Production API latency anomaly",category:"Environmental",severity:"Medium",source:"Cloud & Carbon",confidence:88,description:"Estimated resource utilization suggests an efficiency opportunity."}
],
recommendations:[
 {title:"Define a measurable energy-efficiency target",category:"Environmental",source:"Document Intelligence",reason:"Current policy language is directional rather than measurable.",action:"Add a numeric target, baseline and review deadline."},
 {title:"Resolve supplier compliance evidence gap",category:"Social",source:"Supplier Intelligence",reason:"Required labour evidence is expired.",action:"Request updated evidence and assign an owner."},
 {title:"Review production resource anomaly",category:"Environmental",source:"Cloud & Carbon",reason:"A recurring utilization pattern was flagged.",action:"Review right-sizing and workload scheduling."},
 {title:"Keep governance targets time-bound",category:"Governance",source:"Policy Checker",reason:"Policy comparison can detect target or deadline dilution.",action:"Retain measurable targets and explicit deadlines."}
],
documents:[
 {name:"Sustainability Report FY 2025–26.pdf",type:"PDF",status:"Analyzed",pages:48,uploaded:"18 Sep 2026",findings:12},
 {name:"ESG Policy 2025.pdf",type:"PDF",status:"Analyzed",pages:27,uploaded:"15 Sep 2026",findings:8},
 {name:"Supplier Code of Conduct.docx",type:"DOCX",status:"Processing",pages:14,uploaded:"14 Sep 2026",findings:4},
 {name:"Board ESG Minutes.txt",type:"TXT",status:"Analyzed",pages:6,uploaded:"09 Sep 2026",findings:2}
],
suppliers:[
 ["Apex Components","82","86","77","84","12 / 12","Low"],
 ["Northstar Logistics","73","70","68","81","9 / 10","Medium"],
 ["GreenField Packaging","91","94","88","90","14 / 14","Low"],
 ["Vertex Manufacturing","61","58","62","64","7 / 11","High"],
 ["Orion Services","79","81","76","80","10 / 10","Low"]
],
risks:[
 {title:"Supplier labour certificate expired",category:"Social",severity:"High",source:"Supplier Intelligence",status:"Open",confidence:93,evidence:"Labour compliance certificate expired on 30 Aug 2026.",recommendation:"Request updated certificate and assign a compliance owner."},
 {title:"Carbon target lacks a measurable horizon",category:"Environmental",severity:"Medium",source:"Policy Checker",status:"In Progress",confidence:89,evidence:"Policy language describes reduction ambition without a numeric target.",recommendation:"Define a numeric target, baseline and deadline."},
 {title:"Energy efficiency target not evidenced",category:"Environmental",severity:"Medium",source:"Documents",status:"Open",confidence:91,evidence:"Sustainability report does not show a measurable target in the cited section.",recommendation:"Add target, baseline, owner and review cadence."},
 {title:"Repeated API calls in repository",category:"Environmental",severity:"Low",source:"Green Code",status:"Open",confidence:86,evidence:"Repeated calls detected in src/services/report.js.",recommendation:"Cache reusable responses where safe."},
 {title:"Production resource utilization anomaly",category:"Environmental",severity:"Medium",source:"Cloud & Carbon",status:"In Progress",confidence:88,evidence:"Estimated utilization pattern is outside the configured normal range.",recommendation:"Review right-sizing and workload scheduling."},
 {title:"Board review evidence incomplete",category:"Governance",severity:"Low",source:"Documents",status:"Resolved",confidence:84,evidence:"One quarterly review artifact was missing from the evidence set.",recommendation:"Maintain a complete quarterly governance evidence trail."}
],
insights:[
 {priority:"High",category:"Social",title:"Close supplier evidence gap",source:"Supplier Intelligence",reason:"One high-risk supplier has expired labour evidence.",action:"Obtain current documentation and confirm expiry monitoring."},
 {priority:"Medium",category:"Environmental",title:"Make policy targets measurable",source:"Policy Checker",reason:"A draft change removes numeric specificity from a reduction commitment.",action:"Retain measurable target + deadline in the proposed wording."},
 {priority:"Medium",category:"Environmental",title:"Review production server anomaly",source:"Cloud & Carbon",reason:"Estimated utilization indicates an efficiency opportunity.",action:"Assess right-sizing before the next reporting cycle."},
 {priority:"Low",category:"Governance",title:"Standardize evidence ownership",source:"Document Intelligence",reason:"Findings use mixed ownership metadata.",action:"Assign a consistent owner field to recurring evidence checks."}
],
cloud:[
 ["Production API","Compute","62%","Normal","168 kg CO₂e","Medium"],
 ["Analytics Worker","Compute","18%","Underutilized","74 kg CO₂e","High"],
 ["Object Storage","Storage","71%","Normal","53 kg CO₂e","Low"],
 ["CI Runner","Compute","12%","Underutilized","31 kg CO₂e","Medium"]
],
greenCode:[
 {title:"Repeated API calls",severity:"High",file:"src/services/report.js",line:"84–103",explain:"The same remote response is requested multiple times in one execution path.",recommend:"Cache reusable responses or consolidate calls."},
 {title:"Unnecessary database queries",severity:"Medium",file:"src/repositories/esg.js",line:"142",explain:"A loop triggers repeated lookups for data that can be fetched in one query.",recommend:"Batch the query and reuse the returned collection."},
 {title:"Large payload transformation",severity:"Low",file:"src/utils/export.js",line:"51",explain:"A transformation processes a larger object than required by the export.",recommend:"Select only required fields before transformation."}
]
};