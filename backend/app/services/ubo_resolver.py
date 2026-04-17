"""
UBO resolver: DFS traversal of the ownership graph applying trust look-through
and the 25% beneficial ownership threshold per FinCEN CDD rules.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from app.models import (
    Citation,
    Fixture,
    FixtureEdge,
    FixtureEntity,
    OFACResult,
    ResolvedUBO,
)
from app.services import ofac_service
from app.services.trust_logic import (
    is_irrevocable,
    is_revocable,
    resolve_grantor_passthrough,
    resolve_irrevocable_controlling_parties,
    should_look_through,
)

logger = logging.getLogger(__name__)

UBO_THRESHOLD = 0.25


def _page_excerpt(fixture: Fixture, doc_id: str, page: int) -> str:
    """Pull up to 200 chars from the relevant fixture page for use as citation excerpt."""
    for doc in fixture.documents:
        if doc.doc_id == doc_id:
            for p in doc.pages:
                if p.page == page:
                    return p.text[:200].replace("\n", " ").strip()
    return ""


def _doc_label(fixture: Fixture, doc_id: str) -> str:
    for doc in fixture.documents:
        if doc.doc_id == doc_id:
            return doc.label
    return doc_id


def resolve(fixture: Fixture) -> List[ResolvedUBO]:
    """
    Resolve beneficial owners from the fixture.

    Steps:
    1. Build adjacency list (source → list of (target, edge)).
    2. Find root entity (is_root=True).
    3. DFS from root, accumulating effective ownership percentages.
    4. On trust nodes: apply revocable or irrevocable look-through.
    5. Aggregate % by individual across all paths.
    6. Filter: keep if aggregated_pct >= 25% OR has_control_rights.
    7. Screen each qualifying individual via OFAC stub.
    """
    entities_by_id: Dict[str, FixtureEntity] = {e.entity_id: e for e in fixture.entities}

    # Adjacency list: source_id → [(target_id, edge)]
    adj: Dict[str, List[Tuple[str, FixtureEdge]]] = defaultdict(list)
    for edge in fixture.edges:
        adj[edge.source].append((edge.target, edge))

    root = next((e for e in fixture.entities if e.is_root), None)
    if root is None:
        raise ValueError("Fixture has no root entity")

    # Accumulate: individual_id → (effective_pct, path, citations, control_only)
    accumulated: Dict[str, Dict] = {}

    def dfs(
        entity_id: str,
        accumulated_pct: float,
        path: List[str],
        citations: List[Citation],
        visited: Set[str],
    ) -> None:
        if entity_id in visited:
            return
        visited = visited | {entity_id}

        entity = entities_by_id.get(entity_id)
        if entity is None:
            return

        # Leaf: individual entity
        if entity.entity_type == "individual":
            existing = accumulated.get(entity_id)
            if existing:
                existing["pct"] += accumulated_pct
                existing["paths"].append(list(path))
                existing["citations"].extend(citations)
            else:
                accumulated[entity_id] = {
                    "pct": accumulated_pct,
                    "paths": [list(path)],
                    "citations": list(citations),
                    "control_only": False,
                }
            return

        # Trust node: apply look-through
        if should_look_through(entity):
            if is_revocable(entity):
                pass_through = resolve_grantor_passthrough(entity, entities_by_id, accumulated_pct)
                for grantor, eff_pct in pass_through:
                    dfs(grantor.entity_id, eff_pct, path + [grantor.entity_id], citations, visited)
                return

            if is_irrevocable(entity):
                controlling = resolve_irrevocable_controlling_parties(
                    entity, entities_by_id, accumulated_pct
                )
                for ctrl_entity, eff_pct, is_control_only in controlling:
                    existing = accumulated.get(ctrl_entity.entity_id)
                    new_citations = list(citations)
                    if existing:
                        if is_control_only:
                            existing["control_only"] = True
                        else:
                            existing["pct"] += eff_pct
                        existing["paths"].append(path + [ctrl_entity.entity_id])
                        existing["citations"].extend(new_citations)
                    else:
                        accumulated[ctrl_entity.entity_id] = {
                            "pct": 0.0 if is_control_only else eff_pct,
                            "paths": [path + [ctrl_entity.entity_id]],
                            "citations": new_citations,
                            "control_only": is_control_only,
                        }
                return

        # Company / LP / other: traverse children
        for target_id, edge in adj.get(entity_id, []):
            edge_pct = edge.ownership_pct / 100.0
            new_pct = accumulated_pct * edge_pct
            new_citation = Citation(
                doc_id=edge.doc_id,
                page=edge.page,
                excerpt=_page_excerpt(fixture, edge.doc_id, edge.page),
                doc_label=_doc_label(fixture, edge.doc_id),
            )
            dfs(target_id, new_pct, path + [target_id], citations + [new_citation], visited)

    # Start DFS from each direct child of root
    for target_id, edge in adj.get(root.entity_id, []):
        edge_pct = edge.ownership_pct / 100.0
        citation = Citation(
            doc_id=edge.doc_id,
            page=edge.page,
            excerpt=_page_excerpt(fixture, edge.doc_id, edge.page),
            doc_label=_doc_label(fixture, edge.doc_id),
        )
        dfs(target_id, edge_pct, [root.entity_id, target_id], [citation], set())

    # Filter and build ResolvedUBO list
    ubos: List[ResolvedUBO] = []
    for entity_id, data in accumulated.items():
        entity = entities_by_id[entity_id]
        pct = data["pct"]
        control_only = data["control_only"]
        qualifies = pct >= UBO_THRESHOLD or control_only or entity.has_control_rights

        if not qualifies:
            continue

        # OFAC screening
        ofac = ofac_service.screen(entity_id, entity.label)

        # Combine risk flags (deduplicate — fixture may already include some)
        risk_flags_set: set = set(entity.risk_flags)
        if entity.adverse_media:
            risk_flags_set.add("adverse_media")
        if entity.nationality and entity.nationality.upper() not in ("US", "USA"):
            risk_flags_set.add("foreign_national")
        if ofac.status == "potential_match":
            risk_flags_set.add("ofac_potential_match")
        elif ofac.status == "confirmed_hit":
            risk_flags_set.add("ofac_confirmed_hit")
        risk_flags = list(risk_flags_set)

        # Deduplicate citations
        seen_cit = set()
        unique_citations: List[Citation] = []
        for c in data["citations"]:
            key = (c.doc_id, c.page)
            if key not in seen_cit:
                seen_cit.add(key)
                unique_citations.append(c)

        # Use the longest path for display
        best_path = max(data["paths"], key=len)

        ubos.append(
            ResolvedUBO(
                entity_id=entity_id,
                name=entity.label,
                nationality=entity.nationality or "Unknown",
                ownership_pct=round(pct * 100, 2),
                path=best_path,
                risk_flags=risk_flags,
                citations=unique_citations,
                ofac_result=ofac,
                ubo_by_control=control_only or entity.has_control_rights,
            )
        )

    # Sort: highest risk first, then by ownership pct desc
    def sort_key(u: ResolvedUBO):
        risk_score = len(u.risk_flags) * 100 + u.ownership_pct
        return -risk_score

    ubos.sort(key=sort_key)
    logger.info("Resolved %d UBOs for fixture %s", len(ubos), fixture.fixture_id)
    return ubos
