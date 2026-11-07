# ESG Policy Comparator & Risk Methodology

## 1. Standard basis

### Risk assessment
The risk workflow is **aligned with ISO 31000:2018 – Risk management – Guidelines**. ISO 31000 provides principles and a process for identifying, analysing, evaluating, treating, monitoring and communicating risk. It does **not** prescribe one universal 1–5 scoring formula, so this project documents its operational scoring criteria explicitly.

### Policy comparison
The comparator uses an **ESRS 2-style target structure** for comparability: policy objective, metric/target value, unit or direction, scope, baseline/base year, target period/deadline, milestones where available, and methodology/evidence. This follows the fields EFRAG describes for disclosure of measurable, time-bound sustainability targets.

## 2. Policy comparison rules

A commitment is matched using:
1. Commitment ID as a strong signal, but never as unconditional proof.
2. Topic/category compatibility.
3. Metric similarity.
4. Policy-statement similarity.
5. Scope, baseline and deadline similarity.

If the same ID is reused for unrelated metrics, the records are **not forced into a comparison**. A reused ID is rejected when policy-statement, metric and target similarities are all weak. The records can then become one `REMOVED` and one `NEW` record.

### Classifications
- **STRENGTHENED** — target ambition increases, deadline moves earlier, scope expands, or monitoring/obligation becomes stronger.
- **WEAKENED** — target ambition decreases, deadline moves later, scope narrows, or monitoring/obligation becomes weaker.
- **UNCHANGED** — no meaningful change or only equivalent wording.
- **NEW** — commitment appears only in the new policy.
- **REMOVED** — commitment appears only in the old policy.
- **MODIFIED** — the same/related commitment changed, but available structured data does not support a defensible stronger/weaker conclusion.

For reduction metrics, a larger reduction percentage is stronger. For increase metrics, a larger increase is stronger. Deadline comparisons treat an earlier target year as stronger. Raw first-number extraction is intentionally not used, so section numbers such as `4.6` cannot become ESG targets.

## 3. Risk scoring rules

The core matrix is:

`Risk = Likelihood × Impact`

Both are 1–5.

| Score | Level |
|---:|---|
| 1–4 | Low |
| 5–9 | Moderate |
| 10–16 | High |
| 17–25 | Critical |

The API also exposes a 0–100 display score: `(Likelihood × Impact) / 25 × 100`. The equivalent display bands are 0–19.99 Low, 20–39.99 Moderate, 40–67.99 High and 68–100 Critical.

### Likelihood
1 Rare, 2 Unlikely, 3 Possible, 4 Likely, 5 Almost certain.

### Impact
1 Negligible, 2 Minor, 3 Moderate, 4 Major, 5 Severe/Catastrophic.

For this policy-change screening application, the implementation uses a documented operational mapping from change type to baseline likelihood/impact:

| Classification | Likelihood | Impact | Reasoning |
|---|---:|---:|---|
| REMOVED | 4 | 5 | Existing commitment/control disappears. |
| WEAKENED | 4 | 4 | Ambition/control is reduced. |
| MODIFIED | 3 | 3 | Material change, direction uncertain. |
| NEW | 2 | 2 | New exposure/control needs review. |
| STRENGTHENED | 1 | 2 | Stronger commitment generally lowers exposure. |
| UNCHANGED | 1 | 2 | No detected policy deterioration. |

These mappings are **application criteria**, not values mandated by ISO 31000. They are intentionally visible and testable rather than hidden in code.

Evidence quality is reported separately from 1–5 based on extraction/comparison confidence. It does not discount the risk score, because weak evidence should not mathematically make an underlying risk look smaller.

## 4. ESG category score

For each E/S/G category:

`Category score = 100 - average risk display score`

Overall score is the equal-weight average of Environmental, Social and Governance category scores. This is an application-level dashboard indicator, not an ISO or ESRS certification score.
