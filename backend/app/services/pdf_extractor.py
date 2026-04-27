"""
Thin wrapper around pypdf that returns page-by-page text extraction results.

The BSA copilot treats PDFs as the primary input. We deliberately keep this
module free of AI / heuristics — downstream services (document_intelligence.py,
cdd_requirements.py) operate on the plain-text output.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import List

from pypdf import PdfReader

from app.exceptions import EDDServiceError

logger = logging.getLogger(__name__)


class PDFExtractionError(EDDServiceError):
    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(
            detail="pdf_extraction_error",
            message=f"Could not extract text from {filename}: {reason}",
            status_code=400,
        )


@dataclass(frozen=True)
class ExtractedPage:
    page: int
    text: str


@dataclass(frozen=True)
class ExtractedPDF:
    filename: str
    size_bytes: int
    pages: List[ExtractedPage]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)


def extract(filename: str, payload: bytes) -> ExtractedPDF:
    """Extract text from every page of the PDF. Empty pages return empty strings."""
    try:
        reader = PdfReader(BytesIO(payload))
    except Exception as exc:  # pypdf raises a variety — normalise to our error
        raise PDFExtractionError(filename, str(exc)) from exc

    pages: List[ExtractedPage] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("PDF page extraction failed on %s p.%d: %s", filename, idx, exc)
            text = ""
        pages.append(ExtractedPage(page=idx, text=text.strip()))

    if not pages:
        raise PDFExtractionError(filename, "PDF has no pages")

    return ExtractedPDF(filename=filename, size_bytes=len(payload), pages=pages)
