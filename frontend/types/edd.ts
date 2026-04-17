// TypeScript interfaces mirroring the FastAPI Pydantic models

export interface Citation {
  doc_id: string;
  page: number;
  excerpt: string;
  doc_label: string;
}

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

export interface GraphNode {
  id: string;
  node_type: "company" | "trust" | "individual" | "ubo";
  label: string;
  entity_type: string;
  jurisdiction: string;
  is_ubo: boolean;
  risk_flags: string[];
  ofac_status?: "clear" | "potential_match" | "confirmed_hit";
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

export interface AnalyzeResponse {
  fixture_id: string;
  scenario: string;
  resolved_ubos: ResolvedUBO[];
  graph_nodes: GraphNode[];
  graph_edges: GraphEdge[];
  memo_type: "ubo_resolution" | "full_edd";
  memo_sections: MemoSection[];
  risk_level: "low" | "medium" | "high";
  agent_work_product: AgentWorkProduct;
  processing_ms: number;
}

export interface AuditEntry {
  entry_id: string;
  timestamp: string;
  event: string;
  fixture_id: string;
  fixture_label: string;
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
