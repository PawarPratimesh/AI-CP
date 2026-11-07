"""Page-aware chunking, commitment normalization, and deduplication."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from schemas import Commitment, SourceEvidence

logger = logging.getLogger(__name__)

# ~2k tokens. 
MAX_CHUNK_CHARS = 7000
OVERLAP_CHARS = 500
MIN_STATEMENT_CHARS = 20

OPTIONAL_FIELDS = (
    "commitment_id",
    "category",
    "policy_statement",
    "metric",
    "baseline",
    "target",
    "deadline",
    "responsible_owner",
    "scope",
    "evidence_requirement",
    "monitoring_frequency",
    "escalation",
)

HEADER_FOOTER_PATTERNS = (
    re.compile(r"^page\s+\d+(\s+of\s+\d+)?$", re.IGNORECASE),
    re.compile(r"^table of contents$", re.IGNORECASE),
    re.compile(r"^contents$", re.IGNORECASE),
)

STRUCTURED_SPLIT = re.compile(r"(?=COMMITMENT ID\s*:)", re.IGNORECASE)
LABEL_PATTERN = re.compile(
    r"(COMMITMENT ID|CATEGORY|POLICY STATEMENT|METRIC|BASELINE|TARGET|DEADLINE|"
    r"RESPONSIBLE OWNER|SCOPE|EVIDENCE REQUIREMENT|MONITORING FREQUENCY|ESCALATION)\s*:",
    re.IGNORECASE,
)
LABEL_TO_FIELD = {
    "COMMITMENT ID": "commitment_id",
    "CATEGORY": "category",
    "POLICY STATEMENT": "policy_statement",
    "METRIC": "metric",
    "BASELINE": "baseline",
    "TARGET": "target",
    "DEADLINE": "deadline",
    "RESPONSIBLE OWNER": "responsible_owner",
    "SCOPE": "scope",
    "EVIDENCE REQUIREMENT": "evidence_requirement",
    "MONITORING FREQUENCY": "monitoring_frequency",
    "ESCALATION": "escalation",
}
FOOTER_LINE_PATTERNS = (
    re.compile(r"^APEX INDUSTRIAL TECHNOLOGIES LTD", re.IGNORECASE),
    re.compile(r"^Environmental, Social & Governance Policy", re.IGNORECASE),
    re.compile(r"^ESG-POL-", re.IGNORECASE),
    re.compile(r"^Synthetic Demonstration Document", re.IGNORECASE),
    re.compile(r"^Page\s+\d+\s+of\s+\d+", re.IGNORECASE),
)
SECTION_HEADING_LINE = re.compile(
    r"^\d+(\.\d+)*\s+.+\bCommitments\b",
    re.IGNORECASE,
)
TRAILING_SECTION_HEADING = re.compile(
    r"\s+\d+(\.\d+)*\s+\S.*\bCommitments\b.*$",
    re.IGNORECASE,
)


class CommitmentExtractionError(Exception):
    """Raised when commitments cannot be extracted from document text."""


def create_chunks(pages: list[dict]) -> list[dict]:
    """Split extracted pages into deterministic page-aware chunks.

    Each page is usually one chunk. Oversized pages are split by character
    windows. A short overlap from the previous page is prepended so a
    commitment is less likely to be separated from its fields.
    """
    chunks: list[dict] = []
    previous_text = ""
    previous_page: int | None = None

    for page in pages:
        page_number = page["page_number"]
        text = (page.get("extracted_text") or "").strip()
        if not text:
            continue

        overlap_text = ""
        overlap_pages: list[int] = []
        if previous_text and OVERLAP_CHARS > 0:
            overlap_text = previous_text[-OVERLAP_CHARS:].strip()
            if overlap_text and previous_page is not None:
                overlap_pages = [previous_page]

        pieces = _split_text(text)
        for index, piece in enumerate(pieces):
            chunk_text = piece
            page_numbers = [page_number]
            if index == 0 and overlap_text:
                chunk_text = overlap_text + "\n\n" + piece
                page_numbers = overlap_pages + [page_number]
            chunks.append(
                {
                    "page_numbers": page_numbers,
                    "text": chunk_text,
                }
            )

        previous_text = text
        previous_page = page_number

    return chunks


def _split_text(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + MAX_CHUNK_CHARS, len(text))
        pieces.append(text[start:end])
        if end >= len(text):
            break
        start = end - OVERLAP_CHARS
        if start < 0:
            start = 0
        if start >= end:
            start = end
    return pieces


def empty_to_null(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"null", "none", "n/a", "na", "not specified"}:
        return None
    return text


def clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


def normalize_page_numbers(raw_pages: object, fallback: list[int]) -> list[int]:
    numbers: list[int] = []
    if isinstance(raw_pages, list):
        for item in raw_pages:
            try:
                numbers.append(int(item))
            except (TypeError, ValueError):
                continue
    if not numbers:
        numbers = list(fallback)
    # Keep order, drop duplicates.
    seen: set[int] = set()
    ordered: list[int] = []
    for page in numbers:
        if page not in seen:
            seen.add(page)
            ordered.append(page)
    return ordered


def looks_like_header_or_footer(statement: str | None) -> bool:
    if not statement:
        return True
    compact = re.sub(r"\s+", " ", statement).strip()
    if len(compact) < MIN_STATEMENT_CHARS:
        return True
    if any(pattern.match(compact) for pattern in HEADER_FOOTER_PATTERNS):
        return True
    if re.fullmatch(r"(page\s+)?\d+(\s*/\s*\d+)?", compact, flags=re.IGNORECASE):
        return True
    return False


def normalize_commitment(raw: dict, fallback_pages: list[int]) -> Commitment | None:
    """Turn one LLM object into a Commitment, or None if it should be dropped."""
    if not isinstance(raw, dict):
        return None

    fields = {name: empty_to_null(raw.get(name)) for name in OPTIONAL_FIELDS}
    if not fields["commitment_id"] and looks_like_header_or_footer(fields["policy_statement"]):
        return None

    source_raw = raw.get("source") or {}
    if not isinstance(source_raw, dict):
        source_raw = {}

    page_numbers = normalize_page_numbers(source_raw.get("page_numbers"), fallback_pages)
    evidence = empty_to_null(source_raw.get("evidence")) or (fields["policy_statement"] or "")
    if not page_numbers:
        return None

    return Commitment(
        **fields,
        source=SourceEvidence(page_numbers=page_numbers, evidence=evidence),
        confidence=clamp_confidence(raw.get("confidence")),
    )


def _normalized_statement(statement: str | None) -> str:
    if not statement:
        return ""
    return re.sub(r"\s+", " ", statement).strip().lower()


def deduplicate_commitments(commitments: list[Commitment]) -> tuple[list[Commitment], int]:
    """Remove duplicate commitments. Keep first occurrence and merge page numbers."""
    unique: list[Commitment] = []
    index_by_id: dict[str, int] = {}
    index_by_statement: dict[str, int] = {}
    duplicates_removed = 0

    for item in commitments:
        existing_index = None
        if item.commitment_id:
            existing_index = index_by_id.get(item.commitment_id.strip().upper())
        if existing_index is None:
            key = _normalized_statement(item.policy_statement)
            if key:
                existing_index = index_by_statement.get(key)

        if existing_index is None:
            unique.append(item)
            new_index = len(unique) - 1
            if item.commitment_id:
                index_by_id[item.commitment_id.strip().upper()] = new_index
            statement_key = _normalized_statement(item.policy_statement)
            if statement_key:
                index_by_statement[statement_key] = new_index
            continue

        duplicates_removed += 1
        existing = unique[existing_index]
        merged_pages = normalize_page_numbers(
            existing.source.page_numbers + item.source.page_numbers,
            existing.source.page_numbers,
        )
        unique[existing_index] = existing.model_copy(
            update={
                "source": SourceEvidence(
                    page_numbers=merged_pages,
                    evidence=existing.source.evidence or item.source.evidence,
                )
            }
        )

    return unique, duplicates_removed


def _is_footer_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if SECTION_HEADING_LINE.search(stripped):
        return True
    return any(pattern.search(stripped) for pattern in FOOTER_LINE_PATTERNS)


def _clean_field_value(value: str) -> str | None:
    lines = [line.strip() for line in value.splitlines() if line.strip() and not _is_footer_line(line)]
    cleaned = re.sub(r"\s+", " ", " ".join(lines)).strip()
    cleaned = TRAILING_SECTION_HEADING.sub("", cleaned).strip()
    return empty_to_null(cleaned)


def parse_structured_commitments(text: str, page_numbers: list[int]) -> list[dict]:
    """Extract labeled COMMITMENT ID records from page text. No LLM, no invented values."""
    if not text or not re.search(r"COMMITMENT ID\s*:", text, re.IGNORECASE):
        return []

    commitments: list[dict] = []
    for block in STRUCTURED_SPLIT.split(text):
        if not re.search(r"COMMITMENT ID\s*:", block, re.IGNORECASE):
            continue
        matches = list(LABEL_PATTERN.finditer(block))
        if not matches:
            continue

        fields = {name: None for name in OPTIONAL_FIELDS}
        for index, match in enumerate(matches):
            label = re.sub(r"\s+", " ", match.group(1)).upper()
            field_name = LABEL_TO_FIELD.get(label)
            if not field_name:
                continue
            end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
            fields[field_name] = _clean_field_value(block[match.end() : end])

        if not fields["commitment_id"] and not fields["policy_statement"]:
            continue

        evidence_parts = [part for part in (fields["commitment_id"], fields["policy_statement"]) if part]
        commitments.append(
            {
                **fields,
                "source": {
                    "page_numbers": list(page_numbers),
                    "evidence": " ".join(evidence_parts)[:400],
                },
                "confidence": 0.99,
            }
        )
    return commitments


REGISTER_LINE = re.compile(
    r"^(?P<id>(?:ENV|SOC|GOV)-\d{3})\b\s*(?:[—-]\s*)?(?P<title>.*)$",
    re.IGNORECASE,
)


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().lower()


def _extract_monitoring_frequency(statement: str | None) -> str | None:
    if not statement:
        return None
    text = _normalize_text(statement)
    phrases = [
        ("quarterly", "Quarterly"),
        ("every three months", "Quarterly"),
        ("every 3 months", "Quarterly"),
        ("at least quarterly", "Quarterly"),
        ("twice each year", "Twice each year"),
        ("twice yearly", "Twice each year"),
        ("twice per year", "Twice each year"),
        ("at least twice each year", "Twice each year"),
        ("every six months", "Every 6 months"),
        ("every 6 months", "Every 6 months"),
        ("at least once every six months", "Every 6 months"),
        ("at least once every year", "Annual"),
        ("at least once each year", "Annual"),
        ("annually", "Annual"),
        ("annual", "Annual"),
        ("yearly", "Annual"),
        ("once each year", "Annual"),
        ("monthly", "Monthly"),
        ("periodically", "Periodic"),
    ]
    for phrase, label in phrases:
        if phrase in text:
            return label
    return None


def parse_commitment_register(text: str, page_numbers: list[int]) -> list[dict]:
    """Parse the compact ID/title register rows used in the demo PDFs."""
    if not text:
        return []

    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
    items: list[dict] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        match = REGISTER_LINE.match(line)
        if not match:
            i += 1
            continue

        commitment_id = match.group("id").upper()
        title = (match.group("title") or "").strip()
        responsible_owner: str | None = None
        statement_lines: list[str] = []
        j = i + 1

        while j < len(lines):
            next_line = lines[j]
            if re.match(r"^(?:ENV|SOC|GOV)-\d{3}\b", next_line, re.I):
                break

            owner_match = re.match(r"^Accountable Owner\s*:\s*(.+)$", next_line, re.I)
            if owner_match:
                responsible_owner = owner_match.group(1).strip()
                j += 1
                break

            if (
                len(next_line) < 5
                or next_line.lower() in {"environmental commitments", "social commitments", "governance commitments"}
                or re.match(r"^apex industrial systems\s*\|", next_line, re.I)
                or re.match(r"^page\s+\d+", next_line, re.I)
            ):
                j += 1
                continue

            statement_lines.append(next_line)
            j += 1

        statement = " ".join(statement_lines).strip()
        if not statement and title and len(title) >= 5:
            statement = title

        if not statement or len(statement) < 5:
            i += 1
            continue

        category = {"ENV": "Environmental", "SOC": "Social", "GOV": "Governance"}[commitment_id[:3]]
        statement_text = re.sub(r"\s+", " ", statement).strip()

        target_match = re.search(
            r"(\d+(?:\.\d+)?\s*(?:%|hours?)(?:\s+.*?(?:by\s+20\d{2}|from\s+the\s+20\d{2}\s+baseline|by\s+31\s+December\s+20\d{2}))?)",
            statement_text,
            re.I,
        )
        if not target_match:
            target_match = re.search(r"(\d+(?:\.\d+)?\s*(?:%|hours?))", statement_text, re.I)
        deadline_match = re.search(
            r"\b(?:31\s+)?(?:December|January|February|March|April|May|June|July|August|September|October|November)\s+20\d{2}\b",
            statement_text,
            re.I,
        )

        target = target_match.group(1).strip() if target_match else None
        deadline = deadline_match.group(0).strip() if deadline_match else None
        monitoring_frequency = _extract_monitoring_frequency(statement_text)

        items.append({
            "commitment_id": commitment_id,
            "category": category,
            "policy_statement": statement_text,
            "metric": None,
            "baseline": None,
            "target": target,
            "deadline": deadline,
            "responsible_owner": responsible_owner,
            "scope": None,
            "evidence_requirement": None,
            "monitoring_frequency": monitoring_frequency,
            "escalation": None,
            "source": {"page_numbers": list(page_numbers), "evidence": f"{commitment_id} {statement_text}"[:400]},
            "confidence": 0.93,
        })
        i = j

    return items

def extract_commitments(
    pages: list[dict],
    chunk_extractor: Callable[[dict], list[dict]] | None = None,
) -> tuple[list[Commitment], list[str]]:
    """Extract commitments from page text, then normalize and deduplicate.

    Structured COMMITMENT ID records and compact commitment-register rows are parsed locally (free, exact).
    The LLM is used only when no structured records are found.
    """
    usable_pages = [page for page in pages if (page.get("extracted_text") or "").strip()]
    if not usable_pages:
        raise CommitmentExtractionError("The extracted document contains no usable text.")

    logger.info("Pages extracted: %s", len(pages))

    raw_items: list[tuple[dict, list[int]]] = []
    warnings: list[str] = []

    for page in usable_pages:
        page_numbers = [page["page_number"]]
        page_text = page.get("extracted_text") or ""
        structured = parse_structured_commitments(page_text, page_numbers)
        if structured:
            for item in structured:
                raw_items.append((item, page_numbers))
        else:
            for item in parse_commitment_register(page_text, page_numbers):
                raw_items.append((item, page_numbers))

    logger.info("Structured commitments extracted: %s", len(raw_items))

    if not raw_items:
        if chunk_extractor is None:
            raise CommitmentExtractionError(
                "No structured COMMITMENT ID records were found, and no LLM extractor is configured."
            )
        chunks = create_chunks(usable_pages)
        logger.info("Chunks processed: %s", len(chunks))
        for index, chunk in enumerate(chunks, start=1):
            try:
                extracted = chunk_extractor(chunk)
            except Exception:
                logger.exception(
                    "LLM extraction failed for chunk %s (pages %s)",
                    index,
                    chunk["page_numbers"],
                )
                raise
            if not extracted:
                continue
            for item in extracted:
                raw_items.append((item, chunk["page_numbers"]))

    logger.info("Raw commitments extracted: %s", len(raw_items))

    normalized: list[Commitment] = []
    for item, fallback_pages in raw_items:
        commitment = normalize_commitment(item, fallback_pages)
        if commitment is not None:
            normalized.append(commitment)

    unique, duplicates_removed = deduplicate_commitments(normalized)
    logger.info("Duplicates removed: %s", duplicates_removed)
    logger.info("Final commitment count: %s", len(unique))

    if duplicates_removed:
        warnings.append(f"Removed {duplicates_removed} duplicate commitment(s).")

    return unique, warnings
