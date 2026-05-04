"""
Document intelligence agent — turns a corpus of extracted PDF text into a
structured ownership graph (entities + edges) that the downstream UBO resolver
can consume.

Two layers:

1. Heuristic classifier — fast, deterministic doc-type guess from filename
   and page-1 keywords. Catches the common cases without an LLM round-trip.
2. Claude extractor — a single tool_use call that takes the entire document
   corpus for a case and returns a normalised entity/edge schema. The tool
   schema mirrors the backend's FixtureEntity / FixtureEdge shapes so it
   can feed straight into UBO resolution.

The classifier output is advisory — it feeds into the CDD checklist and
the Claude prompt, but the LLM is the authoritative source of truth for
ownership percentages.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from anthropic import APIError

from app.config import get_settings
from app.exceptions import ClaudeAPIError
from app.models import ExtractedEdge, ExtractedEntityRef, UploadedDocumentMeta
from app.services.claude_client import messages_create
from app.services.pdf_extractor import ExtractedPDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristic classifier
# ---------------------------------------------------------------------------

_DOC_TYPES = [
    "articles_of_organization",
    "operating_agreement",
    "trust_agreement",
    "limited_partnership_agreement",
    "commercial_register_extract",
    "certificate_of_incorporation",
    "adverse_media_report",
    "identity_document",
    "other",
]

_HEURISTIC_PATTERNS: Dict[str, List[re.Pattern]] = {
    "articles_of_organization": [
        re.compile(r"certificate of formation", re.IGNORECASE),
        re.compile(r"articles? of organization", re.IGNORECASE),
    ],
    "operating_agreement": [
        re.compile(r"operating agreement", re.IGNORECASE),
    ],
    "trust_agreement": [
        re.compile(r"trust agreement", re.IGNORECASE),
        re.compile(r"\brevocable (?:living )?trust", re.IGNORECASE),
        re.compile(r"\birrevocable trust", re.IGNORECASE),
    ],
    "limited_partnership_agreement": [
        re.compile(r"limited partnership agreement", re.IGNORECASE),
        re.compile(r"limited partnership\b", re.IGNORECASE),
    ],
    "commercial_register_extract": [
        re.compile(r"handelsregister", re.IGNORECASE),
        re.compile(r"commercial register", re.IGNORECASE),
    ],
    "certificate_of_incorporation": [
        re.compile(r"certificate of incorporation", re.IGNORECASE),
    ],
    "adverse_media_report": [
        re.compile(r"adverse media", re.IGNORECASE),
    ],
    "identity_document": [
        re.compile(r"passport", re.IGNORECASE),
        re.compile(r"driver'?s? licen[cs]e", re.IGNORECASE),
        re.compile(r"national identity card", re.IGNORECASE),
    ],
}


@dataclass
class ClassificationHint:
    doc_type: str
    confidence: float
    label: str
    source: str  # "heuristic" | "claude"


def _derive_label(pdf: ExtractedPDF, doc_type: str) -> str:
    """Pull a likely title from the first non-empty line of page 1."""
    first_page = pdf.pages[0].text if pdf.pages else ""
    for line in first_page.splitlines():
        stripped = line.strip()
        if len(stripped) > 8 and len(stripped) < 140 and not stripped.lower().startswith("page "):
            return stripped.title()[:140]
    pretty_type = doc_type.replace("_", " ").title()
    return f"{pretty_type} ({pdf.filename})"


def classify_heuristic(pdf: ExtractedPDF) -> ClassificationHint:
    """
    Score every doc_type by summing weighted pattern hits. Weight matches in the
    filename and title area (first ~400 chars of page 1) much higher than matches
    buried deep in the body — an operating agreement that cites the underlying
    articles of organization shouldn't get mis-labelled as the articles.
    """
    page1 = pdf.pages[0].text if pdf.pages else ""
    title_area = page1[:400]
    body = page1[400:]
    # Normalise the filename so "foo_operating_agreement.pdf" matches the
    # "operating agreement" phrase pattern.
    filename = pdf.filename.replace("_", " ").replace("-", " ")

    scores: Dict[str, float] = {}
    for doc_type, patterns in _HEURISTIC_PATTERNS.items():
        score = 0.0
        for pattern in patterns:
            if pattern.search(filename):
                score += 5.0
            if pattern.search(title_area):
                score += 3.0
            if pattern.search(body):
                score += 0.5
        if score > 0:
            scores[doc_type] = score

    if not scores:
        return ClassificationHint(
            doc_type="other",
            confidence=0.2,
            label=_derive_label(pdf, "other"),
            source="heuristic",
        )

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    runner_up = max((s for t, s in scores.items() if t != best_type), default=0.0)
    # Confidence scales with margin between top and next-best.
    margin = best_score - runner_up
    if best_score >= 5.0 and margin >= 3.0:
        confidence = 0.92
    elif best_score >= 3.0 and margin >= 1.5:
        confidence = 0.82
    else:
        confidence = 0.6   # ambiguous — will trigger the Claude fallback
    return ClassificationHint(
        doc_type=best_type,
        confidence=confidence,
        label=_derive_label(pdf, best_type),
        source="heuristic",
    )


# ---------------------------------------------------------------------------
# Claude extraction
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """You are a senior BSA/AML analyst working on a Customer Due Diligence (CDD) file.
You are given the full text of every document a commercial-lending applicant has submitted.
Your job is to build the ownership graph of the applicant entity in structured form.

