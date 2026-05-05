"""
Claude Agent SDK orchestrator.

`run_stream(case_id)` is an async generator that drives the SDK loop and
yields events as they happen — `tool_use`, `tool_result`, `assistant_text`,
`verifier_*`, and finally `final` (carrying the assembled `AnalyzeResponse`)
or `error`. The `/api/edd/analyze-agent/stream` endpoint serializes those
events as Server-Sent Events for the frontend's live trace.

`run(case_id)` is a thin wrapper that consumes the generator and returns the
final `AnalyzeResponse` — used by the non-streaming endpoint for
back-compat.

What the SDK owns: the tool-use loop, message threading, prompt-cache
breakpoint placement, retries, and `max_turns`. What this module owns: the
per-run `AgentRunContext`, the live event stream, the post-loop
deterministic stitching (graph/reasoning/CDD), and the verifier pass.
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from app.config import get_settings
from app.exceptions import AnalysisError
from app.models import (
    AgentToolCall,
    AgentTrace,
    AnalyzeResponse,
    CDDChecklist,
    Citation,
    EscalationRecommendation,
    JustificationSection,
)
from app.services import (
    agent_prompts,
    agent_sdk_tools,
    agent_tools,
    case_analyzer,
    case_store,
    claude_client,
    graph_builder,
    reasoning_writer,
    ubo_resolver,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers reading post-loop state off `ctx.execution_log`.
# ---------------------------------------------------------------------------

def _last_finalize(execution_log: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for entry in reversed(execution_log):
        if entry["name"] == "finalize" and not entry["is_error"]:
            payload = entry["payload"]
            return payload if isinstance(payload, dict) else None
    return None


def _last_justification(
    execution_log: List[Dict[str, Any]],
) -> List[JustificationSection]:
    for entry in reversed(execution_log):
        if entry["name"] == "draft_justification" and not entry["is_error"]:
            payload = entry["payload"]
            if not isinstance(payload, dict):
                continue
            sections_raw = payload.get("sections") or []
            return [JustificationSection(**s) for s in sections_raw]
    return []


def _last_escalation(
    execution_log: List[Dict[str, Any]],
) -> Optional[EscalationRecommendation]:
    for entry in reversed(execution_log):
        if entry["name"] == "recommend_escalation" and not entry["is_error"]:
            payload = entry["payload"]
            if not isinstance(payload, dict):
                continue
            data = payload.get("escalation")
            if isinstance(data, dict):
                try:
                    return EscalationRecommendation(**data)
                except Exception:
                    return None
    return None


def _strip_mcp_prefix(name: str) -> str:
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        return parts[-1] if len(parts) >= 3 else name
    return name


def _build_trace(
    tool_uses: List[Dict[str, Any]],
    execution_log: List[Dict[str, Any]],
) -> List[AgentToolCall]:
    out: List[AgentToolCall] = []
    n = max(len(tool_uses), len(execution_log))
    for i in range(n):
        tu = tool_uses[i] if i < len(tool_uses) else {}
        log = execution_log[i] if i < len(execution_log) else {}
        name = _strip_mcp_prefix(log.get("name") or tu.get("name") or "unknown")
        out.append(
            AgentToolCall(
                iteration=tu.get("iteration") or log.get("iteration") or 0,
                tool_use_id=tu.get("id") or f"call_{i}",
                name=name,
                input=tu.get("input") or log.get("input") or {},
                output_summary=agent_tools.output_summary(log.get("payload") or {}),
                is_error=bool(log.get("is_error", False)),
                duration_ms=int(log.get("duration_ms") or 0),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Streaming entry point
# ---------------------------------------------------------------------------

async def run_stream(case_id: str) -> AsyncIterator[Dict[str, Any]]:
    """
    Drive the agent loop and yield events as they occur. Final event is
    one of:
      {"type": "final", "response": AnalyzeResponse}
      {"type": "error", "message": str}
    """
    settings = get_settings()
    case = case_store.get_case_internal(case_id)
    if not case.documents:
        yield {
            "type": "error",
            "message": "Upload at least one document before running the agent.",
        }
        return

    scratchpad = case_store.get_scratchpad(case_id)
    ctx = agent_tools.AgentRunContext(case_id=case_id, scratchpad=scratchpad)
    case_store.mark_analyzing(case_id)

    initial_brief = agent_prompts.render_case_brief(case, scratchpad)
    options_kwargs: Dict[str, Any] = dict(
        system_prompt=agent_prompts.AGENT_SYSTEM_PROMPT,
        model=settings.ANTHROPIC_AGENT_MODEL,
        max_turns=settings.AGENT_MAX_ITERATIONS,
        allowed_tools=agent_sdk_tools.ALLOWED_TOOLS,
        mcp_servers={agent_sdk_tools.SERVER_NAME: agent_sdk_tools.MCP_SERVER},
        permission_mode="bypassPermissions",
    )
    if settings.CLAUDE_CLI_PATH:
        options_kwargs["cli_path"] = settings.CLAUDE_CLI_PATH
    options = ClaudeAgentOptions(**options_kwargs)

    yield {
        "type": "started",
        "case_id": case_id,
        "applicant": case.applicant_name or case.name,
        "document_count": len(case.documents),
    }

    tool_uses: List[Dict[str, Any]] = []
    iteration = 0
    stop_reason = "ended_naturally"
    result_msg: Optional[ResultMessage] = None
    emitted_results = 0
    start_loop_ms = time.time()

    token = agent_sdk_tools.set_run_context(ctx)
    try:
        async for message in query(prompt=initial_brief, options=options):
            if isinstance(message, SystemMessage):
                continue

            if isinstance(message, AssistantMessage):
                turn_tool_uses: List[ToolUseBlock] = []
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        turn_tool_uses.append(block)
                    elif isinstance(block, TextBlock) and block.text:
                        yield {"type": "assistant_text", "text": block.text}

                if turn_tool_uses:
                    iteration += 1
                    ctx.iteration = iteration
                    logger.info(
                        "agent.iteration case=%s iter=%s tool_count=%s names=%s",
                        case_id, iteration, len(turn_tool_uses),
                        [_strip_mcp_prefix(b.name) for b in turn_tool_uses],
                    )
                    yield {"type": "iteration", "iteration": iteration}
                    for block in turn_tool_uses:
                        display_name = _strip_mcp_prefix(block.name)
                        record = {
                            "id": block.id,
                            "name": block.name,
                            "input": dict(block.input or {}),
                            "iteration": iteration,
                        }
                        tool_uses.append(record)
                        logger.info(
                            "agent.tool_use case=%s iter=%s name=%s tool_use_id=%s arg_keys=%s",
                            case_id, iteration, display_name, block.id,
                            sorted((block.input or {}).keys()),
                        )
                        yield {
                            "type": "tool_use",
                            "iteration": iteration,
                            "name": display_name,
                            "input": record["input"],
                            "tool_use_id": block.id,
                        }

            elif isinstance(message, UserMessage):
                # Tool results have come back. Emit one tool_result event per
                # newly-appended execution_log entry — they map 1:1 with the
                # ToolResultBlocks in the same order.
                while emitted_results < len(ctx.execution_log):
                    entry = ctx.execution_log[emitted_results]
                    logger.info(
                        "agent.tool_result case=%s iter=%s name=%s is_error=%s duration_ms=%s",
                        case_id, entry["iteration"], _strip_mcp_prefix(entry["name"]),
                        entry["is_error"], entry["duration_ms"],
                    )
                    yield {
                        "type": "tool_result",
                        "iteration": entry["iteration"],
                        "name": _strip_mcp_prefix(entry["name"]),
                        "output_summary": agent_tools.output_summary(entry["payload"]),
                        "is_error": entry["is_error"],
                        "duration_ms": entry["duration_ms"],
                    }
                    emitted_results += 1

            elif isinstance(message, ResultMessage):
                result_msg = message
                subtype = getattr(message, "subtype", "") or ""
                if subtype == "success":
                    stop_reason = "ended_naturally"
                elif "max_turns" in subtype:
                    stop_reason = "max_iterations"
                elif "error" in subtype:
                    stop_reason = f"error:{subtype}"
                else:
                    stop_reason = subtype or "ended_naturally"
    except Exception as exc:
        logger.exception("Agent SDK loop crashed for case %s", case_id)
        yield {"type": "error", "message": f"Agent loop crashed: {exc}"}
        return
    finally:
        agent_sdk_tools.reset_run_context(token)

    # Drain any tool_results that arrived without a trailing UserMessage emit
    # (e.g. final assistant message had no follow-up).
    while emitted_results < len(ctx.execution_log):
        entry = ctx.execution_log[emitted_results]
        logger.info(
            "agent.tool_result_drain case=%s iter=%s name=%s is_error=%s duration_ms=%s",
            case_id, entry["iteration"], _strip_mcp_prefix(entry["name"]),
            entry["is_error"], entry["duration_ms"],
        )
        yield {
            "type": "tool_result",
            "iteration": entry["iteration"],
            "name": _strip_mcp_prefix(entry["name"]),
            "output_summary": agent_tools.output_summary(entry["payload"]),
            "is_error": entry["is_error"],
            "duration_ms": entry["duration_ms"],
        }
        emitted_results += 1

    error_count = sum(1 for e in ctx.execution_log if e["is_error"])
    logger.info(
        "agent.loop_end case=%s iterations=%s tool_calls=%s errors=%s stop_reason=%s",
        case_id, iteration, len(ctx.execution_log), error_count, stop_reason,
    )

    final_args = _last_finalize(ctx.execution_log)
    if final_args is not None:
        stop_reason = "finalized"

    if not ctx.last_resolved_ubos or ctx.last_synthetic_fixture is None:
        # Agent skipped resolve_ownership — fall back to deterministic resolution
        # so the demo never surfaces a raw error to the borrower.
        logger.warning(
            "Agent stopped without resolving ownership (stop_reason=%s) for case %s; "
            "falling back to deterministic UBO resolver.",
            stop_reason, case_id,
        )
        refreshed_case = case_store.get_case_internal(case_id)
        if refreshed_case.extracted_entities:
            synthetic_fallback = case_analyzer.case_to_fixture(refreshed_case)
            ctx.last_synthetic_fixture = synthetic_fallback
            ctx.last_resolved_ubos = ubo_resolver.resolve(synthetic_fallback)
        else:
            scratchpad.last_trace = AgentTrace(
                iterations=iteration,
                tool_calls=_build_trace(tool_uses, ctx.execution_log),
                stop_reason=stop_reason,
            )
            scratchpad.iteration_count += iteration
            case_store.update_scratchpad(case_id, scratchpad)
            yield {
                "type": "error",
                "message": (
                    f"Agent stopped without resolving ownership (stop_reason={stop_reason}) "
                    "and no entity graph is available for fallback."
                ),
            }
            return

    justification_sections = _last_justification(ctx.execution_log)
    if not justification_sections:
        # Agent skipped draft_justification — generate the memo deterministically.
        logger.warning(
            "Agent stopped without drafting a justification (stop_reason=%s) for case %s; "
            "falling back to Claude memo draft.",
            stop_reason, case_id,
        )
        try:
            justification_sections, _ = await claude_client.draft_justification(
                fixture=ctx.last_synthetic_fixture,
                resolved_ubos=ctx.last_resolved_ubos,
                requested_docs=scratchpad.requested_documents,
                escalation=scratchpad.escalation,
            )
        except Exception as exc:
            logger.exception("Fallback memo draft failed for case %s", case_id)
            scratchpad.last_trace = AgentTrace(
                iterations=iteration,
                tool_calls=_build_trace(tool_uses, ctx.execution_log),
                stop_reason=stop_reason,
            )
            scratchpad.iteration_count += iteration
            case_store.update_scratchpad(case_id, scratchpad)
            yield {
                "type": "error",
                "message": (
                    f"Agent stopped without drafting a justification "
                    f"(stop_reason={stop_reason}) and fallback memo draft failed: {exc}"
                ),
            }
            return

    if final_args:
        risk_level = final_args.get("risk_level", "medium")
    else:
        risk_level, _ = case_analyzer.infer_risk_and_memo_type(
            ctx.last_resolved_ubos, ctx.last_synthetic_fixture.entities
        )

    escalation = ctx.escalation or _last_escalation(ctx.execution_log)

    yield {"type": "post_processing", "stop_reason": stop_reason, "iterations": iteration}

    fixture = ctx.last_synthetic_fixture
    fixture.answer_key.risk_level = risk_level
    graph_nodes, graph_edges = graph_builder.build(fixture, ctx.last_resolved_ubos)
    work_product = reasoning_writer.build_work_product(
        fixture, ctx.last_resolved_ubos, risk_level_override=risk_level
    )
    checklist = ctx.last_cdd_checklist or CDDChecklist(
        items=[], missing_count=0, satisfied_count=0, blocking_for_ubo_resolution=False
    )

    fincen_cites: List[Citation] = []
    seen_tags: set[str] = set()
    for sec in justification_sections:
        for c in sec.citations:
            if c.doc_id == "fincen" and c.doc_label not in seen_tags:
                fincen_cites.append(c)
                seen_tags.add(c.doc_label)

    case = case_store.get_case_internal(case_id)
    applicant = case.applicant_name or case.name
    processing_ms = int((time.time() - start_loop_ms) * 1000)

    response = AnalyzeResponse(
        case_id=case_id,
        fixture_id=None,
        scenario=case_id,
        applicant_name=applicant,
        resolved_ubos=ctx.last_resolved_ubos,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        justification_sections=justification_sections,
        risk_level=risk_level,
        agent_work_product=work_product,
        cdd_checklist=checklist,
        escalation=escalation,
        processing_ms=processing_ms,
        agent_trace=AgentTrace(
            iterations=iteration,
            tool_calls=_build_trace(tool_uses, ctx.execution_log),
            stop_reason=stop_reason,
        ),
        fincen_citations=fincen_cites,
    )

    # ----- Persist -----
    scratchpad.last_trace = response.agent_trace
    scratchpad.iteration_count += iteration
    case_store.update_scratchpad(case_id, scratchpad)
    case_store.store_analysis(case_id, response)

    if result_msg is not None:
        logger.info(
            "SDK run finished: case=%s turns=%s cost_usd=%s",
            case_id,
            getattr(result_msg, "num_turns", "?"),
            getattr(result_msg, "total_cost_usd", "?"),
        )

    yield {"type": "final", "response": response}


async def run(case_id: str) -> AnalyzeResponse:
    """Non-streaming wrapper: drains run_stream, returns the final response."""
    async for event in run_stream(case_id):
        if event["type"] == "final":
            return event["response"]
        if event["type"] == "error":
            raise AnalysisError(event["message"])
    raise AnalysisError("Stream ended without a final event.")
