"""
Claude Agent SDK tool registry.

The 13 BSA/AML tools are wrapped as `@tool`-decorated handlers and bundled
into an in-process MCP server (`syntex`). Tools see Claude as
`mcp__syntex__<name>`.

The handlers themselves delegate to the existing `_tool_*` implementations
in `agent_tools.py` — the deterministic services (UBO resolver, screening
stubs, FinCEN digest, memo drafter) are reused unchanged. The only thing
this module owns is:

  - Translating the SDK's per-call `args -> dict` interface into the
    `(args, AgentRunContext)` shape the existing impls expect.
  - Sharing the per-run `AgentRunContext` across handlers via a
    `ContextVar`, since `@tool` doesn't accept extra closure args.
  - Recording each tool call in `ctx.execution_log` so the orchestrator
    can rebuild the `AgentTrace` after the SDK loop ends.
"""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any, Awaitable, Callable, Dict, List

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.services.agent_tools import (
    AgentRunContext,

    _tool_draft_justification,
    _tool_extract_subgraph,
    _tool_finalize,
    _tool_list_documents,
    _tool_lookup_fincen_rule,
    _tool_mark_required_document,
    _tool_note,
    _tool_read_document,
    _tool_recommend_escalation,
    _tool_resolve_ownership,
    _tool_screen_adverse_media,
    _tool_screen_ofac,
    _tool_screen_pep,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared per-run context
# ---------------------------------------------------------------------------
#
# The SDK's @tool handlers receive only `args: dict` — there's no way to pass
# the AgentRunContext explicitly. We bind it to a ContextVar at the start of
# each `run()` and read it inside every handler.

_RUN_CTX: ContextVar[AgentRunContext] = ContextVar("syntex_agent_run_ctx")


def set_run_context(ctx: AgentRunContext) -> Any:
    """Bind the per-run context. Returns a token for `reset_run_context`."""
    return _RUN_CTX.set(ctx)


def reset_run_context(token: Any) -> None:
    _RUN_CTX.reset(token)


def get_run_context() -> AgentRunContext:
    return _RUN_CTX.get()


# ---------------------------------------------------------------------------
# Generic dispatch wrapper
# ---------------------------------------------------------------------------

ImplFn = Callable[[Dict[str, Any], AgentRunContext], Awaitable[Dict[str, Any]]]


async def _invoke(name: str, args: Dict[str, Any], impl: ImplFn) -> Dict[str, Any]:
    """
    Run an underlying tool impl, log it on the run context, and return the
    SDK-shaped response.

    Errors are caught and reported as `is_error: True` content blocks so the
    SDK's loop continues (raising would kill the whole query).
    """
    try:
        ctx = _RUN_CTX.get()
    except LookupError:
        return {
            "content": [
                {"type": "text", "text": "ERROR: agent run context not bound."}
            ],
            "is_error": True,
        }

    t0 = time.time()
    try:
        payload = await impl(args, ctx)
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("SDK tool '%s' raised", name)
        payload = {"error": f"{type(exc).__name__}: {exc}"}

    duration_ms = int((time.time() - t0) * 1000)
    is_error = isinstance(payload, dict) and "error" in payload

    if name == "finalize" and not is_error:
        ctx.final_response = None  # placeholder; real assembly happens in orchestrator
        # Stash the finalize args so the orchestrator can read them off the log.

    # The execution_log lets the orchestrator rebuild AgentToolCall entries
    # without having to re-walk the SDK's streamed messages for argument data.
    ctx.execution_log.append(
        {
            "iteration": ctx.iteration,
            "name": name,
            "input": dict(args),
            "payload": payload,
            "duration_ms": duration_ms,
            "is_error": is_error,
        }
    )

    text = json.dumps(payload, default=str)
    if len(text) > 24000:
        text = text[:24000] + "…[truncated]"

    return {
        "content": [{"type": "text", "text": text}],
        "is_error": is_error,
    }


# ---------------------------------------------------------------------------
# Tool definitions — schemas mirror agent_tools.TOOL_SCHEMAS so the agent's
# tool surface is unchanged from the previous (raw-API) implementation.
# ---------------------------------------------------------------------------

@tool(
    "list_documents",
    "Return the metadata for every document uploaded to this case. "
    "Use this before reading anything to inventory what is available.",
    {"type": "object", "properties": {}, "required": []},
)
async def list_documents(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("list_documents", args, _tool_list_documents)


@tool(
    "read_document",
    "Read the text of a specific document, optionally a single page. "
    "Use this to inspect operating agreements, trust deeds, or other "
    "source documents you need to verify a claim.",
    {
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
)
async def read_document(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("read_document", args, _tool_read_document)


@tool(
    "extract_subgraph",
    "Run Claude over the document corpus to (re)extract the ownership "
    "graph (entities + edges + applicant_name). Call this once after "
    "documents are uploaded; do not call it more than once per run.",
    {
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
)
async def extract_subgraph(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("extract_subgraph", args, _tool_extract_subgraph)


@tool(
    "resolve_ownership",
    "Run deterministic UBO resolution (FinCEN 25% threshold + trust "
    "look-through) over the current entity graph. Returns the list of "
    "resolved UBOs. Call extract_subgraph first.",
    {"type": "object", "properties": {}, "required": []},
)
async def resolve_ownership(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("resolve_ownership", args, _tool_resolve_ownership)


@tool(
    "screen_ofac",
    "Screen a single individual against OFAC SDN.",
    {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["entity_id", "name"],
    },
)
async def screen_ofac(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("screen_ofac", args, _tool_screen_ofac)


@tool(
    "screen_pep",
    "Screen a single individual against the PEP list.",
    {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["entity_id", "name"],
    },
)
async def screen_pep(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("screen_pep", args, _tool_screen_pep)


@tool(
    "screen_adverse_media",
    "Screen a single individual against adverse media sources.",
    {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["entity_id", "name"],
    },
)
async def screen_adverse_media(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("screen_adverse_media", args, _tool_screen_adverse_media)


@tool(
    "mark_required_document",
    "Record a document the case needs that the deterministic checklist "
    "did not catch (e.g. a sub-LLC's operating agreement). Persists "
    "across runs in the case scratchpad.",
    {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "description": (
                    "Human-readable name (e.g. 'Operating Agreement for Acme Holdings LLC')"
                ),
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
)
async def mark_required_document(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("mark_required_document", args, _tool_mark_required_document)


@tool(
    "note",
    "Record a free-form note in the case scratchpad. Notes persist "
    "across re-runs and are surfaced to you in the next run's brief.",
    {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The note text."}
        },
        "required": ["content"],
    },
)
async def note(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("note", args, _tool_note)


@tool(
    "lookup_fincen_rule",
    "Re-read a section of the FinCEN digest by tag. The digest is "
    "already in your system prompt; use this when you want to confirm "
    "an exact phrase before quoting it.",
    {
        "type": "object",
        "properties": {
            "tag": {
                "type": "string",
                "description": "Section tag (e.g. '31CFR1010.230').",
            }
        },
        "required": ["tag"],
    },
)
async def lookup_fincen_rule(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("lookup_fincen_rule", args, _tool_lookup_fincen_rule)


@tool(
    "draft_justification",
    "Draft the intake justification: a structured, citation-backed "
    "explanation of (1) how ownership was deduced, (2) why each requested "
    "document is required, and (3) — if recommend_escalation has been "
    "called — why escalation is warranted. Requires resolve_ownership.",
    {"type": "object", "properties": {}, "required": []},
)
async def draft_justification(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("draft_justification", args, _tool_draft_justification)


@tool(
    "recommend_escalation",
    "Mark this case as requiring human compliance review. Call when "
    "complexity exceeds what an autonomous agent can responsibly resolve "
    "(multi-tier global structures, nominee arrangements, confirmed "
    "screening hits, or ≥2 escalation triggers from "
    "[fincen:OFFSHORE_JURISDICTION_RISK]).",
    {
        "type": "object",
        "properties": {
            "reasons": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Free-text reasons for escalation, ordered by importance.",
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
                "description": "Which human team should pick up the case.",
            },
        },
        "required": ["reasons", "complexity_signals"],
    },
)
async def recommend_escalation(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("recommend_escalation", args, _tool_recommend_escalation)


@tool(
    "finalize",
    "End the agent loop and emit the final risk verdict + one-sentence "
    "conclusion for the relationship manager. Call this LAST, after "
    "draft_justification (and recommend_escalation if applicable). After "
    "this, stop — emit no further tool calls.",
    {
        "type": "object",
        "properties": {
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "conclusion": {
                "type": "string",
                "description": (
                    "One-sentence summary for the RM: file shape, what's "
                    "still needed, escalation status."
                ),
            },
            "escalated": {
                "type": "boolean",
                "description": "Mirror of whether recommend_escalation was called.",
            },
        },
        "required": ["risk_level", "conclusion"],
    },
)
async def finalize(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _invoke("finalize", args, _tool_finalize)


# ---------------------------------------------------------------------------
# Server & allowed-tools list
# ---------------------------------------------------------------------------

_TOOLS: List[Any] = [
    list_documents,
    read_document,
    extract_subgraph,
    resolve_ownership,
    screen_ofac,
    screen_pep,
    screen_adverse_media,
    mark_required_document,
    note,
    lookup_fincen_rule,
    draft_justification,
    recommend_escalation,
    finalize,
]

SERVER_NAME = "syntex"

MCP_SERVER = create_sdk_mcp_server(
    name=SERVER_NAME,
    version="1.0.0",
    tools=_TOOLS,
)

_TOOL_NAMES: List[str] = [
    "list_documents",
    "read_document",
    "extract_subgraph",
    "resolve_ownership",
    "screen_ofac",
    "screen_pep",
    "screen_adverse_media",
    "mark_required_document",
    "note",
    "lookup_fincen_rule",
    "draft_justification",
    "recommend_escalation",
    "finalize",
]

ALLOWED_TOOLS: List[str] = [f"mcp__{SERVER_NAME}__{n}" for n in _TOOL_NAMES]
