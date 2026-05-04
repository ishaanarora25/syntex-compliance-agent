"""
Name-consistency check between the application form and the formation document.

The applicant types a company name into the onboarding form. They also upload
formation documents (Articles of Organization, Certificate of Incorporation,
etc.) which carry the official legal name. This service downloads the first
formation-document blob, extracts its text, and compares.

Mismatch detection runs in two layers:

  1. Cheap deterministic similarity over normalized names — catches whitespace,
     punctuation, suffix differences (LLC vs. L.L.C.), and obvious typos.
  2. If similarity is in the ambiguous band, ask Claude to make the call. The
     LLM is allowed to return "consistent" for things like d/b/a, registered
     agent variants, or trade-name vs legal-name patterns that simple string
     similarity would flag.

Returns a NameConsistencyResult tagging the discrepancy severity. Network or
PDF failures fall through to status="no_doc" so the assessment continues.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import List, Optional

import httpx

from app.config import get_settings
from app.models import NameConsistencyResult, WebhookDocument
from app.services import claude_client, pdf_extractor

logger = logging.getLogger(__name__)


_FORMATION_DOC_TYPES = {
    "company_formation_docs",
    "articles_of_organization",
    "certificate_of_incorporation",
    "operating_agreement",
    "limited_partnership_agreement",
}

_ENTITY_SUFFIXES = [
    "limited liability company",
    "incorporated",
    "corporation",
    "limited partnership",
    "limited",
    "company",
    "l.l.c.",
    "llc",
    "inc.",
    "inc",
    "corp.",
    "corp",
    "ltd.",
    "ltd",
    "lp",
    "l.p.",
    "plc",
    "gmbh",
    "ag",
    "sa",
]


def _normalize(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, remove entity suffixes."""
    if not name:
        return ""
    decoded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", decoded).lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # strip a trailing entity-type suffix, longest-first
    for suffix in sorted(_ENTITY_SUFFIXES, key=len, reverse=True):
        if cleaned.endswith(" " + suffix):
            cleaned = cleaned[: -(len(suffix) + 1)].strip()
            break
        if cleaned == suffix:
            cleaned = ""
            break
    return cleaned


def _candidate_names_from_text(text: str) -> List[str]:
    """
    Pull plausible legal-name candidates from extracted formation-doc text.

    Heuristic: lines that mention "name" near a capitalised phrase, or the
    first ALL-CAPS / Title-Cased phrase that ends with an entity suffix.
    """
    candidates: List[str] = []

    if not text:
        return candidates

    # Phase 1 — entity-suffix anchored matches (case-insensitive)
    suffix_pattern = re.compile(
        r"([A-Z][A-Za-z0-9&'\-,. ]{2,80}?(?:LLC|L\.L\.C\.|Inc\.?|Incorporated|Corp\.?|Corporation|"
        r"Ltd\.?|Limited|LP|L\.P\.|PLC|GmbH|AG))",
        re.IGNORECASE,
    )
    for m in suffix_pattern.finditer(text):
        cand = m.group(1).strip(" \t\n,.;:")
        if 4 < len(cand) < 100 and cand not in candidates:
            candidates.append(cand)

    # Phase 2 — "Name of the Company" labels
    label_pattern = re.compile(
        r"(?:Name of (?:the )?(?:Company|LLC|Corporation|Entity|Limited Liability Company)|"
        r"Legal Name|Company Name)\s*[:\-]\s*([A-Z][^\n]{3,80})",
        re.IGNORECASE,
    )
    for m in label_pattern.finditer(text):
        cand = m.group(1).strip(" \t\n,.;:")
        if cand not in candidates:
            candidates.append(cand)

    return candidates[:8]


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _pick_formation_document(documents: List[WebhookDocument]) -> Optional[WebhookDocument]:
    for doc in documents:
        if (doc.type or "").lower() in _FORMATION_DOC_TYPES and doc.blobUrl and doc.status == "uploaded":
            return doc
    return None


async def _download_blob(url: str) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as exc:
        logger.warning("Could not download formation-doc blob %s: %s", url, exc)
        return None


