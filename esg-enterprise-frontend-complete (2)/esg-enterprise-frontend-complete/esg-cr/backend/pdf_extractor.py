"""Extract and lightly clean text from PDF files, page by page."""

from __future__ import annotations

import re
from pathlib import Path

import fitz


MIN_USEFUL_CHARS = 40


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be processed."""


def clean_text(raw_text: str) -> str:
    """Remove extra spaces and collapse repeated blank lines. Do not rewrite meaning."""
    if not raw_text:
        return ""

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.splitlines()]
    cleaned_lines: list[str] = []
    previous_blank = False

    for line in lines:
        is_blank = line == ""
        if is_blank and previous_blank:
            continue
        cleaned_lines.append(line)
        previous_blank = is_blank

    return "\n".join(cleaned_lines).strip()


def extract_pdf(pdf_path: str | Path) -> dict:
    """Open a PDF and extract cleaned text for each page.

    Returns a dict with page_count, pages, and warnings.
    Raises PDFExtractionError for empty, corrupted, or image-only PDFs.
    """
    pdf_path = Path(pdf_path)

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:
        raise PDFExtractionError("The PDF file is corrupted or could not be opened.") from exc

    try:
        if document.is_encrypted and not document.authenticate(""):
            raise PDFExtractionError("The PDF is encrypted and cannot be opened.")

        page_count = document.page_count
        if page_count == 0:
            raise PDFExtractionError("The PDF is empty and contains no pages.")

        pages: list[dict] = []
        warnings: list[str] = []
        total_characters = 0

        for index in range(page_count):
            page = document.load_page(index)
            extracted_text = clean_text(page.get_text("text") or "")
            character_count = len(extracted_text)
            total_characters += character_count
            page_number = index + 1

            pages.append(
                {
                    "page_number": page_number,
                    "extracted_text": extracted_text,
                    "character_count": character_count,
                }
            )

            if character_count == 0:
                warnings.append(f"No text was extracted from page {page_number}.")
            elif character_count < MIN_USEFUL_CHARS:
                warnings.append(
                    f"Very little text was extracted from page {page_number} "
                    f"({character_count} characters)."
                )

        if total_characters == 0:
            raise PDFExtractionError(
                "This PDF appears to be scanned or image-only. OCR is required to extract text."
            )

        return {
            "page_count": page_count,
            "pages": pages,
            "warnings": warnings,
        }
    finally:
        document.close()
