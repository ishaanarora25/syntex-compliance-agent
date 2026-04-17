"""
EDD router — all endpoints under /api/edd.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter

from app.exceptions import AnalysisError
from app.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    ApproveRequest,
    ApproveResponse,
    AuditEntry,
    AuditLogResponse,
    Fixture,
    FixtureListResponse,
)
from app.services import claude_client, fixtures, graph_builder, reasoning_writer, ubo_resolver

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/edd", tags=["edd"])

# In-memory audit log (demo only — lost on restart)
_audit_log: List[AuditEntry] = []


@router.get("/fixtures", response_model=FixtureListResponse)
async def list_fixtures() -> FixtureListResponse:
    return FixtureListResponse(fixtures=fixtures.list_fixtures())


@router.get("/fixtures/{fixture_id}")
async def get_fixture(fixture_id: str) -> dict:
    fixture = fixtures.get_fixture(fixture_id)
    return fixture.model_dump()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    start_ms = time.time()

    fixture: Fixture = fixtures.get_fixture(request.fixture_id)
    logger.info("Starting analysis for fixture %s", fixture.fixture_id)

    try:
        # 1. Resolve UBOs (deterministic: trust look-through + OFAC stub)
        resolved_ubos = ubo_resolver.resolve(fixture)

        # 2. Build ownership graph with BFS layout
        graph_nodes, graph_edges = graph_builder.build(fixture, resolved_ubos)

        # 3. Build agent work product (deterministic reasoning trace)
        work_product = reasoning_writer.build_work_product(fixture, resolved_ubos)

        # 4. Draft memo via Claude
        memo_type = fixture.answer_key.memo_type
        if memo_type == "full_edd":
            memo_sections = await claude_client.draft_full_edd_memo(fixture, resolved_ubos)
        else:
            memo_sections = await claude_client.draft_ubo_resolution_memo(fixture, resolved_ubos)

    except Exception as exc:
        logger.exception("Analysis failed for fixture %s", fixture.fixture_id)
        raise AnalysisError(f"Analysis failed: {exc}") from exc

    processing_ms = int((time.time() - start_ms) * 1000)
    logger.info(
        "Analysis complete for fixture %s in %dms — %d UBOs, %d memo sections",
        fixture.fixture_id,
        processing_ms,
        len(resolved_ubos),
        len(memo_sections),
    )

    return AnalyzeResponse(
        fixture_id=fixture.fixture_id,
        scenario=fixture.scenario,
        resolved_ubos=resolved_ubos,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        memo_type=memo_type,
        memo_sections=memo_sections,
        risk_level=fixture.answer_key.risk_level,
        agent_work_product=work_product,
        processing_ms=processing_ms,
    )


@router.post("/approve", response_model=ApproveResponse)
async def approve(request: ApproveRequest) -> ApproveResponse:
    fixture = fixtures.get_fixture(request.fixture_id)

    entry = AuditEntry(
        entry_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        event="DRAFT_APPROVED",
        fixture_id=request.fixture_id,
        fixture_label=fixture.label,
        approved_by=request.approved_by,
        risk_level=fixture.answer_key.risk_level,
        conclusion=request.conclusion,
    )
    _audit_log.append(entry)
    logger.info(
        "Audit: %s approved fixture %s (risk=%s conclusion=%s)",
        request.approved_by,
        request.fixture_id,
        fixture.answer_key.risk_level,
        request.conclusion,
    )
    return ApproveResponse(entry=entry)


@router.get("/audit", response_model=AuditLogResponse)
async def get_audit_log() -> AuditLogResponse:
    return AuditLogResponse(entries=list(reversed(_audit_log)))
