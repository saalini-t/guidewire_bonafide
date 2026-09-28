"""Text extraction (PDF) and structured findings (regex only, no LLM) for
real-file documents. Every findings field is either a genuine regex match or
None — never inferred or guessed, so there is no hallucination risk here.

OCR fallback (for scanned/image-only PDFs with no embedded text layer) is
optional: it requires the `pytesseract` pip package AND the separate
Tesseract OCR binary (not pip-installable) — see README/setup notes. Neither
is a hard dependency of this app; if either is missing, ocr_pdf_text()
degrades gracefully to "" and the caller marks the document FAILED for
manual review, exactly as if OCR didn't exist.
"""
import re

MIN_EXTRACTABLE_TEXT_CHARS = 20

_COST_RE = re.compile(r"\$\s?[\d,]+(?:\.\d{2})?")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}"
    r"|(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)


def extract_pdf_text(content: bytes) -> str:
    """Returns extracted text, or "" if the PDF has no embedded text layer
    (e.g. a scanned image) or can't be parsed at all (corrupt/malformed
    file) — never raises; the caller treats "" the same as "no text found"
    and marks the document FAILED for manual review.
    """
    import fitz  # PyMuPDF

    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc).strip()
    except Exception:
        return ""


def ocr_pdf_text(content: bytes, *, max_pages: int = 10) -> str:
    """Best-effort OCR for a PDF with no embedded text layer. Returns "" —
    never raises — if pytesseract/Pillow aren't installed, the Tesseract
    binary isn't on PATH, or OCR otherwise fails. `max_pages` bounds the
    work for a large scanned document (OCR is comparatively slow per page).
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""

    import io

    import fitz  # PyMuPDF

    try:
        texts = []
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page in doc[:max_pages]:
                pixmap = page.get_pixmap(dpi=200)
                image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                texts.append(pytesseract.image_to_string(image))
        return "\n".join(texts).strip()
    except Exception:
        # Covers pytesseract.TesseractNotFoundError (binary not on PATH)
        # and any other OCR/render failure — OCR is a best-effort fallback,
        # never a reason to fail the whole upload.
        return ""


def extract_findings(text: str) -> dict:
    """Best-effort structured findings. Not AI — plain regex over the
    document text, so a field is either a real match or explicitly null.
    """
    costs = _COST_RE.findall(text)
    dates = _DATE_RE.findall(text)
    return {
        "estimated_repair_cost": costs[-1] if costs else None,
        "incident_date": dates[0] if dates else None,
    }


if __name__ == "__main__":
    sample = "Repair estimate dated March 3, 2026 totals $4,521.50 for parts and labor."
    findings = extract_findings(sample)
    assert findings["estimated_repair_cost"] == "$4,521.50"
    assert findings["incident_date"] == "March 3, 2026"
    assert extract_findings("no relevant figures here") == {"estimated_repair_cost": None, "incident_date": None}
    assert ocr_pdf_text(b"not a real pdf") == ""  # graceful no-crash regardless of whether OCR deps are installed
    print("ok")