Rules:
- Only return facts you can directly cite from the provided document text.
- Always identify ONE applicant/root entity (the one that is applying for banking/credit).
  The root is almost always the top-most operating LLC / Corp referenced across the
  documents — not an individual, not a trust.
- Use stable snake_case entity_ids derived from the entity name.
- For trusts, set entity_type="trust" and entity_subtype="revocable_trust" or
  "irrevocable_trust". Populate grantor_ids/grantor_pcts for revocable trusts,
  and grantor_ids (treated as trustee IDs) + beneficiary_ids/pcts for irrevocable.
- Edges must point from parent entity → child (owner → owned entity is modelled as
  parent-LLC → child-owner so that percentages on the edge represent the ownership
  stake the child has in the parent — this matches the existing fixture schema).
  Re-read: source = entity whose equity is being held, target = the holder. Edge
  ownership_pct is the percentage of `source` held by `target`.
- Nationalities should be ISO-like ("US", "MX", "DE", "JP", "CN"). Use "Unknown"
  when not stated.
- Always prefer the applicant entity as is_root=true. Never set more than one root.
- Cite doc_id + page for every edge."""


_EXTRACT_TOOL = {
    "name": "emit_ownership_graph",
    "description": "Emit the structured ownership graph for the applicant.",
    "input_schema": {
        "type": "object",
        "properties": {
            "applicant_name": {
                "type": "string",
                "description": "Human-readable name of the applicant (root) entity.",
            },
            "entities": {
                "type": "array",
                "description": "Every entity referenced across the documents.",
                "items": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string"},
                        "label": {"type": "string"},
                        "entity_type": {"type": "string", "enum": ["company", "trust", "individual"]},
                        "entity_subtype": {
                            "type": "string",
                            "description": "One of: LLC, GmbH, LP, Corp, Ltd, revocable_trust, irrevocable_trust, or null.",
                        },
                        "jurisdiction": {"type": "string"},
                        "nationality": {
                            "type": "string",
                            "description": "Only for individuals (ISO-like code). Use 'Unknown' if not stated.",
                        },
                        "is_root": {"type": "boolean"},
                        "has_control_rights": {"type": "boolean"},
                        "source_doc_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Doc IDs where this entity is established / described.",
                        },
                        "grantor_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Trust only. For irrevocable trusts, list the trustee IDs here.",
                        },
                        "grantor_pcts": {
                            "type": "object",
                            "description": "Trust only. entity_id -> fraction (0-1).",
                            "additionalProperties": {"type": "number"},
                        },
                        "beneficiary_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "beneficiary_pcts": {
                            "type": "object",
                            "additionalProperties": {"type": "number"},
                        },
                        "discretionary": {"type": "boolean"},
                    },
                    "required": ["entity_id", "label", "entity_type", "jurisdiction", "is_root"],
                },
            },
            "edges": {
                "type": "array",
                "description": (
                    "Ownership edges. source = entity whose equity is being held; "
                    "target = entity that holds the stake; ownership_pct = the percent of source held by target."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "edge_id": {"type": "string"},
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "ownership_pct": {"type": "number"},
                        "doc_id": {"type": "string"},
                        "page": {"type": "integer"},
                        "excerpt": {
                            "type": "string",
                            "description": "≤200-char verbatim excerpt from the cited page establishing this edge.",
                        },
                    },
                    "required": ["edge_id", "source", "target", "ownership_pct", "doc_id", "page"],
                },
            },
        },
        "required": ["applicant_name", "entities", "edges"],
    },
}


def _format_corpus(docs: List[Tuple[UploadedDocumentMeta, ExtractedPDF]]) -> str:
    parts: List[str] = []
    for meta, pdf in docs:
        parts.append(
            f"=== DOCUMENT [{meta.doc_id}] — {meta.label} "
            f"(doc_type={meta.doc_type}) ==="
        )
        for page in pdf.pages:
            excerpt = page.text.strip()
            if not excerpt:
                continue
            # Cap each page at ~2000 chars to keep prompt size bounded
            if len(excerpt) > 2000:
                excerpt = excerpt[:2000] + "…"
            parts.append(f"[page {page.page}]\n{excerpt}")
        parts.append("")
    return "\n".join(parts)


async def extract_graph(
    docs: List[Tuple[UploadedDocumentMeta, ExtractedPDF]],
) -> Tuple[str, List[ExtractedEntityRef], List[ExtractedEdge]]:
    """
    Run Claude on the full document corpus and return (applicant_name, entities, edges).

    The caller is responsible for persisting the result on the case and re-running
    UBO resolution against it.
    """
    if not docs:
        return "", [], []

    corpus = _format_corpus(docs)

    user_message = (
        "You are provided every document the applicant has submitted for Customer Due Diligence. "
        "Produce the ownership graph via the emit_ownership_graph tool. "
        "Be exhaustive — every entity that appears on any page with an ownership relationship must be listed, "
        "even if it is only referenced once.\n\n"
        f"---\n{corpus}\n---"
    )

    try:
        response = await messages_create(
            model=get_settings().ANTHROPIC_MODEL,
            max_tokens=4000,
            system=_EXTRACT_SYSTEM,
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "emit_ownership_graph"},
            messages=[{"role": "user", "content": user_message}],
        )
    except APIError as exc:
        logger.error("Claude graph extraction failed: %s", exc)
        raise ClaudeAPIError(f"Document intelligence call failed: {exc}") from exc

    tool_input: Dict[str, Any] = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "emit_ownership_graph":
            tool_input = block.input  # type: ignore[assignment]
            break
    if not tool_input:
        raise ClaudeAPIError("Claude did not emit an ownership graph.")

    applicant_name = tool_input.get("applicant_name", "")

    raw_entities = tool_input.get("entities", [])
    raw_edges = tool_input.get("edges", [])

    entities: List[ExtractedEntityRef] = []
    seen_ids: set = set()
    root_marked = False
    for raw in raw_entities:
        ent_id = raw.get("entity_id")
        if not ent_id or ent_id in seen_ids:
            continue
        seen_ids.add(ent_id)
        is_root = bool(raw.get("is_root", False))
        if is_root and root_marked:
            # enforce single-root invariant — prefer the first one
            is_root = False
        if is_root:
            root_marked = True

        subtype = raw.get("entity_subtype")
        if subtype in ("", "null", None):
            subtype = None

        entities.append(
            ExtractedEntityRef(
                entity_id=ent_id,
                label=raw.get("label", ent_id),
                entity_type=raw.get("entity_type", "company"),
                entity_subtype=subtype,
                jurisdiction=raw.get("jurisdiction", "Unknown"),
                nationality=raw.get("nationality"),
                is_root=is_root,
                has_control_rights=bool(raw.get("has_control_rights", False)),
                source_doc_ids=list(raw.get("source_doc_ids", []) or []),
                grantor_ids=raw.get("grantor_ids"),
                grantor_pcts=raw.get("grantor_pcts"),
                beneficiary_ids=raw.get("beneficiary_ids"),
                beneficiary_pcts=raw.get("beneficiary_pcts"),
                discretionary=bool(raw.get("discretionary", False)),
            )
        )

    edges: List[ExtractedEdge] = []
    for idx, raw in enumerate(raw_edges, start=1):
        source = raw.get("source")
        target = raw.get("target")
        if not source or not target:
            continue
        if source not in seen_ids or target not in seen_ids:
            logger.warning(
                "Dropping edge with unknown endpoint (%s → %s)", source, target
            )
            continue
        try:
            pct = float(raw.get("ownership_pct", 0) or 0)
        except (TypeError, ValueError):
            pct = 0.0
        try:
            page = int(raw.get("page", 1) or 1)
        except (TypeError, ValueError):
            page = 1
        edges.append(
            ExtractedEdge(
                edge_id=raw.get("edge_id") or f"e{idx}",
                source=source,
                target=target,
                ownership_pct=pct,
                doc_id=raw.get("doc_id", "") or "",
                page=page,
                excerpt=(raw.get("excerpt") or "")[:280],
            )
        )

    logger.info(
        "Extracted %d entities, %d edges from %d documents (applicant=%s)",
        len(entities),
        len(edges),
        len(docs),
        applicant_name,
    )
    return applicant_name, entities, edges


# ---------------------------------------------------------------------------
# Classification polish via Claude (lightweight)
# ---------------------------------------------------------------------------

async def reclassify_with_claude(pdf: ExtractedPDF, current: ClassificationHint) -> ClassificationHint:
    """
    When the heuristic classifier is uncertain (confidence < 0.7), ask Claude
    to pick a type from the allowed enum. Keeps one-doc-at-a-time cost bounded.
    """
    if current.confidence >= 0.7:
        return current

    first_page = pdf.pages[0].text[:1500] if pdf.pages else ""
    if not first_page.strip():
        return current

    user_message = (
        "Classify the following document's type. Choose one of: "
        + ", ".join(_DOC_TYPES)
        + ".\n\nFirst-page text:\n"
        + first_page
        + "\n\nReturn JSON of shape {\"doc_type\": <string>, \"label\": <string>, \"confidence\": <0-1>}."
    )

    try:
        response = await messages_create(
            model=get_settings().ANTHROPIC_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": user_message}],
        )
    except APIError as exc:
        logger.warning("Claude classifier fallback failed: %s", exc)
        return current

    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return current
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return current
    doc_type = data.get("doc_type")
    if doc_type not in _DOC_TYPES:
        return current
    return ClassificationHint(
        doc_type=doc_type,
        confidence=float(data.get("confidence", 0.7)),
        label=str(data.get("label") or current.label)[:140],
        source="claude",
    )