async def check(
    applicant_name: str,
    documents: List[WebhookDocument],
) -> NameConsistencyResult:
    formation_doc = _pick_formation_document(documents)
    if formation_doc is None:
        return NameConsistencyResult(
            status="no_doc",
            applicant_name=applicant_name,
            notes="No formation document supplied — cannot run the name-consistency check.",
            checked_with_llm=False,
        )

    payload = await _download_blob(formation_doc.blobUrl or "")
    if not payload:
        return NameConsistencyResult(
            status="no_doc",
            applicant_name=applicant_name,
            document_filename=formation_doc.fileName,
            notes="Formation document blob could not be downloaded for inspection.",
            checked_with_llm=False,
        )

    try:
        pdf = pdf_extractor.extract(formation_doc.fileName or "formation.pdf", payload)
    except Exception as exc:
        logger.warning("Formation PDF extraction failed: %s", exc)
        return NameConsistencyResult(
            status="no_doc",
            applicant_name=applicant_name,
            document_filename=formation_doc.fileName,
            notes=f"Could not extract text from formation document: {exc}",
            checked_with_llm=False,
        )

    full_text = pdf.full_text
    candidates = _candidate_names_from_text(full_text)

    if not candidates:
        return NameConsistencyResult(
            status="no_doc",
            applicant_name=applicant_name,
            document_filename=formation_doc.fileName,
            notes="Formation document parsed but no entity name could be recovered from the text.",
            checked_with_llm=False,
        )

    norm_applicant = _normalize(applicant_name)

    # Pick the candidate with highest normalised similarity to the applicant.
    scored = sorted(
        ((c, _similarity(norm_applicant, _normalize(c))) for c in candidates),
        key=lambda x: x[1],
        reverse=True,
    )
    best, best_score = scored[0]

    if best_score >= 0.97:
        status = "consistent"
        notes = (
            f"Applicant name '{applicant_name}' matches the formation-document name "
            f"'{best}' (similarity {best_score:.2f})."
        )
        return NameConsistencyResult(
            status=status,
            applicant_name=applicant_name,
            document_name=best,
            document_filename=formation_doc.fileName,
            similarity=round(best_score, 2),
            notes=notes,
            checked_with_llm=False,
        )

    if best_score < 0.55:
        status = "mismatch"
        notes = (
            f"Applicant name '{applicant_name}' does not appear in the uploaded formation "
            f"document. Closest candidate found was '{best}' (similarity {best_score:.2f}). "
            "Confirm with applicant — wrong document or wrong company."
        )
        return NameConsistencyResult(
            status=status,
            applicant_name=applicant_name,
            document_name=best,
            document_filename=formation_doc.fileName,
            similarity=round(best_score, 2),
            notes=notes,
            checked_with_llm=False,
        )

    # Ambiguous band — ask Claude to adjudicate.
    llm_status, llm_notes = await _adjudicate_with_claude(
        applicant_name=applicant_name,
        document_excerpt=full_text[:4000],
        candidates=candidates,
    )
    return NameConsistencyResult(
        status=llm_status,
        applicant_name=applicant_name,
        document_name=best,
        document_filename=formation_doc.fileName,
        similarity=round(best_score, 2),
        notes=llm_notes,
        checked_with_llm=True,
    )


async def _adjudicate_with_claude(
    applicant_name: str,
    document_excerpt: str,
    candidates: List[str],
) -> tuple[str, str]:
    """Ask Claude whether the applicant name and the document name refer to the same entity."""
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        return (
            "minor_variation",
            f"Applicant name '{applicant_name}' partially matches the formation document "
            f"(closest candidate: '{candidates[0]}'). Manual review recommended.",
        )

    system_prompt = (
        "You are a BSA/AML analyst comparing a company name on an application form against "
        "the company name in an uploaded formation document. Output a JSON object with two "
        'keys: "verdict" (one of "consistent", "minor_variation", "mismatch") and "notes" '
        "(one short sentence explaining the verdict). 'consistent' means the same legal entity "
        "(allowing for d/b/a, suffix punctuation, or trade-name patterns). 'minor_variation' "
        "means the same entity with a small spelling or punctuation slip the banker should "
        "still reconcile. 'mismatch' means a different entity. Reply with ONLY the JSON object."
    )

    user_message = (
        f"Applicant-supplied name: {applicant_name}\n\n"
        f"Candidate names recovered from the formation document:\n"
        + "\n".join(f"- {c}" for c in candidates)
        + f"\n\nFormation-document excerpt (truncated):\n{document_excerpt}"
    )

    try:
        response = await claude_client.messages_create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:
        logger.warning("Name-consistency LLM call failed: %s", exc)
        return (
            "minor_variation",
            f"LLM adjudication unavailable; applicant name '{applicant_name}' partially matches "
            f"document candidate '{candidates[0]}'. Manual review recommended.",
        )

    text = "".join(block.text for block in response.content if block.type == "text")
    verdict, notes = _parse_llm_verdict(text)
    return verdict, notes


def _parse_llm_verdict(text: str) -> tuple[str, str]:
    import json as _json
    try:
        # Strip markdown fences if any
        cleaned = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
        obj = _json.loads(cleaned)
        verdict = str(obj.get("verdict", "minor_variation")).lower().strip()
        if verdict not in {"consistent", "minor_variation", "mismatch"}:
            verdict = "minor_variation"
        notes = str(obj.get("notes", "")).strip() or "LLM adjudicated the name comparison."
        return verdict, notes
    except Exception:
        # Best-effort textual fallback
        lowered = text.lower()
        if "mismatch" in lowered:
            return "mismatch", text.strip()[:300]
        if "consistent" in lowered:
            return "consistent", text.strip()[:300]
        return "minor_variation", text.strip()[:300] or "LLM verdict could not be parsed."
