"""
In-memory case store for the BSA copilot.

A "case" is a single applicant file: a bundle of uploaded documents, the
structured ownership graph derived from them, and the last analysis run.
Cases are lost on process restart — that's fine for the demo surface area,
and mirrors the existing in-memory audit log pattern.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.exceptions import EDDServiceError
from app.models import (
    AgentScratchpad,
    AnalyzeResponse,
    CaseDetail,
    CaseSummary,
    EscalationRecommendation,
    ExtractedEdge,
    ExtractedEntityRef,
    RequestedDoc,
    UploadedDocumentMeta,
)
from app.services.pdf_extractor import ExtractedPDF

logger = logging.getLogger(__name__)


class CaseNotFoundError(EDDServiceError):
    def __init__(self, case_id: str) -> None:
        super().__init__(
            detail="case_not_found",
            message=f"No case found with ID '{case_id}'.",
            status_code=404,
        )


@dataclass
class _Case:
    case_id: str
    name: str
    status: str
    created_at: str
    updated_at: str
    documents: List[UploadedDocumentMeta] = field(default_factory=list)
    pdfs: Dict[str, ExtractedPDF] = field(default_factory=dict)  # doc_id -> extracted pages
    extracted_entities: List[ExtractedEntityRef] = field(default_factory=list)
    extracted_edges: List[ExtractedEdge] = field(default_factory=list)
    applicant_name: str = ""
    last_analysis: Optional[AnalyzeResponse] = None
    last_analysis_at: Optional[str] = None
    scratchpad: AgentScratchpad = field(default_factory=AgentScratchpad)


_store: Dict[str, _Case] = {}
_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_summary(case: _Case) -> CaseSummary:
    return CaseSummary(
        case_id=case.case_id,
        name=case.name,
        status=case.status,
        created_at=case.created_at,
        updated_at=case.updated_at,
        document_count=len(case.documents),
        last_analysis_at=case.last_analysis_at,
    )


def create_case(name: str) -> CaseSummary:
    with _lock:
        case_id = f"case_{uuid.uuid4().hex[:10]}"
        now = _now()
        case = _Case(
            case_id=case_id,
            name=name or "Untitled Case",
            status="awaiting_documents",
            created_at=now,
            updated_at=now,
        )
        _store[case_id] = case
        logger.info("Created case %s", case_id)
        return _as_summary(case)


def get_case(case_id: str) -> CaseDetail:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        summary = _as_summary(case)
        return CaseDetail(
            **summary.model_dump(),
            documents=list(case.documents),
            extracted_entities=list(case.extracted_entities),
            extracted_edges=list(case.extracted_edges),
        )


def list_cases() -> List[CaseSummary]:
    with _lock:
        return [
            _as_summary(c)
            for c in sorted(_store.values(), key=lambda c: c.updated_at, reverse=True)
        ]


def add_documents(
    case_id: str,
    documents: List[UploadedDocumentMeta],
    pdfs: Dict[str, ExtractedPDF],
) -> CaseSummary:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        case.documents.extend(documents)
        case.pdfs.update(pdfs)
        case.status = "ready_to_analyze"
        case.updated_at = _now()
        return _as_summary(case)


def set_graph(
    case_id: str,
    applicant_name: str,
    entities: List[ExtractedEntityRef],
    edges: List[ExtractedEdge],
) -> None:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        case.applicant_name = applicant_name
        case.extracted_entities = list(entities)
        case.extracted_edges = list(edges)
        case.updated_at = _now()


def mark_analyzing(case_id: str) -> None:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        case.status = "analyzing"
        case.updated_at = _now()


def store_analysis(case_id: str, response: AnalyzeResponse) -> None:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        case.last_analysis = response
        case.last_analysis_at = _now()
        case.status = "analyzed"
        case.updated_at = case.last_analysis_at


def get_case_internal(case_id: str) -> _Case:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        return case


def delete_case(case_id: str) -> None:
    with _lock:
        _store.pop(case_id, None)


# ---------------------------------------------------------------------------
# Agent scratchpad operations
# ---------------------------------------------------------------------------

def get_scratchpad(case_id: str) -> AgentScratchpad:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        return case.scratchpad.model_copy(deep=True)


def update_scratchpad(case_id: str, scratchpad: AgentScratchpad) -> None:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        case.scratchpad = scratchpad
        case.updated_at = _now()


def append_note(case_id: str, note: str) -> None:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        case.scratchpad.notes.append(note)
        case.updated_at = _now()


def set_escalation(case_id: str, escalation: EscalationRecommendation) -> None:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        case.scratchpad.escalation = escalation
        case.updated_at = _now()


def add_requested_document(case_id: str, doc: RequestedDoc) -> None:
    with _lock:
        case = _store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        # Deduplicate on (label, applies_to_entity_id)
        for existing in case.scratchpad.requested_documents:
            if (
                existing.label == doc.label
                and existing.applies_to_entity_id == doc.applies_to_entity_id
            ):
                return
        case.scratchpad.requested_documents.append(doc)
        case.updated_at = _now()
