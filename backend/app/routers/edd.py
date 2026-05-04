"""
BSA/AML Copilot API — all endpoints under /api.

Two analysis entry points share the same downstream pipeline:

  POST /api/edd/analyze { fixture_id }   — legacy scripted scenarios
  POST /api/edd/analyze { case_id }      — newly uploaded case files

Case lifecycle:

  POST   /api/cases                      create an empty case
  POST   /api/cases/{case_id}/documents  multipart upload (multiple PDFs)
  GET    /api/cases/{case_id}            fetch case detail (docs + entities)
  GET    /api/cases                      list all cases
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.exceptions import AnalysisError, EDDServiceError
from app.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    AssessApplicationRequest,
    AssessApplicationResponse,
    CaseDetail,
    CaseListResponse,
    CaseSummary,
    CreateCaseRequest,
    CreateCaseResponse,
    Fixture,
    FixtureListResponse,
    UploadDocumentsResponse,
    UploadedDocumentMeta,
)
from app.services import (
    agent_sdk_orchestrator,
    application_assessor,
    case_analyzer,
    case_store,
    claude_client,
    document_intelligence,
    fixtures,
    graph_builder,
    pdf_extractor,
    reasoning_writer,
    ubo_resolver,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["bsa-copilot"])


# ---------------------------------------------------------------------------
# Fixtures (legacy scripted scenarios — kept for regression)
# ---------------------------------------------------------------------------

@router.get("/edd/fixtures", response_model=FixtureListResponse)
async def list_fixtures() -> FixtureListResponse:
    return FixtureListResponse(fixtures=fixtures.list_fixtures())


@router.get("/edd/fixtures/{fixture_id}")
async def get_fixture(fixture_id: str) -> dict:
    fixture = fixtures.get_fixture(fixture_id)
    return fixture.model_dump()


# ---------------------------------------------------------------------------
# Cases (primary upload-driven flow)
# ---------------------------------------------------------------------------

@router.post("/cases", response_model=CreateCaseResponse)
async def create_case(request: CreateCaseRequest) -> CreateCaseResponse:
    case = case_store.create_case(request.name)
    return CreateCaseResponse(case=case)


@router.get("/cases", response_model=CaseListResponse)
async def list_cases() -> CaseListResponse:
    return CaseListResponse(cases=case_store.list_cases())


@router.get("/cases/{case_id}", response_model=CaseDetail)
async def get_case(case_id: str) -> CaseDetail:
    return case_store.get_case(case_id)


@router.get("/cases/{case_id}/analysis")
async def get_case_analysis(case_id: str) -> JSONResponse:
    case = case_store.get_case_internal(case_id)
    if case.last_analysis is None:
        # 204 No Content — must have no body, otherwise Starlette/uvicorn raises
        # "Response content longer than Content-Length".
        return Response(status_code=204)
    return JSONResponse(content=case.last_analysis.model_dump())


@router.post("/cases/{case_id}/documents", response_model=UploadDocumentsResponse)
async def upload_documents(
    case_id: str,
    files: List[UploadFile] = File(...),
) -> UploadDocumentsResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    # Ensure the case exists before doing any work.
    case_store.get_case(case_id)

    now = datetime.now(timezone.utc).isoformat()
    uploaded_meta: List[UploadedDocumentMeta] = []
    extracted_map = {}
    corpus_for_ai = []

    for upload in files:
        filename = upload.filename or f"upload_{uuid.uuid4().hex[:6]}.pdf"
        payload = await upload.read()
        if not payload:
            raise HTTPException(status_code=400, detail=f"{filename} is empty.")
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"{filename} is not a PDF. Only PDFs are supported right now.",
            )

        pdf = pdf_extractor.extract(filename, payload)
        hint = document_intelligence.classify_heuristic(pdf)
        if hint.confidence < 0.7:
            hint = await document_intelligence.reclassify_with_claude(pdf, hint)

        doc_id = f"doc_{uuid.uuid4().hex[:10]}"
        meta = UploadedDocumentMeta(
            doc_id=doc_id,
            filename=filename,
            size_bytes=pdf.size_bytes,
            page_count=pdf.page_count,
            doc_type=hint.doc_type,
            doc_type_confidence=round(hint.confidence, 2),
            classifier_source=hint.source,
            label=hint.label,
            uploaded_at=now,
        )
        uploaded_meta.append(meta)
        extracted_map[doc_id] = pdf
        corpus_for_ai.append((meta, pdf))

    case_store.add_documents(case_id, uploaded_meta, extracted_map)

    refreshed = case_store.get_case(case_id)
    return UploadDocumentsResponse(
        case=CaseSummary(
            case_id=refreshed.case_id,
            name=refreshed.name,
            status=refreshed.status,
            created_at=refreshed.created_at,
            updated_at=refreshed.updated_at,
            document_count=refreshed.document_count,
            last_analysis_at=refreshed.last_analysis_at,
        ),
        documents=refreshed.documents,
        extracted_entities=refreshed.extracted_entities,
        extracted_edges=refreshed.extracted_edges,
    )


# ---------------------------------------------------------------------------
# Analyze — shared between fixture and case paths
# ---------------------------------------------------------------------------

@router.post("/edd/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    if not request.fixture_id and not request.case_id:
        raise HTTPException(
            status_code=400,
            detail="Provide either fixture_id or case_id.",
        )

    start_ms = time.time()

    if request.case_id:
        return await _analyze_case(request.case_id, start_ms)
    return await _analyze_fixture(request.fixture_id, start_ms)


@router.post("/edd/analyze-agent", response_model=AnalyzeResponse)
async def analyze_agent(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Agent-driven analysis loop, powered by the Claude Agent SDK.

    Same response shape as `/edd/analyze`, but the middle of the pipeline is
    replaced by an SDK-driven tool-use loop. The SDK owns the message
    threading, prompt-cache breakpoint placement, retries, and stop-condition
    logic; we own the tool registry (in-process MCP server `syntex`),
    deterministic post-processing (UBO math, trust look-through, citation
    resolution, CDD checklist), and the verifier subagent.

    Only `case_id` is supported here — fixtures still go through the legacy
    `/edd/analyze` path so demo scenarios remain reproducible.

    """
    if not request.case_id:
        raise HTTPException(
            status_code=400,
            detail="analyze-agent requires case_id (fixtures use /edd/analyze).",
        )
    try:
        return await agent_sdk_orchestrator.run(request.case_id)
    except AnalysisError:
        raise
    except Exception as exc:
        logger.exception("Agent loop failed for case %s", request.case_id)
        raise AnalysisError(f"Agent loop failed: {exc}") from exc


