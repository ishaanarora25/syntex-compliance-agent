"""
Agent tool registry.

Defines the Anthropic-style `tools` schemas and an async `dispatch` function
that the agent_orchestrator calls for every tool_use block. Each tool wraps an
existing deterministic service so the agent loop is purely a routing layer.

Tools mutate the shared `AgentRunContext`, which carries the case and
scratchpad through the loop. Outputs are JSON-serializable dicts (Pydantic
models are .model_dump()'d before return).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.exceptions import ClaudeAPIError, EDDServiceError
from app.models import (
    AgentScratchpad,
    AnalyzeResponse,
    CDDChecklist,
    Citation,
    EscalationRecommendation,
    Fixture,
    FixtureDocument,
    FixturePage,
    JustificationSection,
    RequestedDoc,
    ResolvedUBO,
    UploadedDocumentMeta,
)
from app.services import (
    adverse_media_service,
    business_risk,
    case_analyzer,
    case_store,

    claude_client,
    document_intelligence,
    fincen_digest,
    graph_builder,
    name_consistency,
    ofac_service,
    pep_service,
    reasoning_writer,
    ubo_resolver,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Run context — what every tool dispatcher sees
# ---------------------------------------------------------------------------

@dataclass
class AgentRunContext:
    case_id: str
    scratchpad: AgentScratchpad
    iteration: int = 0
    # Cached intermediate state across tool calls within a single run.
    last_resolved_ubos: List[ResolvedUBO] = field(default_factory=list)
    last_synthetic_fixture: Optional[Fixture] = None
    last_justification: List[JustificationSection] = field(default_factory=list)
    last_cdd_checklist: Optional[CDDChecklist] = None
    escalation: Optional[EscalationRecommendation] = None
    final_response: Optional[AnalyzeResponse] = None
    # Used by the SDK-based orchestrator (agent_sdk_orchestrator) to rebuild
    # the trace after the SDK loop ends.
    execution_log: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool schemas (Anthropic format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "list_documents",
        "description": (
            "Return the metadata for every document uploaded to this case. "
            "Use this before reading anything to inventory what is available."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_document",
        "description": (
            "Read the text of a specific document, optionally a single page. "
            "Use this to inspect operating agreements, trust deeds, or other "
            "source documents you need to verify a claim."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "doc_id from list_documents"},
                "page": {
                    "type": "integer",
                    "description": "1-indexed page; omit to return all pages.",
                },
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "extract_subgraph",
        "description": (
            "Run Claude over the document corpus to (re)extract the ownership "
            "graph (entities + edges + applicant_name). Call this once after "
            "documents are uploaded; do not call it more than once per run."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional subset of doc_ids to extract from. Omit to "
                        "use the full corpus."
                    ),
                }
            },
            "required": [],
        },
    },
    {
        "name": "resolve_ownership",
        "description": (
            "Run deterministic UBO resolution (FinCEN 25% threshold + trust "
            "look-through) over the current entity graph. Returns the list of "
            "resolved UBOs. Call extract_subgraph first."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "screen_ofac",
        "description": "Screen a single individual against OFAC SDN.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["entity_id", "name"],
        },
    },
    {
        "name": "screen_pep",
        "description": "Screen a single individual against the PEP list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["entity_id", "name"],
        },
    },
    {
        "name": "screen_adverse_media",
        "description": "Screen a single individual against adverse media sources.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["entity_id", "name"],
        },
    },
    {
        "name": "mark_required_document",
        "description": (
            "Record a document the case needs that the deterministic checklist "
            "did not catch (e.g. a sub-LLC's operating agreement). Persists "
            "across runs in the case scratchpad."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Human-readable name (e.g. 'Operating Agreement for Acme Holdings LLC')",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this document is required.",
                },
                "applies_to_entity_id": {
                    "type": "string",
                    "description": "Entity this document is needed for; optional.",
                },
            },
            "required": ["label", "rationale"],
        },
    },
    {
        "name": "note",
        "description": (
            "Record a free-form note in the case scratchpad. Notes persist "
            "across re-runs and are surfaced to you in the next run's brief."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The note text."}
            },
            "required": ["content"],
        },
    },
    {
        "name": "lookup_fincen_rule",
        "description": (
            "Re-read a section of the FinCEN digest by tag. The digest is "
            "already in your system prompt; use this when you want to confirm "
            "an exact phrase before quoting it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tag": {
                    "type": "string",
                    "description": "Section tag (e.g. '31CFR1010.230').",
                }
            },
            "required": ["tag"],
        },
    },
    {
        "name": "draft_justification",
        "description": (
            "Draft the intake justification: a structured, citation-backed "
            "explanation of (1) how ownership was deduced from the documents, "
            "(2) why each requested document is required, and (3) — if "
            "recommend_escalation has been called — why escalation is "
            "warranted. Replaces the legacy draft_memo tool. Requires "
            "resolve_ownership to have been called first."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "recommend_escalation",
        "description": (
            "Mark this case as requiring human compliance review. Call when "
            "complexity exceeds what an autonomous agent can responsibly "
            "resolve (multi-tier global structures, nominee arrangements, "
            "confirmed sanctions/PEP hits, or ≥2 escalation triggers from the "
            "FinCEN OFFSHORE_JURISDICTION_RISK digest). Reasons and signals "
            "should be specific so the human reviewer can pick up cleanly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Free-text reasons for escalation, ordered by importance."
                    ),
                },
                "complexity_signals": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "multi_tier",
                            "multi_jurisdiction",
                            "nominee_arrangement",
                            "offshore_intermediary",
                            "confirmed_screening_hit",
                            "irrevocable_trust_with_foreign_nationals",
                            "incomplete_documentation",
                        ],
                    },
                    "description": "Structured complexity signals that fired.",
                },
                "recommended_team": {
                    "type": "string",
                    "description": (
                        "Which human team should pick up the case "
                        "(e.g. 'BSA/AML enhanced review team')."
                    ),
                },
            },
            "required": ["reasons", "complexity_signals"],
        },
    },
    {
        "name": "finalize",
        "description": (
            "End the agent loop and emit the final risk verdict + one-sentence "
            "conclusion. Call this LAST, after draft_justification (and "
            "recommend_escalation if applicable). After this, stop — emit no "
            "further tool calls."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
                "conclusion": {
                    "type": "string",
                    "description": (
                        "One-sentence summary for the relationship manager: "
                        "what the file looks like, what's still needed, and "
                        "whether escalation has been recommended."
                    ),
                },
                "escalated": {
                    "type": "boolean",
                    "description": (
                        "Mirror of whether recommend_escalation was called. "
                        "Optional — orchestrator falls back to scratchpad."
                    ),
                },
            },
            "required": ["risk_level", "conclusion"],
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize(value: Any, limit: int = 600) -> str:
    """Compact, human-readable string for the trace's output_summary field."""
    if isinstance(value, dict):
        if "error" in value:
            return f"ERROR: {value['error']}"
        # Prefer a single-line preview of common fields
        keys = list(value.keys())[:6]
        parts = []
        for k in keys:
            v = value.get(k)
            if isinstance(v, (list, dict)):
                parts.append(f"{k}=[{len(v)} items]" if isinstance(v, list) else f"{k}={{…}}")
            else:
                parts.append(f"{k}={str(v)[:40]}")
        s = ", ".join(parts)
        return s[:limit]
    s = str(value)
    return s[:limit]


