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

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.exceptions import AnalysisError, EDDServiceError
from app.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    ApproveRequest,
    ApproveResponse,
    AuditEntry,
    AuditLogResponse,
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
    case_analyzer,
    case_store,
    cdd_requirements,
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

# In-memory audit log (demo only — lost on restart)
_audit_log: List[AuditEntry] = []


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
        return JSONResponse(status_code=204, content=None)
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


async def _analyze_fixture(fixture_id: str, start_ms: float) -> AnalyzeResponse:
    fixture: Fixture = fixtures.get_fixture(fixture_id)
    logger.info("Starting fixture analysis %s", fixture.fixture_id)

    try:
        resolved_ubos = ubo_resolver.resolve(fixture)
        graph_nodes, graph_edges = graph_builder.build(fixture, resolved_ubos)
        work_product = reasoning_writer.build_work_product(fixture, resolved_ubos)

        memo_type = fixture.answer_key.memo_type
        if memo_type == "full_edd":
            memo_sections = await claude_client.draft_full_edd_memo(fixture, resolved_ubos)
        else:
            memo_sections = await claude_client.draft_ubo_resolution_memo(fixture, resolved_ubos)

        # Build a synthetic "uploaded documents" list from the fixture so the
        # CDD checklist can evaluate which required docs are present.
        uploaded = [
            UploadedDocumentMeta(
                doc_id=d.doc_id,
                filename=f"{d.doc_id}.pdf",
                size_bytes=0,
                page_count=len(d.pages),
                doc_type=d.doc_type,
                doc_type_confidence=1.0,
                classifier_source="fixture",
                label=d.label,
                uploaded_at=datetime.now(timezone.utc).isoformat(),
            )
            for d in fixture.documents
        ]
        checklist = cdd_requirements.build_checklist(
            entities=[
                _fixture_entity_to_ref(e) for e in fixture.entities
            ],
            edges=[
                _fixture_edge_to_ref(e) for e in fixture.edges
            ],
            documents=uploaded,
            resolved_ubos=resolved_ubos,
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
        memo_type=memo_type,
        memo_sections=memo_sections,
        risk_level=fixture.answer_key.risk_level,
        agent_work_product=work_product,
        cdd_checklist=checklist,
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

        risk_level, memo_type = case_analyzer.infer_risk_and_memo_type(
            resolved_ubos, synthetic_fixture.entities
        )
        # Rewrite answer_key so downstream consumers stay consistent.
        synthetic_fixture.answer_key.risk_level = risk_level
        synthetic_fixture.answer_key.memo_type = memo_type

        graph_nodes, graph_edges = graph_builder.build(synthetic_fixture, resolved_ubos)
        work_product = reasoning_writer.build_work_product(
            synthetic_fixture, resolved_ubos, risk_level_override=risk_level
        )

        if memo_type == "full_edd":
            memo_sections = await claude_client.draft_full_edd_memo(
                synthetic_fixture, resolved_ubos
            )
        else:
            memo_sections = await claude_client.draft_ubo_resolution_memo(
                synthetic_fixture, resolved_ubos
            )

        checklist = cdd_requirements.build_checklist(
            entities=case.extracted_entities,
            edges=case.extracted_edges,
            documents=case.documents,
            resolved_ubos=resolved_ubos,
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
        memo_type=memo_type,
        memo_sections=memo_sections,
        risk_level=risk_level,
        agent_work_product=work_product,
        cdd_checklist=checklist,
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
# Approve + audit
# ---------------------------------------------------------------------------

@router.post("/edd/approve", response_model=ApproveResponse)
async def approve(request: ApproveRequest) -> ApproveResponse:
    if request.fixture_id:
        fixture = fixtures.get_fixture(request.fixture_id)
        risk = fixture.answer_key.risk_level
        case_label = fixture.label
    elif request.case_id:
        case = case_store.get_case_internal(request.case_id)
        risk = case.last_analysis.risk_level if case.last_analysis else "unknown"
        case_label = case.applicant_name or case.name
    else:
        raise HTTPException(
            status_code=400, detail="Provide either fixture_id or case_id."
        )

    entry = AuditEntry(
        entry_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        event="DRAFT_APPROVED",
        case_id=request.case_id,
        fixture_id=request.fixture_id,
        case_label=case_label,
        approved_by=request.approved_by,
        risk_level=risk,
        conclusion=request.conclusion,
    )
    _audit_log.append(entry)
    logger.info(
        "Audit: %s approved %s (risk=%s conclusion=%s)",
        request.approved_by,
        request.fixture_id or request.case_id,
        risk,
        request.conclusion,
    )
    return ApproveResponse(entry=entry)


@router.get("/edd/audit", response_model=AuditLogResponse)
async def get_audit_log() -> AuditLogResponse:
    return AuditLogResponse(entries=list(reversed(_audit_log)))
