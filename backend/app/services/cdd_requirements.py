"""
CDD document-requirement checklist.

Given the ownership graph (entities + edges) and the set of uploaded documents,
work out which FinCEN CDD-required documents are present and which are missing.
The output feeds a frontend checklist so the analyst knows what to chase before
the file can be closed.

Rule set (loose interpretation of 31 CFR § 1010.230):
  - Every LLC must have Articles of Organization (or equivalent formation doc).
  - Every LLC with > 1 member must also have an Operating Agreement.
  - Every LP must have a Limited Partnership Agreement.
  - Every foreign company (GmbH / Ltd / etc.) must have a Commercial Register
    Extract or equivalent certificate of incorporation.
  - Every trust must have a Trust Agreement.
  - Every beneficial owner over the 25% threshold *should* have an identity
    document on file. The demo marks this as "advisory" rather than blocking.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List

from app.models import (
    CDDChecklist,
    ExtractedEdge,
    ExtractedEntityRef,
    RequiredDocument,
    ResolvedUBO,
    UploadedDocumentMeta,
)

logger = logging.getLogger(__name__)

_FORMATION_TYPES = {"articles_of_organization", "certificate_of_incorporation"}
_OPERATING_TYPES = {"operating_agreement"}
_TRUST_TYPES = {"trust_agreement"}
_LP_TYPES = {"limited_partnership_agreement"}
_REGISTER_TYPES = {"commercial_register_extract", "certificate_of_incorporation"}
_ID_TYPES = {"identity_document"}


_ENTITY_SUFFIX_TOKENS = {
    "llc", "ltd", "lp", "gmbh", "corp", "inc", "plc", "sa", "sarl",
    "trust", "revocable", "irrevocable", "family", "joint", "living",
    "the", "of", "and",
}


def _entity_tokens(entity_id: str, label: str) -> List[str]:
    """Tokens used to correlate an entity to a doc.

    Strip generic suffixes / stop words so "Apex Holdings LLC" (entity_id
    "apex_holdings_llc") matches "Apex Holdings LLC Operating Agreement"
    (doc_id "apex_holdings_operating_agreement").
    """
    parts = []
    for raw in (entity_id + " " + label).lower().replace("_", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum())
        if not token or token in _ENTITY_SUFFIX_TOKENS:
            continue
        parts.append(token)
    return parts


def _doc_haystack(doc: UploadedDocumentMeta) -> str:
    return (doc.doc_id + " " + doc.label + " " + doc.filename).lower()


def _entity_matches_doc(entity_tokens: List[str], doc: UploadedDocumentMeta) -> bool:
    if not entity_tokens:
        return False
    hay = _doc_haystack(doc)
    # Require the two most distinctive tokens to appear — this keeps us from
    # matching "Mitchell Family Trust" against "Apex Holdings Operating Agmt"
    # while still matching "Apex Holdings LLC" against
    # "apex_holdings_operating_agreement".
    distinctive = [t for t in entity_tokens if len(t) >= 4][:3] or entity_tokens[:2]
    hits = sum(1 for t in distinctive if t in hay)
    return hits >= min(2, len(distinctive))


def _docs_of_type_about(
    entity_id: str,
    label: str,
    allowed_types: set,
    docs: List[UploadedDocumentMeta],
) -> List[str]:
    tokens = _entity_tokens(entity_id, label)
    hits = []
    for d in docs:
        if d.doc_type not in allowed_types:
            continue
        if _entity_matches_doc(tokens, d):
            hits.append(d.doc_id)
    return hits


def build_checklist(
    entities: List[ExtractedEntityRef],
    edges: List[ExtractedEdge],
    documents: List[UploadedDocumentMeta],
    resolved_ubos: List[ResolvedUBO],
) -> CDDChecklist:
    items: List[RequiredDocument] = []

    # Count direct children per entity — used to decide if an LLC needs an OA.
    child_counts: Dict[str, int] = defaultdict(int)
    for edge in edges:
        child_counts[edge.source] += 1

    for entity in entities:
        subtype = (entity.entity_subtype or "").lower()

        # Formation document
        if entity.entity_type == "company" and subtype in ("llc", "corp"):
            hits = _docs_of_type_about(entity.entity_id, entity.label, _FORMATION_TYPES, documents)
            items.append(
                RequiredDocument(
                    requirement_id=f"formation__{entity.entity_id}",
                    label=f"Articles of Organization — {entity.label}",
                    rationale=(
                        "Formation document required to verify legal existence and "
                        "jurisdiction of organization per FinCEN CDD Rule."
                    ),
                    status="provided" if hits else "missing",
                    provided_by=hits,
                    applies_to_entity_id=entity.entity_id,
                )
            )

            if child_counts.get(entity.entity_id, 0) >= 2:
                oa_hits = _docs_of_type_about(entity.entity_id, entity.label, _OPERATING_TYPES, documents)
                items.append(
                    RequiredDocument(
                        requirement_id=f"operating__{entity.entity_id}",
                        label=f"Operating Agreement — {entity.label}",
                        rationale=(
                            "Multi-member LLC — operating agreement needed to confirm "
                            "member ownership percentages and management authority."
                        ),
                        status="provided" if oa_hits else "missing",
                        provided_by=oa_hits,
                        applies_to_entity_id=entity.entity_id,
                    )
                )

        # Foreign company — require a register extract
        if entity.entity_type == "company" and subtype in ("gmbh", "ltd", "sarl", "sa", "plc"):
            reg_hits = _docs_of_type_about(entity.entity_id, entity.label, _REGISTER_TYPES, documents)
            items.append(
                RequiredDocument(
                    requirement_id=f"register__{entity.entity_id}",
                    label=f"Commercial Register / Incorporation Certificate — {entity.label}",
                    rationale=(
                        "Foreign entity — register extract or certificate of incorporation "
                        "required to verify legal existence and shareholders."
                    ),
                    status="provided" if reg_hits else "missing",
                    provided_by=reg_hits,
                    applies_to_entity_id=entity.entity_id,
                )
            )

        # LP — need a partnership agreement
        if entity.entity_type == "company" and subtype == "lp":
            lp_hits = _docs_of_type_about(entity.entity_id, entity.label, _LP_TYPES, documents)
            items.append(
                RequiredDocument(
                    requirement_id=f"lp_agreement__{entity.entity_id}",
                    label=f"Limited Partnership Agreement — {entity.label}",
                    rationale=(
                        "LP structure requires the partnership agreement to confirm "
                        "general partner authority and partner splits."
                    ),
                    status="provided" if lp_hits else "missing",
                    provided_by=lp_hits,
                    applies_to_entity_id=entity.entity_id,
                )
            )

        # Trust — need a trust agreement
        if entity.entity_type == "trust":
            trust_hits = _docs_of_type_about(entity.entity_id, entity.label, _TRUST_TYPES, documents)
            items.append(
                RequiredDocument(
                    requirement_id=f"trust_agreement__{entity.entity_id}",
                    label=f"Trust Agreement — {entity.label}",
                    rationale=(
                        "Trust look-through requires the trust agreement to identify "
                        "grantor(s), trustee(s), and beneficiaries."
                    ),
                    status="provided" if trust_hits else "missing",
                    provided_by=trust_hits,
                    applies_to_entity_id=entity.entity_id,
                )
            )

    # ID check for every UBO ≥ 25%
    for ubo in resolved_ubos:
        id_hits = _docs_of_type_about(ubo.entity_id, ubo.name, _ID_TYPES, documents)
        items.append(
            RequiredDocument(
                requirement_id=f"identity__{ubo.entity_id}",
                label=f"Government-issued ID — {ubo.name}",
                rationale=(
                    "Beneficial owner meeting the 25% threshold — identity verification "
                    "required per FinCEN CDD Rule. Advisory for demo purposes."
                ),
                status="provided" if id_hits else "missing",
                provided_by=id_hits,
                applies_to_entity_id=ubo.entity_id,
            )
        )

    missing = [i for i in items if i.status == "missing"]
    satisfied = [i for i in items if i.status == "provided"]

    # A missing formation / operating / trust agreement blocks UBO resolution.
    blocking = any(
        i.status == "missing" and not i.requirement_id.startswith("identity__")
        for i in items
    )

    logger.info(
        "CDD checklist: %d satisfied, %d missing, blocking=%s",
        len(satisfied), len(missing), blocking,
    )
    return CDDChecklist(
        items=items,
        missing_count=len(missing),
        satisfied_count=len(satisfied),
        blocking_for_ubo_resolution=blocking,
    )