def _docs_to_fixture_documents(case_documents: List[UploadedDocumentMeta], pdfs) -> List[FixtureDocument]:
    """Build FixtureDocument list from case PDFs (used by claude_client memo drafters)."""
    out: List[FixtureDocument] = []
    for meta in case_documents:
        pdf = pdfs.get(meta.doc_id)
        if pdf is None:
            continue
        out.append(
            FixtureDocument(
                doc_id=meta.doc_id,
                label=meta.label,
                doc_type=meta.doc_type,
                pages=[FixturePage(page=p.page, text=p.text) for p in pdf.pages],
            )
        )
    return out


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def _tool_list_documents(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    case = case_store.get_case_internal(ctx.case_id)
    return {
        "documents": [
            {
                "doc_id": d.doc_id,
                "filename": d.filename,
                "label": d.label,
                "doc_type": d.doc_type,
                "page_count": d.page_count,
                "classifier_source": d.classifier_source,
                "doc_type_confidence": d.doc_type_confidence,
            }
            for d in case.documents
        ]
    }


async def _tool_read_document(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    doc_id = args.get("doc_id")
    if not doc_id:
        return {"error": "doc_id required"}
    page = args.get("page")
    case = case_store.get_case_internal(ctx.case_id)
    pdf = case.pdfs.get(doc_id)
    if pdf is None:
        return {"error": f"unknown doc_id {doc_id}"}
    pages = pdf.pages
    if page is not None:
        try:
            page_int = int(page)
        except (TypeError, ValueError):
            return {"error": "page must be an integer"}
        pages = [p for p in pages if p.page == page_int]
        if not pages:
            return {"error": f"page {page_int} not found in {doc_id}"}
    return {
        "doc_id": doc_id,
        "page_count": len(pdf.pages),
        "pages": [
            {"page": p.page, "text": (p.text or "")[:4000]} for p in pages
        ],
    }


async def _tool_extract_subgraph(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    case = case_store.get_case_internal(ctx.case_id)
    if not case.documents:
        return {"error": "no documents uploaded yet"}
    subset = args.get("doc_ids")
    if subset:
        keep = set(subset)
        corpus = [
            (m, case.pdfs[m.doc_id])
            for m in case.documents
            if m.doc_id in keep and m.doc_id in case.pdfs
        ]
        if not corpus:
            return {"error": "doc_ids did not match any uploaded document"}
    else:
        corpus = [(m, case.pdfs[m.doc_id]) for m in case.documents if m.doc_id in case.pdfs]

    applicant_name, entities, edges = await document_intelligence.extract_graph(corpus)
    case_store.set_graph(ctx.case_id, applicant_name, entities, edges)

    return {
        "applicant_name": applicant_name,
        "entity_count": len(entities),
        "edge_count": len(edges),
        "entities": [
            {
                "entity_id": e.entity_id,
                "label": e.label,
                "entity_type": e.entity_type,
                "entity_subtype": e.entity_subtype,
                "jurisdiction": e.jurisdiction,
                "is_root": e.is_root,
                "has_control_rights": e.has_control_rights,
            }
            for e in entities
        ],
        "edges": [
            {
                "source": ed.source,
                "target": ed.target,
                "ownership_pct": ed.ownership_pct,
                "doc_id": ed.doc_id,
                "page": ed.page,
            }
            for ed in edges
        ],
    }


async def _tool_resolve_ownership(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    case = case_store.get_case_internal(ctx.case_id)
    if not case.extracted_entities:
        return {"error": "no entity graph yet — call extract_subgraph first"}
    synthetic = case_analyzer.case_to_fixture(case)
    ctx.last_synthetic_fixture = synthetic
    resolved = ubo_resolver.resolve(synthetic)
    ctx.last_resolved_ubos = resolved
    return {
        "ubo_count": len(resolved),
        "ubos": [
            {
                "entity_id": u.entity_id,
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
            for u in resolved
        ],
    }


async def _tool_screen_ofac(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    entity_id = args.get("entity_id", "")
    name = args.get("name", "")
    if not name:
        return {"error": "name required"}
    return ofac_service.screen(entity_id, name).model_dump()


async def _tool_screen_pep(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    entity_id = args.get("entity_id", "")
    name = args.get("name", "")
    if not name:
        return {"error": "name required"}
    return pep_service.screen(entity_id, name).model_dump()


async def _tool_screen_adverse_media(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    entity_id = args.get("entity_id", "")
    name = args.get("name", "")
    if not name:
        return {"error": "name required"}
    return adverse_media_service.screen(entity_id, name).model_dump()


async def _tool_mark_required_document(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    label = args.get("label")
    rationale = args.get("rationale")
    if not label or not rationale:
        return {"error": "label and rationale required"}
    doc = RequestedDoc(
        requirement_id=f"req_{uuid.uuid4().hex[:8]}",
        label=label,
        rationale=rationale,
        applies_to_entity_id=args.get("applies_to_entity_id"),
        requested_at=_now(),
    )
    case_store.add_requested_document(ctx.case_id, doc)
    ctx.scratchpad.requested_documents.append(doc)
    return {"recorded": True, "requirement_id": doc.requirement_id}


async def _tool_note(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    content = args.get("content", "").strip()
    if not content:
        return {"error": "content required"}
    case_store.append_note(ctx.case_id, content)
    ctx.scratchpad.notes.append(content)
    return {"recorded": True}


async def _tool_lookup_fincen_rule(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    tag = args.get("tag", "")
    if not tag:
        return {"error": "tag required"}
    section = fincen_digest.lookup(tag)
    if section is None:
        return {
            "error": f"unknown tag '{tag}'",
            "known_tags": fincen_digest.known_tags(),
        }
    if tag not in ctx.scratchpad.fincen_lookups:
        ctx.scratchpad.fincen_lookups.append(tag)
    return {
        "tag": section.tag,
        "title": section.title,
        "snippet": section.snippet,
    }


async def _tool_draft_justification(
    args: Dict[str, Any], ctx: AgentRunContext
) -> Dict[str, Any]:
    if not ctx.last_resolved_ubos and ctx.escalation is None:
        return {
            "error": (
                "call resolve_ownership before draft_justification (or call "
                "recommend_escalation first if the structure cannot be resolved)."
            )
        }
    if ctx.last_synthetic_fixture is None:
        return {"error": "no fixture/case context — extract_subgraph + resolve_ownership first"}

    fixture = ctx.last_synthetic_fixture
    requested = list(ctx.scratchpad.requested_documents)
    sections, checklist = await claude_client.draft_justification(
        fixture=fixture,
        resolved_ubos=ctx.last_resolved_ubos,
        requested_docs=requested,
        escalation=ctx.escalation,
    )
    ctx.last_justification = sections
    ctx.last_cdd_checklist = checklist
    return {
        "sections": [s.model_dump() for s in sections],
    }


async def _tool_recommend_escalation(
    args: Dict[str, Any], ctx: AgentRunContext
) -> Dict[str, Any]:
    reasons = args.get("reasons") or []
    signals = args.get("complexity_signals") or []
    if not isinstance(reasons, list) or not reasons:
        return {"error": "reasons must be a non-empty list of strings"}
    if not isinstance(signals, list) or not signals:
        return {"error": "complexity_signals must be a non-empty list"}

    recommended_team = args.get("recommended_team") or "BSA/AML enhanced review team"
    rec = EscalationRecommendation(
        escalated=True,
        reasons=[str(r) for r in reasons],
        complexity_signals=[str(s) for s in signals],
        recommended_team=str(recommended_team),
        recorded_at=_now(),
    )
    ctx.escalation = rec
    ctx.scratchpad.escalation = rec
    case_store.set_escalation(ctx.case_id, rec)
    return {"recorded": True, "escalation": rec.model_dump()}


async def _tool_finalize(args: Dict[str, Any], ctx: AgentRunContext) -> Dict[str, Any]:
    """
    Finalize doesn't produce an AnalyzeResponse on its own — the orchestrator
    assembles the final response after seeing this tool fire. We record the
    agent's stated risk + conclusion + escalation flag.
    """
    risk_level = args.get("risk_level")
    conclusion = args.get("conclusion", "")
    if risk_level not in ("low", "medium", "high"):
        return {"error": "risk_level required ('low' | 'medium' | 'high')"}

    escalated_arg = args.get("escalated")
    escalated = bool(escalated_arg) if escalated_arg is not None else (ctx.escalation is not None)

    return {
        "finalized": True,
        "risk_level": risk_level,
        "conclusion": str(conclusion),
        "escalated": escalated,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

DISPATCHERS: Dict[str, Callable[[Dict[str, Any], AgentRunContext], Awaitable[Dict[str, Any]]]] = {
    "list_documents": _tool_list_documents,
    "read_document": _tool_read_document,
    "extract_subgraph": _tool_extract_subgraph,
    "resolve_ownership": _tool_resolve_ownership,
    "screen_ofac": _tool_screen_ofac,
    "screen_pep": _tool_screen_pep,
    "screen_adverse_media": _tool_screen_adverse_media,

    "mark_required_document": _tool_mark_required_document,
    "note": _tool_note,
    "lookup_fincen_rule": _tool_lookup_fincen_rule,
    "draft_justification": _tool_draft_justification,
    "recommend_escalation": _tool_recommend_escalation,
    "finalize": _tool_finalize,
}


async def dispatch(
    name: str,
    args: Dict[str, Any],
    ctx: AgentRunContext,
    timeout_s: int,
) -> Dict[str, Any]:
    """Run a single tool with timeout + uniform error handling."""
    fn = DISPATCHERS.get(name)
    if fn is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return await asyncio.wait_for(fn(args, ctx), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning("tool %s timed out", name)
        return {"error": f"tool '{name}' timed out after {timeout_s}s"}
    except (ClaudeAPIError, EDDServiceError) as exc:
        logger.warning("tool %s service error: %s", name, exc)
        return {"error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("tool %s unexpected error", name)
        return {"error": f"unexpected error: {exc}"}


def output_summary(value: Any) -> str:
    return _summarize(value)
