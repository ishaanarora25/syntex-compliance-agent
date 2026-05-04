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
# Justification (replaces formal UBO/EDD memo) + Escalation
# ---------------------------------------------------------------------------

class JustificationSection(BaseModel):
    """One section of the agent's intake justification.

    Replaces the legacy formal compliance memo. Justification sections explain
    WHY the agent did what it did: how ownership was deduced, why each
    requested document is required, and (when present) why escalation was
    recommended.
    """
    section_id: str
    title: str
    content: str
    citations: List[Citation]


# Backwards-compatible alias — internal code (claude_client, verifier, fixtures)
# still references MemoSection by name. Structurally identical to
# JustificationSection.
MemoSection = JustificationSection


class EscalationRecommendation(BaseModel):
    """Agent-issued recommendation that a case requires human compliance review."""
    escalated: bool
    reasons: List[str] = []
    complexity_signals: List[str] = []
    recommended_team: Optional[str] = None
    recorded_at: str


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
    justification_sections: List[JustificationSection] = []
    risk_level: str
    agent_work_product: AgentWorkProduct
    cdd_checklist: CDDChecklist
    escalation: Optional[EscalationRecommendation] = None
    processing_ms: int
    agent_trace: Optional["AgentTrace"] = None      # populated by the agent loop only
    verifier_report: Optional["VerifierReport"] = None
    fincen_citations: List["Citation"] = []         # citations resolved against FinCEN digest


# ---------------------------------------------------------------------------
# Agent loop — scratchpad, trace, verifier
# ---------------------------------------------------------------------------

class RequestedDoc(BaseModel):
    """A document the agent requested but is not yet uploaded."""
    requirement_id: str
    label: str
    rationale: str
    applies_to_entity_id: Optional[str] = None
    requested_at: str


class AgentToolCall(BaseModel):
    """Single tool invocation captured for the trace."""
    iteration: int
    tool_use_id: str
    name: str
    input: dict
    output_summary: str          # human-readable, capped (~600 chars)
    is_error: bool = False
    duration_ms: int = 0


class AgentTrace(BaseModel):
    """Ordered record of every tool call the agent made, plus terminal state."""
    iterations: int
    tool_calls: List[AgentToolCall]
    stop_reason: str             # "finalized" | "max_iterations" | "error"
    revision_rounds: int = 0


class AgentScratchpad(BaseModel):
    """
    Persistent per-case agent memory.

    Survives across upload-driven re-analyses so a follow-up run can see what
    the agent asked for previously and acknowledge satisfied requests.
    """
    notes: List[str] = []
    requested_documents: List[RequestedDoc] = []
    fincen_lookups: List[str] = []        # tags the agent has consulted
    iteration_count: int = 0              # cumulative across runs
    last_trace: Optional[AgentTrace] = None
    escalation: Optional[EscalationRecommendation] = None


class VerifierFinding(BaseModel):
    section_id: Optional[str] = None
    issue: str                            # description of the issue
    severity: str                         # "low" | "medium" | "high"


class VerifierReport(BaseModel):
    needs_revision: bool
    claims_unsupported: List[VerifierFinding] = []
    risks_unaddressed: List[VerifierFinding] = []
    citations_missing: List[VerifierFinding] = []
    summary: str = ""


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
    memo_type: Optional[str] = None  # legacy; no longer drives routing
    expected_escalation: bool = False
    expected_complexity_signals: List[str] = []


class Fixture(BaseModel):
    fixture_id: str
    label: str
    scenario: str
    description: str
    entities: List[FixtureEntity]
    edges: List[FixtureEdge]
    documents: List[FixtureDocument]
    answer_key: AnswerKey


# ---------------------------------------------------------------------------
# Application assessment (called from onboarding-manager webhook)
# ---------------------------------------------------------------------------

class WebhookAddress(BaseModel):
    street1: Optional[str] = None
    street2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None
    country: Optional[str] = None


class WebhookCompanyInfo(BaseModel):
    companyName: str
    entityType: Optional[str] = None
    countryOfFormation: Optional[str] = None
    stateOfFormation: Optional[str] = None
    formationDate: Optional[str] = None
    ein: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    fundingStage: Optional[str] = None
    fundingAmount: Optional[str] = None
    businessAddress: Optional[WebhookAddress] = None


class WebhookBeneficialOwner(BaseModel):
    id: str
    name: str
    dob: Optional[str] = None
    email: Optional[str] = None
    jobTitle: Optional[str] = None
    ownershipPercent: float = 0.0
    citizenship: Optional[str] = None
    isUSCitizen: Optional[bool] = None
    ssn: Optional[str] = None
    passportNumber: Optional[str] = None
    passportCountry: Optional[str] = None
    address: Optional[WebhookAddress] = None
    idDocumentUrl: Optional[str] = None
    idDocumentPath: Optional[str] = None


