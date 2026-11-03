import io
import logging
from typing import Tuple

import pymupdf  # PyMuPDF modern API

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".txt"}


class ResumeParsingError(Exception):
    """Raised when resume extraction fails due to format, corruption, or missing text."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_file_metadata(filename: str, file_size: int) -> str:
    """Validate filename extension and file size. Returns normalized extension."""
    if not filename:
        raise ResumeParsingError("Filename must not be empty.")

    lower_filename = filename.lower()
    ext = None
    for allowed in ALLOWED_EXTENSIONS:
        if lower_filename.endswith(allowed):
            ext = allowed
            break

    if not ext:
        raise ResumeParsingError(
            f"Unsupported file format '{filename}'. Only PDF and TXT files are accepted."
        )

    if file_size <= 0:
        raise ResumeParsingError("The uploaded file is empty (0 bytes).")

    if file_size > MAX_FILE_SIZE_BYTES:
        raise ResumeParsingError(
            f"File size exceeds the 10 MB limit ({file_size / (1024 * 1024):.2f} MB)."
        )

    return ext


def extract_text_from_pdf(content: bytes) -> str:
    """Extract clean text content from PDF binary bytes using PyMuPDF."""
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        logger.warning("Corrupted or unreadable PDF: %s", exc)
        raise ResumeParsingError(
            "The PDF file is corrupted, encrypted, or cannot be opened."
        ) from exc

    try:
        if doc.is_encrypted:
            raise ResumeParsingError(
                "Password-protected PDF files cannot be processed. Please upload an unprotected document."
            )

        if doc.page_count == 0:
            raise ResumeParsingError("The PDF contains no pages.")

        text_parts: list[str] = []
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            if page_text and page_text.strip():
                text_parts.append(page_text.strip())

        extracted = "\n\n".join(text_parts).strip()
        if not extracted:
            raise ResumeParsingError(
                "No readable text found in the PDF. Image-only or scanned PDFs without OCR are not supported."
            )
        return extracted
    finally:
        doc.close()


def extract_text_from_txt(content: bytes) -> str:
    """Extract clean text content from raw TXT bytes with robust encoding fallbacks."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            decoded = content.decode(encoding).strip()
            if decoded:
                return decoded
        except UnicodeDecodeError:
            continue

    decoded = content.decode("utf-8", errors="replace").strip()
    if not decoded:
        raise ResumeParsingError("The text file is empty or contains no readable characters.")
    return decoded


def parse_resume_file(filename: str, content: bytes) -> Tuple[str, str]:
    """
    Validate and extract textual content from uploaded file bytes.
    Returns:
        Tuple of (clean_text, normalized_extension)
    """
    ext = validate_file_metadata(filename, len(content))

    if ext == ".pdf":
        text = extract_text_from_pdf(content)
    elif ext == ".txt":
        text = extract_text_from_txt(content)
    else:
        raise ResumeParsingError(f"Unsupported extension {ext}")

    if len(text.strip()) < 30:
        raise ResumeParsingError(
            "The extracted resume text is too brief to form a meaningful candidate profile."
        )

    logger.info("Successfully extracted %d characters from %s", len(text), filename)
    return text, ext
