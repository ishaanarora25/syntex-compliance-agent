// TypeScript interfaces mirroring the FastAPI Pydantic models

export interface Citation {
  doc_id: string;
  page: number;
  excerpt: string;
  doc_label: string;
}

export type ScreeningStatus = "clear" | "potential_match" | "confirmed_hit" | "confirmed_pep";

export interface OFACResult {
  entity_id: string;
  name: string;
  status: "clear" | "potential_match" | "confirmed_hit";
  match_score?: number;
  sdn_name?: string;
  program?: string;
  list_type?: string;
  remarks?: string;
  checked_at: string;
}

export interface PEPResult {
  entity_id: string;
  name: string;
  status: "clear" | "potential_match" | "confirmed_pep";
  match_score?: number;
  role?: string;
  country?: string;
  category?: string;
  source?: string;
  remarks?: string;
  checked_at: string;
}

export interface AdverseMediaArticle {
  headline: string;
  source: string;
  date: string;
  url?: string;
  disposition?: string;
}

export interface AdverseMediaResult {
  entity_id: string;
  name: string;
  status: "clear" | "potential_match" | "confirmed_hit";
  categories: string[];
  articles: AdverseMediaArticle[];
  severity?: "low" | "medium" | "high";
  remarks?: string;
  checked_at: string;
}

export interface GraphNode {
  id: string;
  node_type: "company" | "trust" | "individual" | "ubo";
  label: string;
  entity_type: string;
  jurisdiction: string;
  is_ubo: boolean;
  risk_flags: string[];
  ofac_status?: OFACResult["status"];
  pep_status?: PEPResult["status"];
  adverse_media_status?: AdverseMediaResult["status"];
  position: { x: number; y: number };
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  ownership_pct: number;
  citations: Citation[];
  edge_type: "direct" | "through_trust" | "look_through";
}

export interface ResolvedUBO {
  entity_id: string;
  name: string;
  nationality: string;
  ownership_pct: number;
  path: string[];
  risk_flags: string[];
  citations: Citation[];
  ofac_result: OFACResult;
  pep_result: PEPResult;
  adverse_media_result: AdverseMediaResult;
  ubo_by_control: boolean;
}

export interface MemoSection {
  section_id: string;
  title: string;
  content: string;
  citations: Citation[];
}

export interface AgentReasoningStep {
  step_number: number;
  category:
    | "document_review"
    | "entity_extraction"
    | "ownership_mapping"
    | "trust_analysis"
    | "ubo_calculation"
    | "ofac_screening"
    | "screening"
    | "risk_assessment"
    | "conclusion";
  title: string;
  detail: string;
  outcome: string;
}

export interface AgentWorkProduct {
  steps: AgentReasoningStep[];
  summary: string;
  conclusion: string;
  total_ubos_resolved: number;
  risk_flags_found: string[];
}

export interface RequiredDocument {
  requirement_id: string;
  label: string;
  rationale: string;
  status: "missing" | "provided" | "not_applicable";
  provided_by: string[];
  applies_to_entity_id?: string;
}

export interface CDDChecklist {
  items: RequiredDocument[];
  missing_count: number;
  satisfied_count: number;
  blocking_for_ubo_resolution: boolean;
}

export interface UploadedDocumentMeta {
  doc_id: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  doc_type: string;
  doc_type_confidence: number;
  classifier_source: "heuristic" | "claude" | "fixture";
  label: string;
  uploaded_at: string;
}

export interface ExtractedEntityRef {
  entity_id: string;
  label: string;
  entity_type: "company" | "trust" | "individual";
  entity_subtype?: string | null;
  jurisdiction: string;
  nationality?: string | null;
  is_root: boolean;
  has_control_rights: boolean;
  risk_flags: string[];
  source_doc_ids: string[];
  grantor_ids?: string[] | null;
  grantor_pcts?: Record<string, number> | null;
  beneficiary_ids?: string[] | null;
  beneficiary_pcts?: Record<string, number> | null;
  discretionary: boolean;
}

export interface ExtractedEdge {
  edge_id: string;
  source: string;
  target: string;
  ownership_pct: number;
  doc_id: string;
  page: number;
  excerpt: string;
}

export interface CaseSummary {
  case_id: string;
  name: string;
  status:
    | "awaiting_documents"
    | "ready_to_analyze"
    | "analyzing"
    | "analyzed"
    | "approved";
  created_at: string;
  updated_at: string;
  document_count: number;
  last_analysis_at?: string;
}

export interface CaseDetail extends CaseSummary {
  documents: UploadedDocumentMeta[];
  extracted_entities: ExtractedEntityRef[];
  extracted_edges: ExtractedEdge[];
}

export interface AnalyzeResponse {
  case_id?: string;
  fixture_id?: string;
  scenario: string;
  applicant_name: string;
  resolved_ubos: ResolvedUBO[];
  graph_nodes: GraphNode[];
  graph_edges: GraphEdge[];
  memo_type: "ubo_resolution" | "full_edd";
  memo_sections: MemoSection[];
  risk_level: "low" | "medium" | "high" | "pending";
  agent_work_product: AgentWorkProduct;
  cdd_checklist: CDDChecklist;
  processing_ms: number;
}

export interface AuditEntry {
  entry_id: string;
  timestamp: string;
  event: string;
  case_id?: string;
  fixture_id?: string;
  case_label: string;
  approved_by: string;
  risk_level: string;
  conclusion: string;
}

export interface FixtureMeta {
  fixture_id: string;
  label: string;
  scenario: string;
  description: string;
}

export interface UploadDocumentsResponse {
  case: CaseSummary;
  documents: UploadedDocumentMeta[];
  extracted_entities: ExtractedEntityRef[];
  extracted_edges: ExtractedEdge[];
}
