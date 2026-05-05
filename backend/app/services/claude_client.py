"""
Anthropic Claude API wrapper for EDD analysis.

Mirrors the tool_use pattern from syntex-doc-service's LLMParser.
All Claude calls are used for memo drafting only — UBO resolution,
trust look-through, and OFAC screening are handled deterministically.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any, Dict, List

from anthropic import APIError, APIStatusError, AsyncAnthropic, RateLimitError
from anthropic.types import Message

from app.config import get_settings
from app.exceptions import ClaudeAPIError
from app.models import (
    CDDChecklist,
    Citation,
    EscalationRecommendation,
    Fixture,
    JustificationSection,
    MemoSection,
    RequestedDoc,
    RequiredDocument,
    ResolvedUBO,
)
from app.services import fincen_digest
from app.services.prompts import JUSTIFICATION_SYSTEM

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=get_settings().ANTHROPIC_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Retry helper for messages.create()
#
# Anthropic returns 429 when you exceed the per-minute / per-token rate limit
# and 529 when the service is temporarily overloaded. Both are transient — we
# back off and try again. Other APIErrors (4xx, malformed input, auth) bubble.
# ---------------------------------------------------------------------------

_RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504, 529}
_MAX_RETRIES = 4
_BASE_DELAY_S = 2.0


async def messages_create(**kwargs: Any) -> Message:
    """
    Wrapper around `_get_client().messages.create(**kwargs)` with bounded
    exponential backoff on 429/529. Use this everywhere instead of calling
    `messages.create` directly so the agent loop stays alive when Anthropic
    rate-limits us.
    """
    client = _get_client()
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await client.messages.create(**kwargs)
        except (RateLimitError, APIStatusError) as exc:
            status = getattr(exc, "status_code", None)
            if status not in _RETRYABLE_STATUSES or attempt == _MAX_RETRIES:
                raise
            # Anthropic sometimes returns retry-after; honor it when present.
            retry_after = _extract_retry_after(exc)
            delay = retry_after if retry_after is not None else _backoff_delay(attempt)
            logger.warning(
                "Anthropic %s on attempt %d/%d — sleeping %.1fs before retry",
                status, attempt + 1, _MAX_RETRIES + 1, delay,
            )
            await asyncio.sleep(delay)
            last_exc = exc
        except APIError as exc:
            # Generic APIError without an HTTP status (network blip, etc.)
            if attempt == _MAX_RETRIES:
                raise
            delay = _backoff_delay(attempt)
            logger.warning(
                "Anthropic transport error on attempt %d/%d (%s) — sleeping %.1fs",
                attempt + 1, _MAX_RETRIES + 1, exc, delay,
            )
            await asyncio.sleep(delay)
            last_exc = exc
    # Defensive — the loop above either returns or raises.
    raise last_exc if last_exc else ClaudeAPIError("messages.create exhausted retries")


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: 2s, 4s, 8s, 16s (± 25%)."""
    base = _BASE_DELAY_S * (2 ** attempt)
    jitter = base * 0.25 * (random.random() * 2 - 1)
    return max(0.5, base + jitter)


