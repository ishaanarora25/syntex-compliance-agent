"""
Glue service that adapts the case/upload flow into the same pipeline the
fixture-based flow uses.

A case's extracted entities + edges + uploaded PDFs are repackaged into the
internal `Fixture` shape so the existing UBO resolver, graph builder, memo
writer, and reasoning writer don't need a second code path.
"""

from __future__ import annotations

import logging
import re
from typing import List

from app.models import (
    AnswerKey,
    Fixture,
    FixtureDocument,
    FixtureEdge,
    FixtureEntity,
    FixturePage,
)
from app.services.case_store import _Case

logger = logging.getLogger(__name__)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_") or "case"


def case_to_fixture(case: _Case) -> Fixture:
    """Build a synthetic Fixture from case state so the existing pipeline runs."""
    applicant = case.applicant_name or case.name or "Applicant"

    entities: List[FixtureEntity] = []
    for ent in case.extracted_entities:
        entities.append(
            FixtureEntity(
                entity_id=ent.entity_id,
                label=ent.label,
                entity_type=ent.entity_type,
                entity_subtype=ent.entity_subtype,
                jurisdiction=ent.jurisdiction,
                nationality=ent.nationality,
                is_root=ent.is_root,
                has_control_rights=ent.has_control_rights,
                risk_flags=list(ent.risk_flags),
                adverse_media=None,  # adverse media is captured via screening service
                grantor_ids=ent.grantor_ids,
                grantor_pcts=ent.grantor_pcts,
                beneficiary_ids=ent.beneficiary_ids,
                beneficiary_pcts=ent.beneficiary_pcts,
                discretionary=ent.discretionary,
            )
        )

    edges: List[FixtureEdge] = []
    for edge in case.extracted_edges:
        edges.append(
            FixtureEdge(
                edge_id=edge.edge_id,
                source=edge.source,
                target=edge.target,
                ownership_pct=edge.ownership_pct,
                doc_id=edge.doc_id,
                page=edge.page,
            )
        )

    documents: List[FixtureDocument] = []
    for meta in case.documents:
        pdf = case.pdfs.get(meta.doc_id)
        pages: List[FixturePage] = []
        if pdf:
            for p in pdf.pages:
                pages.append(FixturePage(page=p.page, text=p.text))
        documents.append(
            FixtureDocument(
                doc_id=meta.doc_id,
                label=meta.label,
                doc_type=meta.doc_type,
                pages=pages,
            )
        )

    return Fixture(
        fixture_id=case.case_id,
        label=applicant,
        scenario=case.case_id,
        description=f"Case file for {applicant} — {len(documents)} uploaded document(s).",
        entities=entities,
        edges=edges,
        documents=documents,
        answer_key=AnswerKey(
            resolved_ubos=[],
            risk_level="pending",   # inferred downstream
            memo_type="ubo_resolution",
        ),
    )


def infer_risk_and_memo_type(resolved_ubos, entities) -> tuple[str, str]:
    """
    Deterministic risk classification so we don't depend on an answer key.

      - high: any confirmed OFAC hit, potential OFAC match, PEP match, or
              adverse media match.
      - medium: any foreign national UBO, or any UBO operating through a
                high-risk jurisdiction (Cayman, BVI, Panama, Seychelles).
      - low: everything else.

    Memo type: full_edd when risk==high, else ubo_resolution.
    """
    high_risk_jurisdictions = [
        "cayman islands", "british virgin islands", "panama", "seychelles", "belize"
    ]
    risk = "low"

    for ubo in resolved_ubos:
        if ubo.ofac_result.status in ("potential_match", "confirmed_hit"):
            risk = "high"
            break
        if ubo.pep_result.status in ("potential_match", "confirmed_pep"):
            risk = "high"
            break
        if ubo.adverse_media_result.status in ("potential_match", "confirmed_hit"):
            risk = "high"
            break

    if risk != "high":
        for ubo in resolved_ubos:
            nat = (ubo.nationality or "").upper()
            if nat not in ("US", "USA", "UNKNOWN"):
                risk = "medium"
                break
    if risk != "high":
        for ent in entities:
            if any(hrj in ent.jurisdiction.lower() for hrj in high_risk_jurisdictions):
                risk = "medium"
                break

    memo_type = "full_edd" if risk == "high" else "ubo_resolution"
    return risk, memo_type
