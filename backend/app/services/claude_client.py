"""
Anthropic Claude API wrapper for EDD analysis.

Mirrors the tool_use pattern from syntex-doc-service's LLMParser.
All Claude calls are used for memo drafting only — UBO resolution,
trust look-through, and OFAC screening are handled deterministically.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from anthropic import AsyncAnthropic, APIError
from anthropic.types import Message

from app.config import get_settings
from app.exceptions import ClaudeAPIError
from app.models import Citation, Fixture, MemoSection, ResolvedUBO
from app.services.prompts import EDD_MEMO_SYSTEM, UBO_MEMO_SYSTEM

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=get_settings().ANTHROPIC_API_KEY)
    return _client


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
    Parse [doc_id:page] markers from Claude's output.
    Replace each unique (doc_id, page) with a sequential [N] marker.
    Return the cleaned text and the ordered citations list.
    """
    pattern = re.compile(r'\[([a-z0-9_]+):(\d+)\]')
    citations: List[Citation] = []
    seen: Dict[tuple, int] = {}

    def replace(match: re.Match) -> str:
        doc_id = match.group(1)
        page = int(match.group(2))
        key = (doc_id, page)
        if key not in seen:
            # Look up excerpt from fixture
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


async def draft_ubo_resolution_memo(
    fixture: Fixture,
    resolved_ubos: List[ResolvedUBO],
) -> List[MemoSection]:
    """
    Generate a short UBO resolution memo (Scenario A / stress).
    Returns a single MemoSection with the prose + citations.
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

    doc_context = "\n\n".join(
        f"[{doc.doc_id}] {doc.label}\n" +
        "\n".join(f"  Page {p.page}: {p.text[:500]}" for p in doc.pages)
        for doc in fixture.documents
    )

    user_message = (
        f"Applicant: {next((e.label for e in fixture.entities if e.is_root), 'Unknown')}\n\n"
        f"Resolved Beneficial Owners:\n{ubo_summary}\n\n"
        f"Entity Structure:\n{entity_summary}\n\n"
        f"Document Excerpts:\n{doc_context}\n\n"
        "Draft a UBO resolution memorandum covering: (1) brief entity overview, "
        "(2) ownership structure and resolution methodology, (3) identified beneficial owners "
        "with ownership percentages, (4) OFAC screening results, (5) recommendation. "
        "Cite every factual claim using [doc_id:page] format."
    )

    try:
        response = await _get_client().messages.create(
            model=get_settings().ANTHROPIC_MODEL,
            max_tokens=1200,
            system=UBO_MEMO_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
    except APIError as exc:
        logger.error("Claude API error drafting UBO memo: %s", exc)
        raise ClaudeAPIError(f"Claude API call failed: {exc}") from exc

    raw_text = "".join(block.text for block in response.content if block.type == "text")
    cleaned_text, citations = _resolve_citation_markers(raw_text, fixture)

    return [
        MemoSection(
            section_id="ubo_resolution",
            title="UBO Resolution Memorandum",
            content=cleaned_text,
            citations=citations,
        )
    ]


_EDD_MEMO_TOOL = {
    "name": "draft_edd_memo",
    "description": "Draft a structured EDD memo with six sections.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_overview": {
                "type": "string",
                "description": "Overview of the applicant entity: type, jurisdiction, date of formation, business purpose.",
            },
            "ownership_structure": {
                "type": "string",
                "description": "Description of the ownership structure, beneficial owners, and look-through methodology.",
            },
            "source_of_funds": {
                "type": "string",
                "description": "Analysis of stated source of funds and business revenue sources.",
            },
            "risk_factors": {
                "type": "string",
                "description": "All identified risk factors including adverse media, OFAC findings, foreign nationals, high-risk jurisdictions.",
            },
            "mitigants": {
                "type": "string",
                "description": "Risk mitigating factors: disposition of investigations, clean OFAC results, documentation quality.",
            },
            "recommendation": {
                "type": "string",
                "description": "Final recommendation: Approve / Approve with Conditions / Escalate / Decline, with rationale.",
            },
        },
        "required": [
            "entity_overview",
            "ownership_structure",
            "source_of_funds",
            "risk_factors",
            "mitigants",
            "recommendation",
        ],
    },
}

_EDD_SECTION_TITLES = {
    "entity_overview": "Entity Overview",
    "ownership_structure": "Ownership Structure",
    "source_of_funds": "Source of Funds",
    "risk_factors": "Risk Factors",
    "mitigants": "Mitigating Factors",
    "recommendation": "Recommendation",
}


async def draft_full_edd_memo(
    fixture: Fixture,
    resolved_ubos: List[ResolvedUBO],
) -> List[MemoSection]:
    """
    Generate a full 6-section EDD memo (Scenario B).
    Returns one MemoSection per section with prose + citations.
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
                "ofac_remarks": u.ofac_result.remarks,
            }
            for u in resolved_ubos
        ],
        indent=2,
    )

    doc_context = "\n\n".join(
        f"[{doc.doc_id}] {doc.label}\n" +
        "\n".join(f"  Page {p.page}: {p.text[:800]}" for p in doc.pages)
        for doc in fixture.documents
    )

    user_message = (
        f"Applicant: {next((e.label for e in fixture.entities if e.is_root), 'Unknown')}\n\n"
        f"Resolved Beneficial Owners:\n{ubo_summary}\n\n"
        f"Full Document Text:\n{doc_context}\n\n"
        "Draft a complete EDD memo. Cite every factual claim with [doc_id:page]. "
        "The Risk Factors section MUST address all adverse media findings and unresolved OFAC matches. "
        "The Recommendation section must state whether to approve, approve with conditions, or escalate."
    )

    try:
        response = await _get_client().messages.create(
            model=get_settings().ANTHROPIC_MODEL,
            max_tokens=2500,
            system=EDD_MEMO_SYSTEM,
            tools=[_EDD_MEMO_TOOL],
            tool_choice={"type": "tool", "name": "draft_edd_memo"},
            messages=[{"role": "user", "content": user_message}],
        )
    except APIError as exc:
        logger.error("Claude API error drafting EDD memo: %s", exc)
        raise ClaudeAPIError(f"Claude API call failed: {exc}") from exc

    tool_input = _extract_tool_input(response, "draft_edd_memo")

    sections: List[MemoSection] = []
    for section_id in [
        "entity_overview",
        "ownership_structure",
        "source_of_funds",
        "risk_factors",
        "mitigants",
        "recommendation",
    ]:
        raw_text = tool_input.get(section_id, "")
        cleaned_text, citations = _resolve_citation_markers(raw_text, fixture)
        sections.append(
            MemoSection(
                section_id=section_id,
                title=_EDD_SECTION_TITLES[section_id],
                content=cleaned_text,
                citations=citations,
            )
        )

    return sections
