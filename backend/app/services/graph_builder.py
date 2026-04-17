"""
Converts fixture entities/edges + resolved UBOs into React Flow graph schema
with BFS-computed node positions.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

from app.models import (
    Citation,
    Fixture,
    GraphEdge,
    GraphNode,
    ResolvedUBO,
)

logger = logging.getLogger(__name__)

_SUBTYPE_DISPLAY = {
    "LLC": "LLC",
    "GmbH": "GmbH",
    "LP": "LP",
    "Corp": "Corp",
    "Ltd": "Ltd",
    "revocable_trust": "Revocable Trust",
    "irrevocable_trust": "Irrevocable Trust",
    None: "Entity",
}

_LEVEL_Y_SPACING = 180
_SIBLING_X_SPACING = 280


def _entity_type_display(entity_subtype: str | None) -> str:
    return _SUBTYPE_DISPLAY.get(entity_subtype, entity_subtype or "Entity")


def _node_type(entity_type: str, is_ubo: bool) -> str:
    if is_ubo:
        return "ubo"
    if entity_type == "trust":
        return "trust"
    if entity_type == "individual":
        return "individual"
    return "company"


def _page_excerpt(fixture: Fixture, doc_id: str, page: int) -> str:
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


def build(fixture: Fixture, resolved_ubos: List[ResolvedUBO]) -> Tuple[List[GraphNode], List[GraphEdge]]:
    """
    Build React Flow nodes and edges with BFS-computed positions.
    Also injects synthetic look-through edges for trust nodes.
    """
    entities_by_id = {e.entity_id: e for e in fixture.entities}
    ubo_ids: Set[str] = {u.entity_id for u in resolved_ubos}

    # Build adjacency (source → list[target])
    adj: Dict[str, List[str]] = defaultdict(list)
    for edge in fixture.edges:
        adj[edge.source].append(edge.target)

    root = next((e for e in fixture.entities if e.is_root), None)
    if root is None:
        return [], []

    # BFS to compute levels and sibling order
    levels: Dict[str, int] = {root.entity_id: 0}
    sibling_order: Dict[str, int] = {root.entity_id: 0}
    siblings_at_level: Dict[int, List[str]] = defaultdict(list)
    siblings_at_level[0].append(root.entity_id)

    queue = deque([root.entity_id])
    visited: Set[str] = {root.entity_id}

    while queue:
        node_id = queue.popleft()
        entity = entities_by_id.get(node_id)
        if entity is None:
            continue

        children = list(adj.get(node_id, []))

        # For trust nodes, add look-through children
        if entity.entity_type == "trust":
            through_ids: List[str] = []
            if entity.grantor_ids:
                through_ids.extend(entity.grantor_ids)
            if entity.beneficiary_ids:
                through_ids.extend(entity.beneficiary_ids)
            children = through_ids  # replace with look-through targets

        current_level = levels[node_id]
        for i, child_id in enumerate(children):
            if child_id not in visited:
                visited.add(child_id)
                levels[child_id] = current_level + 1
                siblings_at_level[current_level + 1].append(child_id)
                sibling_order[child_id] = len(siblings_at_level[current_level + 1]) - 1
                queue.append(child_id)

    # Compute x positions per level (centered)
    def _x_pos(entity_id: str) -> float:
        level = levels.get(entity_id, 0)
        siblings = siblings_at_level[level]
        idx = siblings.index(entity_id) if entity_id in siblings else 0
        count = len(siblings)
        return (idx - (count - 1) / 2.0) * _SIBLING_X_SPACING

    def _y_pos(entity_id: str) -> float:
        return levels.get(entity_id, 0) * _LEVEL_Y_SPACING

    # Build nodes
    nodes: List[GraphNode] = []
    for entity_id in visited:
        entity = entities_by_id.get(entity_id)
        if entity is None:
            continue

        is_ubo = entity_id in ubo_ids
        ubo = next((u for u in resolved_ubos if u.entity_id == entity_id), None)

        nodes.append(
            GraphNode(
                id=entity_id,
                node_type=_node_type(entity.entity_type, is_ubo),
                label=entity.label,
                entity_type=_entity_type_display(entity.entity_subtype),
                jurisdiction=entity.jurisdiction,
                is_ubo=is_ubo,
                risk_flags=list(entity.risk_flags) + (["adverse_media"] if entity.adverse_media else []),
                ofac_status=ubo.ofac_result.status if ubo else None,
                position={"x": _x_pos(entity_id), "y": _y_pos(entity_id)},
            )
        )

    # Build edges (declared + synthetic look-through)
    edges: List[GraphEdge] = []
    for edge in fixture.edges:
        citation = Citation(
            doc_id=edge.doc_id,
            page=edge.page,
            excerpt=_page_excerpt(fixture, edge.doc_id, edge.page),
            doc_label=_doc_label(fixture, edge.doc_id),
        )
        target_entity = entities_by_id.get(edge.target)
        edge_type = "through_trust" if (target_entity and target_entity.entity_type == "trust") else "direct"

        edges.append(
            GraphEdge(
                id=edge.edge_id,
                source=edge.source,
                target=edge.target,
                ownership_pct=edge.ownership_pct,
                citations=[citation],
                edge_type=edge_type,
            )
        )

    # Synthetic look-through edges for trust nodes
    for entity in fixture.entities:
        if entity.entity_type != "trust":
            continue
        look_through_targets: List[str] = []
        if entity.grantor_ids:
            look_through_targets.extend(entity.grantor_ids)
        if entity.beneficiary_ids:
            look_through_targets.extend(entity.beneficiary_ids)

        for idx, target_id in enumerate(look_through_targets):
            target = entities_by_id.get(target_id)
            if target is None:
                continue
            pct = 100.0  # revocable: full pass-through; irrevocable: trustee control
            if entity.entity_subtype == "irrevocable_trust" and entity.beneficiary_pcts:
                pct = (entity.beneficiary_pcts.get(target_id, 0.0)) * 100.0
            if entity.entity_subtype == "revocable_trust" and entity.grantor_pcts:
                pct = (entity.grantor_pcts.get(target_id, 1.0)) * 100.0

            edges.append(
                GraphEdge(
                    id=f"look_{entity.entity_id}_{target_id}",
                    source=entity.entity_id,
                    target=target_id,
                    ownership_pct=pct,
                    citations=[],
                    edge_type="look_through",
                )
            )

    logger.info(
        "Graph built: %d nodes, %d edges for fixture %s",
        len(nodes),
        len(edges),
        fixture.fixture_id,
    )
    return nodes, edges
