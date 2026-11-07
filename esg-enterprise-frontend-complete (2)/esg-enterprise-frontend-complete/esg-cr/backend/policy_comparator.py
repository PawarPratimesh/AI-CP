"""Standard-aligned comparison of old vs new structured ESG commitments.

Methodology:
- Commitment matching uses ID only as a strong signal; metric/topic/scope are
  checked so a reused ID cannot silently compare unrelated commitments.
- Comparison fields follow the target attributes commonly disclosed under ESRS 2:
  metric/target, scope, baseline, target period and supporting methodology.
- Quantitative target direction is interpreted from the commitment language
  (reduce/decrease/lower vs increase/raise/higher), not by raw-number comparison.

"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable

from schemas import Commitment, CommitmentComparison, ComparisonSummary, SourceEvidence

logger = logging.getLogger(__name__)

COMPARE_FIELDS = (
    "policy_statement", "metric", "baseline", "target", "deadline",
    "responsible_owner", "scope", "evidence_requirement",
    "monitoring_frequency", "escalation",
)

CLASSIFICATIONS = ("STRENGTHENED", "WEAKENED", "UNCHANGED", "NEW", "REMOVED", "MODIFIED")
MATCH_THRESHOLD = 0.72
PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
YEAR_RE = re.compile(r"\b(20\d{2})\b")
HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b", re.I)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
FREQ_RANK = {
    "daily": 5, "weekly": 4, "monthly": 3, "quarterly": 3,
    "every three months": 3, "every 3 months": 3,
    "twice each year": 2, "twice yearly": 2, "twice per year": 2,
    "every six months": 2, "every 6 months": 2, "semiannual": 2,
    "semi-annually": 2, "annual": 1, "annually": 1,
    "once each year": 1, "yearly": 1,
}
EMPTY_SOURCE = SourceEvidence(page_numbers=[], evidence="")


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


def _tokens(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "will", "shall", "company", "this", "that", "by", "to", "of", "in", "on", "a", "an"}
    return {t for t in re.findall(r"[a-z0-9]+", normalize_text(text)) if t not in stop}


def jaccard(left: str | None, right: str | None) -> float:
    a, b = _tokens(left or ""), _tokens(right or "")
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def changed_fields(old: Commitment, new: Commitment) -> list[str]:
    return [f for f in COMPARE_FIELDS if normalize_text(getattr(old, f)) != normalize_text(getattr(new, f))]


def _first_percent(value: str | None) -> float | None:
    match = PERCENT_RE.search(value or "")
    return float(match.group(1)) if match else None


def _first_year(value: str | None) -> int | None:
    match = YEAR_RE.search(value or "")
    return int(match.group(1)) if match else None


def _target_number(value: str | None) -> float | None:
    """Extract a target number only when it has target-like context.

    Deliberately avoids generic first-number extraction because values such as
    section labels (e.g. '4.6 Diversity') are not targets.
    """
    text = value or ""
    percent = _first_percent(text)
    if percent is not None:
        return percent
    hours = HOURS_RE.search(text)
    if hours:
        return float(hours.group(1))
    patterns = (
        r"(?:target|threshold|limit|cap|below|under|less than|at least|at most|up to)\s*(?:of\s*)?(-?\d+(?:\.\d+)?)",
        r"(-?\d+(?:\.\d+)?)\s*(?:units?|tonnes?|tons?|tco2e|kg|mwh|kwh)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1))
    return None


def _freq_rank(value: str | None) -> int | None:
    text = normalize_text(value)
    for key, rank in FREQ_RANK.items():
        if key in text:
            return rank
    return None


def _metric_direction(old: Commitment, new: Commitment) -> str | None:
    text = normalize_text(f"{old.metric or ''} {old.policy_statement or ''} {new.metric or ''} {new.policy_statement or ''}")
    if re.search(r"\b(reduc|decreas|lower|less|cut|decarboni|drop|shrink)\w*\b", text):
        return "REDUCTION"
    if re.search(r"\b(increas|rais|higher|more|expand|grow|improv|boost|uplift)\w*\b", text):
        return "INCREASE"
    if re.search(r"\b(at least|minimum|min)\b", text):
        return "INCREASE"
    return None


def _target_comparison(old: Commitment, new: Commitment) -> tuple[str, str, float] | None:
    a, b = _target_number(old.target), _target_number(new.target)
    if a is None or b is None or a == b:
        return None
    direction = _metric_direction(old, new)
    if direction == "REDUCTION":
        stronger = b > a
    elif direction == "INCREASE":
        stronger = b > a
    else:
        return None
    return (
        "STRENGTHENED" if stronger else "WEAKENED",
        f"The target changed from {old.target} to {new.target}; for this metric, {('a larger' if direction == 'REDUCTION' else 'a larger')} target represents greater ambition.",
        0.94,
    )


def _scope_signal(old: str | None, new: str | None) -> int:
    a, b = _tokens(old or ""), _tokens(new or "")
    if not a or not b:
        return 0
    # Added scope concepts are a strengthening signal; removed concepts weaken.
    added, removed = b - a, a - b
    if added and not removed:
        return 1
    if removed and not added:
        return -1
    return 0


def _mandatory_signal(text: str | None) -> int:
    t = normalize_text(text)
    strong = bool(re.search(r"\b(shall|required|must|mandatory|will)\b", t))
    weak = bool(re.search(r"\b(aim|seek|aspire|may|where feasible|voluntary)\b", t))
    return int(strong) - int(weak)


def _build_result(classification: str, reason: str, fields: list[str], confidence: float) -> dict:
    return {"classification": classification, "reason": reason, "changed_fields": fields, "confidence": confidence}


def classify_deterministically(old: Commitment, new: Commitment) -> dict | None:
    fields = changed_fields(old, new)
    if not fields:
        return _build_result("UNCHANGED", "No meaningful change in the compared fields.", [], 0.99)

    target_result = _target_comparison(old, new) if "target" in fields or "policy_statement" in fields or "metric" in fields else None
    if target_result:
        return _build_result(target_result[0], target_result[1], fields, target_result[2])

    if "deadline" in fields:
        a, b = _first_year(old.deadline), _first_year(new.deadline)
        if a is not None and b is not None and a != b:
            cls = "STRENGTHENED" if b < a else "WEAKENED"
            return _build_result(cls, f"The target deadline moved from {old.deadline} to {new.deadline}.", fields, 0.94)

    if "scope" in fields:
        signal = _scope_signal(old.scope, new.scope)
        if signal:
            cls = "STRENGTHENED" if signal > 0 else "WEAKENED"
            return _build_result(cls, f"The target scope changed from '{old.scope}' to '{new.scope}'.", fields, 0.82)

    if "policy_statement" in fields:
        hours_old, hours_new = HOURS_RE.search(old.policy_statement or ""), HOURS_RE.search(new.policy_statement or "")
        if hours_old and hours_new and float(hours_old.group(1)) != float(hours_new.group(1)):
            stronger = float(hours_new.group(1)) > float(hours_old.group(1))
            return _build_result(
                "STRENGTHENED" if stronger else "WEAKENED",
                f"The training requirement changed from {hours_old.group(1)} hours to {hours_new.group(1)} hours.",
                fields, 0.92,
            )

    if "policy_statement" in fields:
        a, b = _freq_rank(old.policy_statement), _freq_rank(new.policy_statement)
        if a is not None or b is not None:
            if a is None and b is not None:
                return _build_result("STRENGTHENED", "The new policy statement adds an explicit monitoring frequency.", fields, 0.86)
            if a is not None and b is None:
                return _build_result("WEAKENED", "The new policy statement removes the previously stated monitoring frequency.", fields, 0.86)
            if a != b:
                cls = "STRENGTHENED" if b > a else "WEAKENED"
                return _build_result(cls, "The policy statement changes the required monitoring frequency.", fields, 0.88)

    if "monitoring_frequency" in fields:
        a, b = _freq_rank(old.monitoring_frequency), _freq_rank(new.monitoring_frequency)
        if a is not None and b is not None and a != b:
            cls = "STRENGTHENED" if b > a else "WEAKENED"
            return _build_result(cls, f"Monitoring frequency changed from {old.monitoring_frequency} to {new.monitoring_frequency}.", fields, 0.90)

    if "policy_statement" in fields:
        a, b = _mandatory_signal(old.policy_statement), _mandatory_signal(new.policy_statement)
        if a != b:
            cls = "STRENGTHENED" if b > a else "WEAKENED"
            return _build_result(cls, "The commitment language changed in its degree of obligation.", fields, 0.78)
        if jaccard(old.policy_statement, new.policy_statement) >= 0.90:
            return _build_result("UNCHANGED", "Wording changed but the commitment meaning is effectively equivalent.", fields, 0.86)

    return None


def _id_equal(old: Commitment, new: Commitment) -> bool:
    return bool(old.commitment_id and new.commitment_id and old.commitment_id.strip().upper() == new.commitment_id.strip().upper())


def match_score(old: Commitment, new: Commitment) -> float:
    if old.category and new.category and normalize_text(old.category) != normalize_text(new.category):
        return 0.0
    statement = jaccard(old.policy_statement, new.policy_statement)
    metric = jaccard(old.metric, new.metric)
    scope = jaccard(old.scope, new.scope)
    baseline = jaccard(old.baseline, new.baseline)
    deadline = 1.0 if (_first_year(old.deadline) and _first_year(old.deadline) == _first_year(new.deadline)) else 0.0
    return 0.35 * statement + 0.30 * metric + 0.15 * scope + 0.10 * baseline + 0.10 * deadline


def match_commitments(old_items: list[Commitment], new_items: list[Commitment]) -> dict:
    matched, used_old, used_new = [], set(), set()
    old_by_id: dict[str, list[int]] = {}
    for i, item in enumerate(old_items):
        if item.commitment_id:
            old_by_id.setdefault(item.commitment_id.strip().upper(), []).append(i)

    # Same ID is accepted only if the underlying topic/metric is not contradictory.
    for ni, new in enumerate(new_items):
        key = new.commitment_id.strip().upper() if new.commitment_id else None
        if not key or key not in old_by_id:
            continue
        candidates = [i for i in old_by_id[key] if i not in used_old]
        if not candidates:
            continue
        oi = max(candidates, key=lambda i: match_score(old_items[i], new))
        old = old_items[oi]
        semantic = match_score(old, new)
        # IDs are strong, but a zero/near-zero semantic score indicates ID reuse.
        statement_similarity = jaccard(old.policy_statement, new.policy_statement)
        metric_similarity = jaccard(old.metric, new.metric)
        target_similarity = jaccard(old.target, new.target)
        score = max(0.82, semantic) if semantic else 0.82
        matched.append((oi, ni, round(min(1.0, score), 2)))
        used_old.add(oi); used_new.add(ni)

    candidates: list[tuple[float, int, int]] = []
    for oi, old in enumerate(old_items):
        if oi in used_old:
            continue
        for ni, new in enumerate(new_items):
            if ni in used_new:
                continue
            if old.commitment_id and new.commitment_id and old.commitment_id.strip().upper() != new.commitment_id.strip().upper():
                continue
            score = match_score(old, new)
            if score >= MATCH_THRESHOLD:
                candidates.append((score, oi, ni))
    candidates.sort(reverse=True)
    for score, oi, ni in candidates:
        if oi not in used_old and ni not in used_new:
            matched.append((oi, ni, score)); used_old.add(oi); used_new.add(ni)
    return {"matched": matched, "unmatched_old": [i for i in range(len(old_items)) if i not in used_old], "unmatched_new": [i for i in range(len(new_items)) if i not in used_new]}


def _commitment_fields(item: Commitment) -> dict:
    return {field: getattr(item, field) for field in COMPARE_FIELDS}


def _build_row(*, classification: str, reason: str, changed: list[str], match_confidence: float, confidence: float, old_item: Commitment | None, new_item: Commitment | None) -> CommitmentComparison:
    return CommitmentComparison(
        old_commitment_id=old_item.commitment_id if old_item else None,
        new_commitment_id=new_item.commitment_id if new_item else None,
        classification=classification,
        reason=reason,
        changed_fields=changed,
        match_confidence=clamp_confidence(match_confidence),
        confidence=clamp_confidence(confidence),
        old_source=old_item.source if old_item else EMPTY_SOURCE,
        new_source=new_item.source if new_item else EMPTY_SOURCE,
    )


def compare_matched_pair(old_item: Commitment, new_item: Commitment, match_confidence: float, llm_comparer: Callable[[dict, dict], dict] | None = None) -> tuple[CommitmentComparison, str | None]:
    result = classify_deterministically(old_item, new_item)
    warning = None
    if result is None:
        if llm_comparer is not None:
            try:
                llm_result = llm_comparer(_commitment_fields(old_item), _commitment_fields(new_item))
                cls = str(llm_result.get("classification", "MODIFIED")).upper()
                if cls == "REDUCED": cls = "WEAKENED"
                if cls not in CLASSIFICATIONS: cls = "MODIFIED"
                result = _build_result(cls, str(llm_result.get("reason") or "Semantic comparison of the structured commitment fields."), llm_result.get("changed_fields") or changed_fields(old_item, new_item), clamp_confidence(llm_result.get("confidence")))
            except Exception as exc:
                result = _build_result("MODIFIED", "The commitment changed, but the available structured fields do not support a defensible stronger/weaker conclusion.", changed_fields(old_item, new_item), 0.45)
                warning = f"LLM comparison skipped: {exc}"
        else:
            result = _build_result("MODIFIED", "The commitment changed, but the available structured fields do not support a defensible stronger/weaker conclusion.", changed_fields(old_item, new_item), 0.45)
            warning = f"Ambiguous change for {old_item.commitment_id or 'commitment'}; recorded as MODIFIED rather than inventing a direction."
    return _build_row(classification=result["classification"], reason=result["reason"], changed=list(result.get("changed_fields") or []), match_confidence=match_confidence, confidence=result.get("confidence", 0.5), old_item=old_item, new_item=new_item), warning


def summarize(rows: list[CommitmentComparison]) -> ComparisonSummary:
    counts = {"strengthened": 0, "weakened": 0, "reduced": 0, "unchanged": 0, "new": 0, "removed": 0, "modified": 0}
    for row in rows:
        cls = row.classification.upper()
        if cls == "STRENGTHENED": counts["strengthened"] += 1
        elif cls == "WEAKENED": counts["weakened"] += 1; counts["reduced"] += 1  # legacy summary alias
        elif cls == "REDUCED": counts["weakened"] += 1; counts["reduced"] += 1  # backward-compatible alias
        elif cls == "UNCHANGED": counts["unchanged"] += 1
        elif cls == "NEW": counts["new"] += 1
        elif cls == "REMOVED": counts["removed"] += 1
        elif cls == "MODIFIED": counts["modified"] += 1
    return ComparisonSummary(**counts)


def compare_policies(old_commitments: list[Commitment], new_commitments: list[Commitment], llm_comparer: Callable[[dict, dict], dict] | None = None) -> tuple[list[CommitmentComparison], list[str]]:
    matching = match_commitments(old_commitments, new_commitments)
    rows, warnings = [], []
    for oi, ni, score in matching["matched"]:
        row, warning = compare_matched_pair(old_commitments[oi], new_commitments[ni], score, llm_comparer)
        rows.append(row)
        if warning: warnings.append(warning)
    for oi in matching["unmatched_old"]:
        item = old_commitments[oi]
        rows.append(_build_row(classification="REMOVED", reason="This commitment exists only in the old policy.", changed=[], match_confidence=1.0, confidence=item.confidence, old_item=item, new_item=None))
    for ni in matching["unmatched_new"]:
        item = new_commitments[ni]
        rows.append(_build_row(classification="NEW", reason="This commitment exists only in the new policy.", changed=[], match_confidence=1.0, confidence=item.confidence, old_item=None, new_item=item))
    rows.sort(key=lambda row: (row.classification, row.new_commitment_id or row.old_commitment_id or ""))
    return rows, warnings
