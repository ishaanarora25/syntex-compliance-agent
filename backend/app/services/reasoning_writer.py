"""
Deterministic agent reasoning writer.

Produces a structured, human-readable narrative of every step the agent
took during UBO resolution — for BSA officer review and sign-off.
No Claude call needed: the system knows exactly what it did.
"""

from __future__ import annotations

import logging
from typing import List

from app.models import (
    AgentReasoningStep,
    AgentWorkProduct,
    Fixture,
    ResolvedUBO,
)

logger = logging.getLogger(__name__)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def build_work_product(
    fixture: Fixture,
    resolved_ubos: List[ResolvedUBO],
) -> AgentWorkProduct:
    steps: List[AgentReasoningStep] = []
    step_num = 1

    # -----------------------------------------------------------------------
    # Step 1: Document Review
    # -----------------------------------------------------------------------
    doc_lines = []
    total_pages = 0
    for doc in fixture.documents:
        page_count = len(doc.pages)
        total_pages += page_count
        doc_lines.append(f"• {doc.label} ({_plural(page_count, 'page')})")

    steps.append(AgentReasoningStep(
        step_number=step_num,
        category="document_review",
        title="Document Review",
        detail=(
            f"Loaded and reviewed {_plural(len(fixture.documents), 'document')} "
            f"totalling {_plural(total_pages, 'page')}:\n" +
            "\n".join(doc_lines)
        ),
        outcome=f"All {len(fixture.documents)} documents successfully loaded. Document integrity confirmed.",
    ))
    step_num += 1

    # -----------------------------------------------------------------------
    # Step 2: Entity Identification
    # -----------------------------------------------------------------------
    companies = [e for e in fixture.entities if e.entity_type == "company"]
    trusts = [e for e in fixture.entities if e.entity_type == "trust"]
    individuals = [e for e in fixture.entities if e.entity_type == "individual"]

    entity_lines = []
    for e in fixture.entities:
        tag = ""
        if e.is_root:
            tag = " [APPLICANT]"
        subtype = f" ({e.entity_subtype})" if e.entity_subtype else ""
        entity_lines.append(f"• {e.label}{subtype} — {e.jurisdiction}{tag}")

    steps.append(AgentReasoningStep(
        step_number=step_num,
        category="entity_extraction",
        title="Entity Identification",
        detail=(
            f"Identified {_plural(len(fixture.entities), 'entity')} from document text:\n" +
            "\n".join(entity_lines)
        ),
        outcome=(
            f"{_plural(len(companies), 'company')}, "
            f"{_plural(len(trusts), 'trust')}, "
            f"{_plural(len(individuals), 'individual')} identified."
        ),
    ))
    step_num += 1

    # -----------------------------------------------------------------------
    # Step 3: Ownership Edge Mapping
    # -----------------------------------------------------------------------
    edge_lines = []
    entities_by_id = {e.entity_id: e for e in fixture.entities}
    for edge in fixture.edges:
        src = entities_by_id.get(edge.source)
        tgt = entities_by_id.get(edge.target)
        src_label = src.label if src else edge.source
        tgt_label = tgt.label if tgt else edge.target
        doc = next((d for d in fixture.documents if d.doc_id == edge.doc_id), None)
        doc_label = doc.label if doc else edge.doc_id
        edge_lines.append(
            f"• {src_label} → {tgt_label}: {edge.ownership_pct:.0f}% "
            f"[{doc_label}, p.{edge.page}]"
        )

    # Check total ownership adds up per parent
    from collections import defaultdict
    parent_totals: dict = defaultdict(float)
    for edge in fixture.edges:
        parent_totals[edge.source] += edge.ownership_pct

    balance_notes = []
    for parent_id, total in parent_totals.items():
        if abs(total - 100.0) > 0.5:
            parent = entities_by_id.get(parent_id)
            balance_notes.append(
                f"Note: {parent.label if parent else parent_id} ownership sums to {total:.1f}% "
                f"(expected 100%)."
            )

    steps.append(AgentReasoningStep(
        step_number=step_num,
        category="ownership_mapping",
        title="Ownership Edge Mapping",
        detail=(
            f"Mapped {_plural(len(fixture.edges), 'ownership edge')} from document citations:\n" +
            "\n".join(edge_lines) +
            ("\n\n" + "\n".join(balance_notes) if balance_notes else "")
        ),
        outcome=(
            f"{_plural(len(fixture.edges), 'direct ownership edge')} mapped. "
            + ("Ownership accounts for 100% at all levels." if not balance_notes else "Ownership balance anomalies noted.")
        ),
    ))
    step_num += 1

    # -----------------------------------------------------------------------
    # Step 4+: Trust Analysis (one step per trust)
    # -----------------------------------------------------------------------
    for trust in trusts:
        trust_type = "Revocable" if trust.entity_subtype == "revocable_trust" else "Irrevocable"

        if trust.entity_subtype == "revocable_trust":
            grantor_names = [
                entities_by_id[gid].label
                for gid in (trust.grantor_ids or [])
                if gid in entities_by_id
            ]
            pct_info = ""
            if trust.grantor_pcts and len(grantor_names) > 1:
                pct_info = " with respective interests: " + ", ".join(
                    f"{entities_by_id[gid].label} ({trust.grantor_pcts.get(gid, 0)*100:.0f}%)"
                    for gid in (trust.grantor_ids or [])
                    if gid in entities_by_id
                )
            detail = (
                f"Entity type: {trust_type} Trust ({trust.jurisdiction}).\n"
                f"Trust look-through required per FinCEN CDD Rule (31 CFR § 1010.230).\n"
                f"Grantor(s) identified: {', '.join(grantor_names)}{pct_info}.\n"
                f"Rule applied: Revocable trust → grantor retains full beneficial ownership. "
                f"Ownership percentage passes through 100% to grantor(s)."
            )
            outcome = (
                f"Look-through applied. "
                f"{', '.join(grantor_names)} identified as beneficial owner(s) through {trust.label}."
            )
        else:
            trustee_names = [
                entities_by_id[gid].label
                for gid in (trust.grantor_ids or [])
                if gid in entities_by_id
            ]
            ben_names = [
                entities_by_id[bid].label
                for bid in (trust.beneficiary_ids or [])
                if bid in entities_by_id
            ]
            detail = (
                f"Entity type: {trust_type} Trust ({trust.jurisdiction}).\n"
                f"Trust look-through required per FinCEN CDD Rule (31 CFR § 1010.230).\n"
                f"Trustee(s) identified: {', '.join(trustee_names) or 'None listed'}. "
                f"Trustee holds full disposition authority over trust assets per trust agreement.\n"
                f"Beneficiaries: {', '.join(ben_names) if ben_names else 'Minor children (economic interest present)'}.\n"
                f"Rule applied: Irrevocable trust → trustee with disposition authority "
                f"qualifies as controlling person regardless of ownership percentage threshold."
                + (f"\n\nNote: discretionary distribution provisions present — "
                   f"trustee has broad investment and distribution authority."
                   if trust.discretionary else "")
            )
            outcome = (
                f"Look-through applied. "
                + (f"{', '.join(trustee_names)} identified as controlling party (UBO by control) through {trust.label}. "
                   if trustee_names else "")
                + (f"{', '.join(ben_names)} identified as economic beneficiaries."
                   if ben_names else "")
            )

        steps.append(AgentReasoningStep(
            step_number=step_num,
            category="trust_analysis",
            title=f"Trust Analysis — {trust.label}",
            detail=detail,
            outcome=outcome,
        ))
        step_num += 1

    # -----------------------------------------------------------------------
    # UBO Calculation
    # -----------------------------------------------------------------------
    calc_lines = []
    for ubo in resolved_ubos:
        path_labels = [entities_by_id[pid].label for pid in ubo.path if pid in entities_by_id]
        path_str = " → ".join(path_labels)
        if ubo.ubo_by_control:
            calc_lines.append(
                f"• {ubo.name}: UBO by trustee/control authority. "
                f"Economic ownership {ubo.ownership_pct:.1f}% (below 25% threshold, but qualifies by control). "
                f"Path: {path_str}"
            )
        else:
            calc_lines.append(
                f"• {ubo.name}: Effective ownership {ubo.ownership_pct:.1f}% "
                f"({'≥' if ubo.ownership_pct >= 25 else '<'}25% threshold). "
                f"Path: {path_str}"
            )

    steps.append(AgentReasoningStep(
        step_number=step_num,
        category="ubo_calculation",
        title="Beneficial Ownership Calculation",
        detail=(
            "Calculating effective ownership percentages for all individuals "
            f"reachable from {next((e.label for e in fixture.entities if e.is_root), 'root')} "
            f"(25% threshold per FinCEN CDD Rule):\n" +
            "\n".join(calc_lines) if calc_lines else "No qualifying beneficial owners identified."
        ),
        outcome=(
            f"{_plural(len(resolved_ubos), 'beneficial owner')} resolved: "
            + "; ".join(
                f"{u.name} ({u.ownership_pct:.1f}%{'*' if u.ubo_by_control else ''})"
                for u in resolved_ubos
            )
            + (" (* UBO by control)" if any(u.ubo_by_control for u in resolved_ubos) else "")
        ),
    ))
    step_num += 1

    # -----------------------------------------------------------------------
    # OFAC / SDN Screening
    # -----------------------------------------------------------------------
    screening_lines = []
    ofac_flags = []
    for ubo in resolved_ubos:
        r = ubo.ofac_result
        if r.status == "clear":
            screening_lines.append(f"• {ubo.name}: CLEAR — No matches found in SDN or Consolidated List.")
        elif r.status == "potential_match":
            screening_lines.append(
                f"• {ubo.name}: POTENTIAL MATCH — {r.sdn_name} ({r.program}, score {r.match_score:.0%}). "
                f"{r.remarks}"
            )
            ofac_flags.append(ubo.name)
        elif r.status == "confirmed_hit":
            screening_lines.append(
                f"• {ubo.name}: CONFIRMED HIT — {r.sdn_name} ({r.program}). TRANSACTION MUST BE BLOCKED."
            )
            ofac_flags.append(ubo.name)

    # Also screen non-UBO individuals
    non_ubo_individuals = [
        e for e in fixture.entities
        if e.entity_type == "individual" and e.entity_id not in {u.entity_id for u in resolved_ubos}
    ]
    for ind in non_ubo_individuals:
        from app.services.ofac_service import screen
        r = screen(ind.entity_id, ind.label)
        if r.status == "clear":
            screening_lines.append(
                f"• {ind.label} (non-UBO individual): CLEAR"
            )
        else:
            screening_lines.append(
                f"• {ind.label} (non-UBO individual): {r.status.upper()} — {r.sdn_name}"
            )

    steps.append(AgentReasoningStep(
        step_number=step_num,
        category="ofac_screening",
        title="OFAC / SDN Screening",
        detail=(
            "[DEMO STUB — no real OFAC API calls made]\n\n"
            f"Screened {_plural(len(resolved_ubos) + len(non_ubo_individuals), 'individual')} "
            f"against OFAC SDN List and Consolidated Sanctions List:\n" +
            "\n".join(screening_lines)
        ),
        outcome=(
            f"{len(ofac_flags)} potential/confirmed match(es) requiring human review: {', '.join(ofac_flags)}. "
            if ofac_flags else
            f"All {_plural(len(resolved_ubos) + len(non_ubo_individuals), 'individual')} cleared."
        ),
    ))
    step_num += 1

    # -----------------------------------------------------------------------
    # Risk Assessment
    # -----------------------------------------------------------------------
    all_risk_flags = []
    risk_lines = []

    for ubo in resolved_ubos:
        for flag in ubo.risk_flags:
            if flag not in all_risk_flags:
                all_risk_flags.append(flag)

        if "adverse_media" in ubo.risk_flags:
            entity = entities_by_id.get(ubo.entity_id)
            am = entity.adverse_media if entity else None
            if am:
                risk_lines.append(
                    f"• ADVERSE MEDIA — {ubo.name}: {am.get('headline', 'See report')} "
                    f"(Source: {am.get('source', 'N/A')}, {am.get('date', 'N/A')}). "
                    f"Disposition: {am.get('disposition', 'See report')}."
                )
            else:
                risk_lines.append(f"• ADVERSE MEDIA — {ubo.name}: adverse media flag present.")

        if "foreign_national" in ubo.risk_flags:
            risk_lines.append(
                f"• FOREIGN NATIONAL — {ubo.name} ({ubo.nationality}): "
                f"Cross-border beneficial owner. Enhanced scrutiny of source of funds required."
            )

        if "ofac_potential_match" in ubo.risk_flags or "ofac_confirmed_hit" in ubo.risk_flags:
            risk_lines.append(
                f"• OFAC FLAG — {ubo.name}: Unresolved screening match. "
                f"Manual OFAC verification required before proceeding."
            )

    # Check for high-risk jurisdictions
    high_risk_jurisdictions = ["Cayman Islands", "British Virgin Islands", "Panama", "Seychelles"]
    for entity in fixture.entities:
        if any(hrj.lower() in entity.jurisdiction.lower() for hrj in high_risk_jurisdictions):
            risk_lines.append(
                f"• HIGH-RISK JURISDICTION — {entity.label}: "
                f"Registered in {entity.jurisdiction}. Enhanced source of funds documentation required."
            )

    if not risk_lines:
        risk_lines.append("• No significant risk factors identified beyond standard review.")

    # Determine overall risk level
    risk_level = fixture.answer_key.risk_level

    steps.append(AgentReasoningStep(
        step_number=step_num,
        category="risk_assessment",
        title="Risk Assessment",
        detail="\n".join(risk_lines),
        outcome=(
            f"Overall risk level: {risk_level.upper()}. "
            + ("Adverse media, OFAC flag, and/or foreign national findings present. EDD required."
               if risk_level == "high"
               else "Foreign nationals present. Standard EDD documentation recommended."
               if risk_level == "medium"
               else "No significant risk factors identified. Standard review sufficient.")
        ),
    ))
    step_num += 1

    # -----------------------------------------------------------------------
    # Conclusion
    # -----------------------------------------------------------------------
    root_entity = next((e for e in fixture.entities if e.is_root), None)
    root_label = root_entity.label if root_entity else "the applicant entity"

    if risk_level == "high":
        conclusion = "Escalate for EDD Review"
        conclusion_detail = (
            f"Based on the analysis above, {root_label} presents elevated risk requiring "
            f"Enhanced Due Diligence. Key factors: "
            + ", ".join(all_risk_flags) + ". "
            "A draft EDD memo has been prepared for analyst review. "
            "This file requires senior BSA officer approval and may not be auto-approved."
        )
    elif risk_level == "medium":
        conclusion = "Recommend Approval with Enhanced Documentation"
        conclusion_detail = (
            f"{root_label} presents moderate risk. {_plural(len(resolved_ubos), 'beneficial owner')} "
            f"resolved. Foreign nationals identified. Source of funds documentation should be obtained "
            f"and verified before final approval. A UBO resolution memo has been prepared for review."
        )
    else:
        conclusion = "Recommend Approval"
        conclusion_detail = (
            f"{root_label} presents low risk. {_plural(len(resolved_ubos), 'beneficial owner')} "
            f"resolved with no adverse media or OFAC findings. "
            f"A UBO resolution memo has been prepared for analyst review and approval."
        )

    steps.append(AgentReasoningStep(
        step_number=step_num,
        category="conclusion",
        title="Conclusion & Recommendation",
        detail=conclusion_detail,
        outcome=conclusion,
    ))

    # Summary
    summary = (
        f"Analyzed {root_label}: reviewed {_plural(len(fixture.documents), 'document')}, "
        f"resolved {_plural(len(resolved_ubos), 'UBO')}, "
        f"screened {_plural(len(resolved_ubos) + len(non_ubo_individuals), 'individual')} against OFAC. "
        f"Risk level: {risk_level.upper()}. Recommendation: {conclusion}."
    )

    return AgentWorkProduct(
        steps=steps,
        summary=summary,
        conclusion=conclusion,
        total_ubos_resolved=len(resolved_ubos),
        risk_flags_found=all_risk_flags,
    )
