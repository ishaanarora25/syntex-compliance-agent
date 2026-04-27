"""
Pydantic request/response models for the EDD / BSA-Copilot service.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

class Citation(BaseModel):
    doc_id: str
    page: int
    excerpt: str
    doc_label: str


class OFACResult(BaseModel):
    """Result of an OFAC/SDN stub screening for a single individual."""
    entity_id: str
    name: str
    # "clear" | "potential_match" | "confirmed_hit"
    status: str
    match_score: Optional[float] = None
    sdn_name: Optional[str] = None
    program: Optional[str] = None
    list_type: Optional[str] = None
    remarks: Optional[str] = None
    checked_at: str


class PEPResult(BaseModel):
    """Politically Exposed Persons screening — stubbed."""
    entity_id: str
    name: str
    # "clear" | "potential_match" | "confirmed_pep"
    status: str
    match_score: Optional[float] = None
    role: Optional[str] = None                  # e.g. "Minister of Finance"
    country: Optional[str] = None
    category: Optional[str] = None              # "domestic" | "foreign" | "international_organization" | "family_associate"
    source: Optional[str] = None                # "World-Check" | "Dow Jones" | stub label
    remarks: Optional[str] = None
    checked_at: str


class AdverseMediaResult(BaseModel):
    """Adverse media screening — stubbed."""
    entity_id: str
    name: str
    # "clear" | "potential_match" | "confirmed_hit"
    status: str
    categories: List[str] = []                  # "financial_crime", "corruption", "violence", "regulatory"
    articles: List[Dict[str, Any]] = []         # {headline, source, date, url, disposition}
    severity: Optional[str] = None              # "low" | "medium" | "high"
    remarks: Optional[str] = None
    checked_at: str


class ScreeningBundle(BaseModel):
    """All three screenings rolled up per individual."""
    entity_id: str
    name: str
    ofac: OFACResult
    pep: PEPResult
    adverse_media: AdverseMediaResult


# ---------------------------------------------------------------------------
# Graph schema (React Flow)
# ---------------------------------------------------------------------------

class GraphNodePosition(BaseModel):
    x: float
    y: float


class GraphNode(BaseModel):
    id: str
    node_type: str      # "company" | "trust" | "individual" | "ubo"
    label: str
    entity_type: str
    jurisdiction: str
    is_ubo: bool
    risk_flags: List[str]
    ofac_status: Optional[str] = None
    pep_status: Optional[str] = None
    adverse_media_status: Optional[str] = None
    position: Dict[str, float]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    ownership_pct: float
    citations: List[Citation]
    edge_type: str  # "direct" | "through_trust" | "look_through"


# ---------------------------------------------------------------------------
# UBO resolution
# ---------------------------------------------------------------------------

class ResolvedUBO(BaseModel):
    entity_id: str
    name: str
    nationality: str
    ownership_pct: float
    path: List[str]
    risk_flags: List[str]
    citations: List[Citation]
    ofac_result: OFACResult
    pep_result: PEPResult
    adverse_media_result: AdverseMediaResult
    ubo_by_control: bool = False


# ---------------------------------------------------------------------------
# Memo
# ---------------------------------------------------------------------------

class MemoSection(BaseModel):
    section_id: str
    title: str
    content: str
    citations: List[Citation]


# ---------------------------------------------------------------------------
# Agent reasoning / work product
# ---------------------------------------------------------------------------

class AgentReasoningStep(BaseModel):
    step_number: int
    category: str
    title: str
    detail: str
    outcome: str


class AgentWorkProduct(BaseModel):
    steps: List[AgentReasoningStep]
    summary: str
    conclusion: str
    total_ubos_resolved: int
    risk_flags_found: List[str]


# ---------------------------------------------------------------------------
# CDD document requirements
# ---------------------------------------------------------------------------

class RequiredDocument(BaseModel):
    """One line item on the CDD document checklist."""
    requirement_id: str
    label: str
    rationale: str
    # "missing" | "provided" | "not_applicable"
    status: str
    provided_by: List[str] = []                 # doc_ids that satisfy the requirement
    applies_to_entity_id: Optional[str] = None


class CDDChecklist(BaseModel):
    items: List[RequiredDocument]
    missing_count: int
    satisfied_count: int
    blocking_for_ubo_resolution: bool


# ---------------------------------------------------------------------------
# Case / upload flow
# ---------------------------------------------------------------------------

class UploadedDocumentMeta(BaseModel):
    doc_id: str
    filename: str
    size_bytes: int
    page_count: int
    # "articles_of_organization" | "operating_agreement" | "trust_agreement" |
    # "limited_partnership_agreement" | "commercial_register_extract" |
    # "certificate_of_incorporation" | "adverse_media_report" |
    # "identity_document" | "other"
    doc_type: str
    doc_type_confidence: float
    classifier_source: str                      # "heuristic" | "claude"
    label: str                                  # human-friendly derived title
    uploaded_at: str


class ExtractedEntityRef(BaseModel):
    """Entity lifted from uploaded PDFs before UBO resolution runs."""
    entity_id: str
    label: str
    entity_type: str                            # "company" | "trust" | "individual"
    entity_subtype: Optional[str] = None
    jurisdiction: str
    nationality: Optional[str] = None
    is_root: bool = False
    has_control_rights: bool = False
    risk_flags: List[str] = []
    source_doc_ids: List[str] = []
    # Trust-specific
    grantor_ids: Optional[List[str]] = None
    grantor_pcts: Optional[Dict[str, float]] = None
    beneficiary_ids: Optional[List[str]] = None
    beneficiary_pcts: Optional[Dict[str, float]] = None
    discretionary: bool = False


class ExtractedEdge(BaseModel):
    edge_id: str
    source: str
    target: str
    ownership_pct: float
    doc_id: str
    page: int
    excerpt: str


class CaseSummary(BaseModel):
    case_id: str
    name: str
    status: str                                 # "awaiting_documents" | "ready_to_analyze" | "analyzing" | "analyzed" | "approved"
    created_at: str
    updated_at: str
    document_count: int
    last_analysis_at: Optional[str] = None


class CaseDetail(CaseSummary):
    documents: List[UploadedDocumentMeta]
    extracted_entities: List[ExtractedEntityRef]
    extracted_edges: List[ExtractedEdge]


# ---------------------------------------------------------------------------
# Core API shapes
# ---------------------------------------------------------------------------

class CreateCaseRequest(BaseModel):
    name: str


class CreateCaseResponse(BaseModel):
    case: CaseSummary


class UploadDocumentsResponse(BaseModel):
    case: CaseSummary
    documents: List[UploadedDocumentMeta]
    extracted_entities: List[ExtractedEntityRef]
    extracted_edges: List[ExtractedEdge]


class AnalyzeRequest(BaseModel):
    # One of the two must be provided.
    fixture_id: Optional[str] = None
    case_id: Optional[str] = None


class AnalyzeResponse(BaseModel):
    case_id: Optional[str] = None
    fixture_id: Optional[str] = None
    scenario: str
    applicant_name: str
    resolved_ubos: List[ResolvedUBO]
    graph_nodes: List[GraphNode]
    graph_edges: List[GraphEdge]
    memo_type: str
    memo_sections: List[MemoSection]
    risk_level: str
    agent_work_product: AgentWorkProduct
    cdd_checklist: CDDChecklist
    processing_ms: int


class ApproveRequest(BaseModel):
    fixture_id: Optional[str] = None
    case_id: Optional[str] = None
    approved_by: str
    memo_snapshot: List[MemoSection]
    conclusion: str


class AuditEntry(BaseModel):
    entry_id: str
    timestamp: str
    event: str          # "DRAFT_APPROVED"
    case_id: Optional[str] = None
    fixture_id: Optional[str] = None
    case_label: str
    approved_by: str
    risk_level: str
    conclusion: str


class ApproveResponse(BaseModel):
    entry: AuditEntry


class AuditLogResponse(BaseModel):
    entries: List[AuditEntry]


class FixtureMeta(BaseModel):
    fixture_id: str
    label: str
    scenario: str
    description: str


class FixtureListResponse(BaseModel):
    fixtures: List[FixtureMeta]


class CaseListResponse(BaseModel):
    cases: List[CaseSummary]


# ---------------------------------------------------------------------------
# Internal fixture schema (loaded from JSON)
# ---------------------------------------------------------------------------

class FixturePage(BaseModel):
    page: int
    text: str


class FixtureDocument(BaseModel):
    doc_id: str
    label: str
    doc_type: str
    pages: List[FixturePage]


class FixtureEntity(BaseModel):
    entity_id: str
    label: str
    entity_type: str
    entity_subtype: Optional[str]
    jurisdiction: str
    nationality: Optional[str] = None
    is_root: bool = False
    has_control_rights: bool = False
    risk_flags: List[str] = []
    adverse_media: Optional[Dict[str, Any]] = None
    grantor_ids: Optional[List[str]] = None
    grantor_pcts: Optional[Dict[str, float]] = None
    beneficiary_ids: Optional[List[str]] = None
    beneficiary_pcts: Optional[Dict[str, float]] = None
    discretionary: bool = False


class FixtureEdge(BaseModel):
    edge_id: str
    source: str
    target: str
    ownership_pct: float
    doc_id: str
    page: int


class AnswerKey(BaseModel):
    resolved_ubos: List[Dict[str, Any]]
    risk_level: str
    memo_type: str


class Fixture(BaseModel):
    fixture_id: str
    label: str
    scenario: str
    description: str
    entities: List[FixtureEntity]
    edges: List[FixtureEdge]
    documents: List[FixtureDocument]
    answer_key: AnswerKey