class WebhookDocument(BaseModel):
    id: str
    type: str
    fileName: Optional[str] = None
    fileSize: Optional[int] = None
    blobUrl: Optional[str] = None
    blobPath: Optional[str] = None
    contentType: Optional[str] = None
    status: Optional[str] = None


class WebhookRegulatedCheck(BaseModel):
    selectedCategories: List[str] = []
    isRegulated: bool = False
    confirmedNonRegulated: bool = False


class AssessApplicationRequest(BaseModel):
    """Mirrors the application.submitted webhook payload from the client portal."""
    applicationId: str
    applicantEmail: Optional[str] = None
    applicantPhone: Optional[str] = None
    companyInfo: WebhookCompanyInfo
    beneficialOwners: List[WebhookBeneficialOwner] = []
    regulatedCheck: Optional[WebhookRegulatedCheck] = None
    documents: List[WebhookDocument] = []


class Inconsistency(BaseModel):
    """A discrepancy or data-quality issue detected in the application."""
    field: str                          # e.g. "company_name", "owner_dob"
    severity: str                       # "low" | "medium" | "high"
    description: str                    # what's wrong, in plain English
    suggested_action: Optional[str] = None


class NameConsistencyResult(BaseModel):
    """Whether the company name on the application matches the formation document."""
    status: str                         # "consistent" | "minor_variation" | "mismatch" | "no_doc"
    applicant_name: str
    document_name: Optional[str] = None
    document_filename: Optional[str] = None
    similarity: Optional[float] = None  # 0..1
    notes: str
    checked_with_llm: bool = False


class KYBResult(BaseModel):
    """Stub Middesk-style KYB / business-verification result."""
    provider: str = "Middesk"
    company_name: str
    status: str                         # "verified" | "not_found" | "warning" | "failed"
    secretary_of_state_status: Optional[str] = None  # e.g. "Active", "In Good Standing"
    formation_state: Optional[str] = None
    formation_date: Optional[str] = None
    ein_match: Optional[bool] = None
    registered_agent: Optional[str] = None
    watchlists_hit: List[str] = []
    tin_match_status: Optional[str] = None
    business_address_verified: Optional[bool] = None
    findings: List[str] = []
    raw_score: Optional[float] = None
    checked_at: str
    remarks: str


class KYCResult(BaseModel):
    """Stub Socure-style identity verification + fraud screening."""
    provider: str = "Socure"
    entity_id: str
    name: str
    overall_status: str                 # "pass" | "review" | "fail"
    id_verification_score: Optional[float] = None     # 0..1, Socure DocV
    sigma_fraud_score: Optional[float] = None         # 0..1, Socure Sigma
    address_risk_score: Optional[float] = None
    email_risk_score: Optional[float] = None
    phone_risk_score: Optional[float] = None
    synthetic_id_risk: Optional[str] = None           # "low" | "medium" | "high"
    document_authenticity: Optional[str] = None       # "authentic" | "indeterminate" | "forged"
    selfie_match: Optional[bool] = None
    findings: List[str] = []
    checked_at: str
    remarks: str


class BusinessRiskAssessment(BaseModel):
    """Risk assessment based on industry, NAICS, jurisdiction, etc."""
    risk_level: str                     # "low" | "medium" | "high" | "critical"
    is_foreign_entity: bool
    is_high_risk_industry: bool
    is_regulated: bool
    naics_code: Optional[str] = None
    naics_title: Optional[str] = None
    risk_factors: List[str]
    rationale: str


class UBOCompletenessResult(BaseModel):
    """Audit of the self-attested beneficial-ownership form."""
    total_ownership_pct: float
    declared_owner_count: int
    above_threshold_count: int           # owners ≥ 25%
    coverage_status: str                 # "complete" | "incomplete" | "over_allocated"
    gaps: List[str]                      # e.g. "26% of ownership unaccounted for"
    follow_up_questions: List[str]


class RecommendedDocument(BaseModel):
    """A piece of additional documentation the BSA team should request."""
    label: str
    rationale: str
    priority: str                        # "required" | "recommended" | "optional"
    triggered_by: List[str] = []         # short tags identifying which risk drove this


class ApplicationAssessment(BaseModel):
    application_id: str
    applicant_email: Optional[str]
    company_name: str
    assessed_at: str
    processing_ms: int

    overall_risk: str                    # "low" | "medium" | "high" | "critical"
    risk_summary: str

    name_consistency: NameConsistencyResult
    data_inconsistencies: List[Inconsistency]
    business_risk: BusinessRiskAssessment
    ubo_completeness: UBOCompletenessResult

    kyb_result: KYBResult
    kyc_results: List[KYCResult]
    sanctions_screening: List[ScreeningBundle]

    recommended_documents: List[RecommendedDocument]
    follow_up_questions: List[str]


class AssessApplicationResponse(BaseModel):
    assessment: ApplicationAssessment


# Resolve forward refs added when AnalyzeResponse referenced AgentTrace / VerifierReport
AnalyzeResponse.model_rebuild()