def _extract_retry_after(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _extract_tool_input(response: Message, tool_name: str) -> Dict[str, Any]:
    """Pull the named tool input from the API response (mirrors LLMParser._extract_tool_input)."""
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input  # type: ignore[return-value]
    raise ClaudeAPIError(f"LLM response did not contain the expected tool call ({tool_name}).")


def _resolve_citation_markers(
    text: str,
    fixture: Fixture,
) -> tuple[str, List[Citation]]:
    """
    Parse [doc_id:page] and [fincen:TAG] markers from Claude's output.
    Replace each unique reference with a sequential [N] marker.
    Return the cleaned text and the ordered citations list.

    Two marker shapes:
      - [<doc_id>:<page>]      — resolves against fixture documents
      - [fincen:<tag>]          — resolves against the FinCEN digest sections
    """
    pattern = re.compile(r'\[([a-z0-9_]+):([A-Za-z0-9._-]+)\]')
    citations: List[Citation] = []
    seen: Dict[tuple, int] = {}

    def replace(match: re.Match) -> str:
        prefix = match.group(1)
        ref = match.group(2)

        if prefix == "fincen":
            key = ("fincen", ref)
            if key not in seen:
                meta = fincen_digest.lookup(ref)
                if meta is None:
                    # Unknown FinCEN tag — preserve raw marker so reviewer notices.
                    return match.group(0)
                n = len(citations) + 1
                seen[key] = n
                citations.append(Citation(
                    doc_id="fincen",
                    page=0,
                    excerpt=meta.snippet,
                    doc_label=meta.title,
                ))
            return f"[{seen[key]}]"

        # Regular doc:page marker — `ref` should be an integer page number.
        try:
            page = int(ref)
        except ValueError:
            return match.group(0)
        doc_id = prefix
        key = ("doc", doc_id, page)
        if key not in seen:
            excerpt = ""
            doc_label = doc_id
            for doc in fixture.documents:
                if doc.doc_id == doc_id:
                    doc_label = doc.label
                    for p in doc.pages:
                        if p.page == page:
                            excerpt = p.text[:200].replace("\n", " ").strip()
                            break
                    break
            n = len(citations) + 1
            seen[key] = n
            citations.append(Citation(
                doc_id=doc_id,
                page=page,
                excerpt=excerpt,
                doc_label=doc_label,
            ))
        return f"[{seen[key]}]"

    cleaned = pattern.sub(replace, text)
    return cleaned, citations


_JUSTIFICATION_TOOL = {
    "name": "emit_justification",
    "description": (
        "Emit the structured intake justification (ownership deduction, "
        "document justification, optional escalation reasoning, and the "
        "complete CDD document checklist)."
    ),
    "cache_control": {"type": "ephemeral"},
    "input_schema": {
        "type": "object",
        "properties": {
            "ownership_deduction": {
                "type": "string",
                "description": (
                    "How ownership was deduced from the documents. Cite "
                    "[doc_id:page] and [fincen:TAG] inline."
                ),
            },
            "document_justification": {
                "type": "string",
                "description": (
                    "Why each requested document is required. Group by "
                    "entity / UBO when helpful. Every rationale must cite "
                    "the controlling FinCEN/CTA rule."
                ),
            },
            "escalation_reasoning": {
                "type": "string",
                "description": (
                    "Optional. Present only if escalation has been "
                    "recommended. Explain which complexity signals fired "
                    "and what the human reviewer should focus on first."
                ),
            },
            "required_documents": {
                "type": "array",
                "description": (
                    "CDD document checklist for this specific case. Decide "
                    "what is required based on the entity structure, ownership "
                    "paths, UBOs, and applicable rules — this varies per case. "
                    "For each requirement, check the uploaded documents and list "
                    "in `provided_by` the doc_ids of any already-submitted "
                    "documents that satisfy it."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement_id": {
                            "type": "string",
                            "description": (
                                "Unique snake_case ID, e.g. "
                                "'formation__apex_holdings_llc' or "
                                "'identity__john_doe'."
                            ),
                        },
                        "label": {
                            "type": "string",
                            "description": (
                                "Human-readable label, e.g. "
                                "'Articles of Organization — Apex Holdings LLC'."
                            ),
                        },
                        "rationale": {
                            "type": "string",
                            "description": (
                                "Why this document is required for this case "
                                "(cite the controlling FinCEN/CTA rule, ≤2 sentences)."
                            ),
                        },
                        "applies_to_entity_id": {
                            "type": "string",
                            "description": "entity_id this requirement belongs to.",
                        },
                        "provided_by": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "doc_ids of uploaded documents that already "
                                "satisfy this requirement. Empty if not yet met."
                            ),
                        },
                    },
                    "required": [
                        "requirement_id",
                        "label",
                        "rationale",
                        "applies_to_entity_id",
                        "provided_by",
                    ],
                },
            },
        },
        "required": ["ownership_deduction", "document_justification", "required_documents"],
    },
}


_JUSTIFICATION_TITLES: dict[str, str] = {
    "ownership_deduction": "Ownership Deduction",
    "document_justification": "Document Justification",
    "escalation_reasoning": "Escalation Reasoning",
}


def _build_checklist_from_agent(raw_items: list, fixture: "Fixture") -> CDDChecklist:
    items: list[RequiredDocument] = []
    for raw in raw_items:
        provided_by = raw.get("provided_by") or []
        items.append(
            RequiredDocument(
                requirement_id=raw.get("requirement_id", "unknown"),
                label=raw.get("label", ""),
                rationale=raw.get("rationale", ""),
                applies_to_entity_id=raw.get("applies_to_entity_id") or None,
                provided_by=provided_by,
                status="provided" if provided_by else "missing",
            )
        )
    missing = sum(1 for i in items if i.status == "missing")
    satisfied = sum(1 for i in items if i.status == "provided")
    return CDDChecklist(
        items=items,
        missing_count=missing,
        satisfied_count=satisfied,
        blocking_for_ubo_resolution=missing > 0,
    )


