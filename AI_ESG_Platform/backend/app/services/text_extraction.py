try:
    import fitz  # PyMuPDF (also importable as pymupdf)
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False


def extract_text_from_pdf(file_path):
    if not _FITZ_AVAILABLE:
        raise RuntimeError(
            "PyMuPDF is not installed. Run: pip install pymupdf"
        )

    document = fitz.open(file_path)

    pages = []

    for page_number, page in enumerate(document, start=1):
        text = page.get_text()

        pages.append({
            "page": page_number,
            "text": text
        })

    document.close()

    return pages