@router.post("/edd/analyze-agent/stream")
async def analyze_agent_stream(request: AnalyzeRequest):
    """
    Server-Sent Events stream of agent loop activity.

    Events arrive as `data: <json>\\n\\n`. Each event has a `type`:
      - started, iteration, tool_use, tool_result, assistant_text
      - post_processing, verifier_start, verifier_revision, verifier_done
      - final  — payload `response` is the full AnalyzeResponse
      - error  — payload `message` is the failure reason

    The frontend uses this to render live tool-call activity and avoid the
    60–90s blank wait that hits the Next.js proxy idle-timeout.
    """
    if not request.case_id:
        raise HTTPException(
            status_code=400,
            detail="analyze-agent/stream requires case_id.",
        )

    case_id = request.case_id

    async def event_generator():
        import json

        def _serialize(event: dict) -> str:
            payload = dict(event)
            response = payload.get("response")
            if response is not None and hasattr(response, "model_dump"):
                payload["response"] = response.model_dump()
            return f"data: {json.dumps(payload, default=str)}\n\n"

        try:
            async for event in agent_sdk_orchestrator.run_stream(case_id):
                yield _serialize(event)
        except AnalysisError as exc:
            yield _serialize({"type": "error", "message": str(exc)})
        except Exception as exc:
            logger.exception("Agent stream failed for case %s", case_id)
            yield _serialize({"type": "error", "message": f"Agent loop failed: {exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable nginx-style buffering
            "Connection": "keep-alive",
        },
    )


async def _analyze_fixture(fixture_id: str, start_ms: float) -> AnalyzeResponse:
    fixture: Fixture = fixtures.get_fixture(fixture_id)
    logger.info("Starting fixture analysis %s", fixture.fixture_id)

    try:
        resolved_ubos = ubo_resolver.resolve(fixture)
        graph_nodes, graph_edges = graph_builder.build(fixture, resolved_ubos)
        work_product = reasoning_writer.build_work_product(fixture, resolved_ubos)

        justification_sections, checklist = await claude_client.draft_justification(
            fixture=fixture,
            resolved_ubos=resolved_ubos,
            requested_docs=[],
            escalation=None,
        )
    except Exception as exc:
        logger.exception("Fixture analysis failed %s", fixture.fixture_id)
        raise AnalysisError(f"Analysis failed: {exc}") from exc

    applicant_name = next((e.label for e in fixture.entities if e.is_root), fixture.label)
    processing_ms = int((time.time() - start_ms) * 1000)

    return AnalyzeResponse(
        case_id=None,
        fixture_id=fixture.fixture_id,
        scenario=fixture.scenario,
        applicant_name=applicant_name,
        resolved_ubos=resolved_ubos,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        justification_sections=justification_sections,
        risk_level=fixture.answer_key.risk_level,
        agent_work_product=work_product,
        cdd_checklist=checklist,
        escalation=None,
        processing_ms=processing_ms,
    )


