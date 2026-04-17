"""
Pydantic request/response models for the EDD service.
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
    match_score: Optional[float] = None       # 0.0–1.0 for fuzzy matches
    sdn_name: Optional[str] = None            # matched entry name on list
    program: Optional[str] = None             # OFAC sanctions program
    list_type: Optional[str] = None           # "SDN" | "Consolidated" | null
    remarks: Optional[str] = None
    checked_at: str                           # ISO 8601 timestamp


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
    entity_type: str    # "LLC" | "GmbH" | "LP" | "Revocable Trust" | "Irrevocable Trust" | "Individual"
    jurisdiction: str
    is_ubo: bool
    risk_flags: List[str]
    ofac_status: Optional[str] = None   # "clear" | "potential_match" | "confirmed_hit"
    position: Dict[str, float]           # {"x": float, "y": float}


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
    ownership_pct: float        # effective % through all paths; -1.0 = UBO by control only
    path: List[str]             # entity_ids from root to this UBO
    risk_flags: List[str]
    citations: List[Citation]
    ofac_result: OFACResult
    ubo_by_control: bool = False


# ---------------------------------------------------------------------------
# Memo
# ---------------------------------------------------------------------------

class MemoSection(BaseModel):
    section_id: str
    title: str
    content: str            # prose with [N] citation markers
    citations: List[Citation]


# ---------------------------------------------------------------------------
# Agent reasoning / work product
# ---------------------------------------------------------------------------

class AgentReasoningStep(BaseModel):
    step_number: int
    # "document_review" | "entity_extraction" | "ownership_mapping" |
    # "trust_analysis" | "ubo_calculation" | "ofac_screening" |
    # "risk_assessment" | "conclusion"
    category: str
    title: str
    detail: str
    outcome: str


class AgentWorkProduct(BaseModel):
    """Structured narrative of every step the agent took — for BSA officer review."""
    steps: List[AgentReasoningStep]
    summary: str
    # "Recommend Approval" | "Escalate for EDD Review" | "Refer to Compliance"
    conclusion: str
    total_ubos_resolved: int
    risk_flags_found: List[str]


# ---------------------------------------------------------------------------
# Core API shapes
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    fixture_id: str


class AnalyzeResponse(BaseModel):
    fixture_id: str
    scenario: str               # "A" | "B" | "stress_c" | "stress_d"
    resolved_ubos: List[ResolvedUBO]
    graph_nodes: List[GraphNode]
    graph_edges: List[GraphEdge]
    memo_type: str              # "ubo_resolution" | "full_edd"
    memo_sections: List[MemoSection]
    risk_level: str             # "low" | "medium" | "high"
    agent_work_product: AgentWorkProduct
    processing_ms: int


class ApproveRequest(BaseModel):
    fixture_id: str
    approved_by: str
    memo_snapshot: List[MemoSection]
    conclusion: str


class AuditEntry(BaseModel):
    entry_id: str
    timestamp: str
    event: str          # "DRAFT_APPROVED"
    fixture_id: str
    fixture_label: str
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
    scenario: str       # "A" | "B" | "stress_c" | "stress_d"
    description: str


class FixtureListResponse(BaseModel):
    fixtures: List[FixtureMeta]


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
    entity_type: str                    # "company" | "trust" | "individual"
    entity_subtype: Optional[str]       # "LLC" | "GmbH" | "LP" | "revocable_trust" | "irrevocable_trust"
    jurisdiction: str
    nationality: Optional[str] = None   # for individuals
    is_root: bool = False
    has_control_rights: bool = False
    risk_flags: List[str] = []
    adverse_media: Optional[Dict[str, Any]] = None
    # Trust-specific fields
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
