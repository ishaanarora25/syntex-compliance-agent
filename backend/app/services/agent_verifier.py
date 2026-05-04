"""
Verifier subagent: a second Claude pass that audits the drafted memo against
the resolved UBOs and screening results before we hand the response back.

Two public functions:

- `review(response, scratchpad)` — single LLM call returning a VerifierReport.
- `redraft(response, ubos, fixture, report)` — re-invokes the memo drafter
  with the verifier feedback appended, returning revised memo sections.

Both are awaited from agent_orchestrator. The verifier never modifies state on
its own; the orchestrator decides what to do with its findings.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from anthropic import APIError

from app.config import get_settings
from app.exceptions import ClaudeAPIError
from app.models import (
    AgentScratchpad,
    AnalyzeResponse,
    EscalationRecommendation,
    Fixture,
    JustificationSection,
    RequestedDoc,
    ResolvedUBO,
    VerifierFinding,
    VerifierReport,
)
from app.services import claude_client
from app.services.agent_prompts import VERIFIER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


_VERIFIER_TOOL = {
    "name": "verifier_report",
    "description": "Emit the structured verifier audit of the EDD memo.",
    "input_schema": {
        "type": "object",
        "properties": {
            "needs_revision": {
                "type": "boolean",
                "description": "True if any high-severity issue was found, or >2 medium issues.",
            },
            "claims_unsupported": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_id": {"type": "string"},
                        "issue": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                    "required": ["issue", "severity"],
                },
            },
            "risks_unaddressed": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_id": {"type": "string"},
                        "issue": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                    "required": ["issue", "severity"],
                },
            },
            "citations_missing": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_id": {"type": "string"},
                        "issue": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                    "required": ["issue", "severity"],
                },
            },
            "summary": {
                "type": "string",
                "description": "2-3 sentence overall assessment.",
            },
        },
        "required": ["needs_revision", "summary"],
    },
}


def _findings_from(raw: list) -> List[VerifierFinding]:
    out: List[VerifierFinding] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        try:
            out.append(VerifierFinding(**item))
        except Exception:
            logger.warning("Skipping malformed verifier finding: %s", item)
    return out


def _ubo_summary(ubos: List[ResolvedUBO]) -> str:
    rows = []
    for u in ubos:
        rows.append(
            f"- {u.name} ({u.entity_id}) — {u.ownership_pct:.1f}% — "
            f"OFAC={u.ofac_result.status} PEP={u.pep_result.status} "
            f"AdverseMedia={u.adverse_media_result.status} "
            f"flags={','.join(u.risk_flags) or 'none'}"
        )
    return "\n".join(rows) if rows else "(none resolved)"


def _justification_summary(sections: List[JustificationSection]) -> str:
    parts = []
    for s in sections:
        parts.append(f"### {s.title} ({s.section_id})\n{s.content}")
    return "\n\n".join(parts) if parts else "(no sections drafted)"


def _escalation_summary(escalation: EscalationRecommendation | None) -> str:
    if escalation is None:
        return "(no escalation recommended)"
    return (
        f"escalated=true, recommended_team={escalation.recommended_team}, "
        f"signals={escalation.complexity_signals}, reasons={escalation.reasons}"
    )


async def review(
    response: AnalyzeResponse, scratchpad: AgentScratchpad
) -> VerifierReport:
    settings = get_settings()
    user_message = (
        f"# Case under review\n"
        f"Applicant: {response.applicant_name}\n"
        f"Risk level: {response.risk_level}\n\n"
        f"## Resolved UBOs\n{_ubo_summary(response.resolved_ubos)}\n\n"
        f"## Escalation status\n{_escalation_summary(response.escalation)}\n\n"
        f"## Drafted justification\n"
        f"{_justification_summary(response.justification_sections)}\n\n"
        f"Audit the justification + escalation against the UBO + screening "
        f"data. Return your findings via the `verifier_report` tool."
    )
    try:
        api_response = await claude_client.messages_create(
            model=settings.ANTHROPIC_AGENT_MODEL,
            max_tokens=2000,
            system=VERIFIER_SYSTEM_PROMPT,
            tools=[_VERIFIER_TOOL],
            tool_choice={"type": "tool", "name": "verifier_report"},
            messages=[{"role": "user", "content": user_message}],
        )
    except APIError as exc:
        logger.warning("Verifier call failed: %s", exc)
        # Soft-fail: skip verification rather than block the response.
        return VerifierReport(
            needs_revision=False,
            summary=f"Verifier unavailable: {exc}. Proceeding with un-audited memo.",
        )

    tool_input = None
    for block in api_response.content:
        if block.type == "tool_use" and block.name == "verifier_report":
            tool_input = block.input
            break

    if not isinstance(tool_input, dict):
        return VerifierReport(
            needs_revision=False, summary="Verifier returned no structured output."
        )

    return VerifierReport(
        needs_revision=bool(tool_input.get("needs_revision", False)),
        claims_unsupported=_findings_from(tool_input.get("claims_unsupported")),
        risks_unaddressed=_findings_from(tool_input.get("risks_unaddressed")),
        citations_missing=_findings_from(tool_input.get("citations_missing")),
        summary=str(tool_input.get("summary", "")),
    )


def _findings_to_text(report: VerifierReport) -> str:
    bits: list[str] = []
    if report.claims_unsupported:
        bits.append("Claims that lack support in the data:")
        for f in report.claims_unsupported:
            bits.append(f"  - [{f.severity}] {f.section_id or 'memo'}: {f.issue}")
    if report.risks_unaddressed:
        bits.append("Risks the memo failed to address:")
        for f in report.risks_unaddressed:
            bits.append(f"  - [{f.severity}] {f.section_id or 'memo'}: {f.issue}")
    if report.citations_missing:
        bits.append("Statements that need citations:")
        for f in report.citations_missing:
            bits.append(f"  - [{f.severity}] {f.section_id or 'memo'}: {f.issue}")
    if report.summary:
        bits.append("")
        bits.append(f"Reviewer summary: {report.summary}")
    return "\n".join(bits)


async def redraft(
    response: AnalyzeResponse,
    ubos: List[ResolvedUBO],
    fixture: Fixture,
    requested_docs: List[RequestedDoc],
    escalation: EscalationRecommendation | None,
    report: VerifierReport,
) -> Optional[List[JustificationSection]]:
    """Re-draft the justification with verifier feedback prepended."""
    feedback = _findings_to_text(report)
    if not feedback:
        return None

    original_description = fixture.description
    fixture.description = (
        f"{original_description}\n\n"
        "### Reviewer feedback (incorporate when redrafting):\n"
        f"{feedback}"
    )
    try:
        sections, _ = await claude_client.draft_justification(
            fixture=fixture,
            resolved_ubos=ubos,
            requested_docs=requested_docs,
            escalation=escalation,
        )
        return sections
    except (ClaudeAPIError, APIError) as exc:
        logger.warning("Verifier redraft failed: %s", exc)
        return None
    finally:
        fixture.description = original_description