async def draft_justification(
    fixture: Fixture,
    resolved_ubos: List[ResolvedUBO],
    requested_docs: List[RequestedDoc],
    escalation: EscalationRecommendation | None,
) -> tuple[List[JustificationSection], CDDChecklist]:
    """
    Generate the three-section intake justification.

    Replaces the legacy `draft_ubo_resolution_memo` / `draft_full_edd_memo`.
    """
    ubo_summary = json.dumps(
        [
            {
                "name": u.name,
                "nationality": u.nationality,
                "ownership_pct": u.ownership_pct,
                "ubo_by_control": u.ubo_by_control,
                "risk_flags": u.risk_flags,
                "ofac_status": u.ofac_result.status,
                "pep_status": u.pep_result.status,
                "adverse_media_status": u.adverse_media_result.status,
                "path": u.path,
            }
            for u in resolved_ubos
        ],
        indent=2,
    )

    entity_summary = json.dumps(
        [
            {
                "entity_id": e.entity_id,
                "label": e.label,
                "type": e.entity_type,
                "subtype": e.entity_subtype,
                "jurisdiction": e.jurisdiction,
                "is_root": e.is_root,
            }
            for e in fixture.entities
        ],
        indent=2,
    )

    requested_summary = json.dumps(
        [
            {
                "label": d.label,
                "rationale": d.rationale,
                "applies_to_entity_id": d.applies_to_entity_id,
            }
            for d in requested_docs
        ],
        indent=2,
    ) if requested_docs else "[]"

    escalation_block = (
        json.dumps(
            {
                "reasons": escalation.reasons,
                "complexity_signals": escalation.complexity_signals,
                "recommended_team": escalation.recommended_team,
            },
            indent=2,
        )
        if escalation is not None
        else "(none — do not include the escalation_reasoning field)"
    )

    uploaded_docs_summary = json.dumps(
        [{"doc_id": doc.doc_id, "label": doc.label, "doc_type": doc.doc_type}
         for doc in fixture.documents],
        indent=2,
    )

    doc_context = "\n\n".join(
        f"[{doc.doc_id}] {doc.label}\n"
        + "\n".join(f"  Page {p.page}: {p.text[:600]}" for p in doc.pages)
        for doc in fixture.documents
    )

    user_message = (
        f"Applicant: {next((e.label for e in fixture.entities if e.is_root), 'Unknown')}\n\n"
        f"Resolved Beneficial Owners:\n{ubo_summary}\n\n"
        f"Entity Structure:\n{entity_summary}\n\n"
        f"Submitted Documents (use to populate `provided_by` in required_documents):\n"
        f"{uploaded_docs_summary}\n\n"
        f"Documents the agent flagged as still required:\n{requested_summary}\n\n"
        f"Escalation recommendation (if any):\n{escalation_block}\n\n"
        f"Document Excerpts:\n{doc_context}\n\n"
        "Emit the intake justification and CDD document checklist via the "
        "`emit_justification` tool. Cite [doc_id:page] and [fincen:TAG] inline. "
        "In `required_documents`, list every document this case requires — "
        "decide based on the specific entity structure and facts above. "
        "For each requirement, check the submitted documents list and populate "
        "`provided_by` with any doc_ids that already satisfy it. "
        "Omit `escalation_reasoning` when no escalation has been recorded."
    )

    try:
        response = await messages_create(
            model=get_settings().ANTHROPIC_MODEL,
            max_tokens=8192,
            system=[{"type": "text", "text": JUSTIFICATION_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=[_JUSTIFICATION_TOOL],
            tool_choice={"type": "tool", "name": "emit_justification"},
            messages=[{"role": "user", "content": user_message}],
        )
    except APIError as exc:
        logger.error("Claude API error drafting justification: %s", exc)
        raise ClaudeAPIError(f"Claude API call failed: {exc}") from exc

    tool_input = _extract_tool_input(response, "emit_justification")

    sections: List[JustificationSection] = []
    for section_id in ("ownership_deduction", "document_justification", "escalation_reasoning"):
        raw_text = tool_input.get(section_id)
        if not raw_text:
            continue
        cleaned_text, citations = _resolve_citation_markers(str(raw_text), fixture)
        sections.append(
            JustificationSection(
                section_id=section_id,
                title=_JUSTIFICATION_TITLES[section_id],
                content=cleaned_text,
                citations=citations,
            )
        )

    checklist = _build_checklist_from_agent(tool_input.get("required_documents") or [], fixture)
    return sections, checklist