async def _analyze_case(case_id: str, start_ms: float) -> AnalyzeResponse:
    case = case_store.get_case_internal(case_id)
    if not case.documents:
        raise HTTPException(
            status_code=400,
            detail="Upload at least one document before running analysis.",
        )

    # Build the ownership graph from the full document corpus now that the
    # user has explicitly requested analysis.
    full_corpus = [
        (meta, case.pdfs[meta.doc_id])
        for meta in case.documents
        if meta.doc_id in case.pdfs
    ]
    try:
        applicant_name, extracted_entities, extracted_edges = await document_intelligence.extract_graph(
            full_corpus
        )
        case_store.set_graph(case_id, applicant_name, extracted_entities, extracted_edges)
    except Exception as exc:
        logger.exception("Ownership graph extraction failed for case %s", case_id)
        raise AnalysisError(f"Ownership graph extraction failed: {exc}") from exc

    case = case_store.get_case_internal(case_id)
    case_store.mark_analyzing(case_id)
    synthetic_fixture = case_analyzer.case_to_fixture(case)

    try:
        resolved_ubos = ubo_resolver.resolve(synthetic_fixture)

        risk_level, _ = case_analyzer.infer_risk_and_memo_type(
            resolved_ubos, synthetic_fixture.entities
        )
        synthetic_fixture.answer_key.risk_level = risk_level

        graph_nodes, graph_edges = graph_builder.build(synthetic_fixture, resolved_ubos)
        work_product = reasoning_writer.build_work_product(
            synthetic_fixture, resolved_ubos, risk_level_override=risk_level
        )

        scratchpad = case_store.get_scratchpad(case_id)
        justification_sections, checklist = await claude_client.draft_justification(
            fixture=synthetic_fixture,
            resolved_ubos=resolved_ubos,
            requested_docs=scratchpad.requested_documents,
            escalation=scratchpad.escalation,
        )
    except Exception as exc:
        logger.exception("Case analysis failed %s", case_id)
        raise AnalysisError(f"Analysis failed: {exc}") from exc

    processing_ms = int((time.time() - start_ms) * 1000)
    applicant = case.applicant_name or case.name

    response = AnalyzeResponse(
        case_id=case_id,
        fixture_id=None,
        scenario=case.case_id,
        applicant_name=applicant,
        resolved_ubos=resolved_ubos,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        justification_sections=justification_sections,
        risk_level=risk_level,
        agent_work_product=work_product,
        cdd_checklist=checklist,
        escalation=scratchpad.escalation,
        processing_ms=processing_ms,
    )
    case_store.store_analysis(case_id, response)
    return response


def _fixture_entity_to_ref(e):
    from app.models import ExtractedEntityRef
    return ExtractedEntityRef(
        entity_id=e.entity_id,
        label=e.label,
        entity_type=e.entity_type,
        entity_subtype=e.entity_subtype,
        jurisdiction=e.jurisdiction,
        nationality=e.nationality,
        is_root=e.is_root,
        has_control_rights=e.has_control_rights,
        risk_flags=list(e.risk_flags),
        source_doc_ids=[],
        grantor_ids=e.grantor_ids,
        grantor_pcts=e.grantor_pcts,
        beneficiary_ids=e.beneficiary_ids,
        beneficiary_pcts=e.beneficiary_pcts,
        discretionary=e.discretionary,
    )


def _fixture_edge_to_ref(edge):
    from app.models import ExtractedEdge
    return ExtractedEdge(
        edge_id=edge.edge_id,
        source=edge.source,
        target=edge.target,
        ownership_pct=edge.ownership_pct,
        doc_id=edge.doc_id,
        page=edge.page,
        excerpt="",
    )


# ---------------------------------------------------------------------------
# Application assessment — called by the onboarding-manager webhook receiver
# ---------------------------------------------------------------------------

@router.post("/edd/assess-application", response_model=AssessApplicationResponse)
async def assess_application(request: AssessApplicationRequest) -> AssessApplicationResponse:
    """
    Run the full pre-banker compliance pass on a freshly submitted application.

    Performs name-consistency check (against uploaded formation docs), KYB/KYC
    stub screenings, OFAC + PEP + adverse-media screening, business-risk
    classification, UBO completeness audit, and synthesis of recommended
    follow-up documents and applicant questions.
    """
    try:
        assessment = await application_assessor.assess(request)
    except Exception as exc:
        logger.exception("Application assessment failed for %s", request.applicationId)
        raise AnalysisError(f"Assessment failed: {exc}") from exc
    return AssessApplicationResponse(assessment=assessment)


