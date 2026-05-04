"""
Application-assessment orchestrator.

Runs every check the BSA team needs *before* a banker even looks at a new
application: KYB, KYC, sanctions screening, name-consistency, business-risk
classification, UBO completeness audit, and the synthesis of recommended
documentation + applicant follow-up questions.

This is the single entry point called by the onboarding-manager webhook
receiver after a fresh application lands.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import List, Tuple

from app.models import (
    AdverseMediaResult,
    ApplicationAssessment,
    AssessApplicationRequest,
    BusinessRiskAssessment,
    Inconsistency,
    KYCResult,
    NameConsistencyResult,
    OFACResult,
    PEPResult,
    RecommendedDocument,
    ScreeningBundle,
    UBOCompletenessResult,
    WebhookBeneficialOwner,
)
from app.services import (
    adverse_media_service,
    business_risk,
    id_verification_service,
    kyb_service,
    name_consistency,
    ofac_service,
    pep_service,
    ubo_completeness,
)

logger = logging.getLogger(__name__)


_DOC_TYPES_PRESENT_PRIORITY = [
    "company_formation_docs",
    "owner_ids",
    "tax_returns",
    "bank_statements",
    "financial_statements",
    "business_license",
]


async def assess(request: AssessApplicationRequest) -> ApplicationAssessment:
    start = time.time()
    company = request.companyInfo
    applicant_name = company.companyName
    logger.info(
        "Assessing application %s for %s with %d owner(s) and %d doc(s)",
        request.applicationId, applicant_name,
        len(request.beneficialOwners), len(request.documents),
    )

    # ---- Run independent checks concurrently ---------------------------
    name_consistency_task = name_consistency.check(applicant_name, request.documents)

    # The screening services are synchronous and cheap — run them as a group
    # in the default executor so we still parallelize with the LLM call above.
    loop = asyncio.get_running_loop()

    def _run_sync_checks():
        kyb = kyb_service.screen(company)
        kyc_results: List[KYCResult] = []
        sanctions: List[ScreeningBundle] = []
        for owner in request.beneficialOwners:
            kyc_results.append(id_verification_service.screen(owner))
            sanctions.append(_screen_owner(owner))
        biz_risk = business_risk.assess(company, request.regulatedCheck)
        ubo_audit = ubo_completeness.assess(request.beneficialOwners)
        return kyb, kyc_results, sanctions, biz_risk, ubo_audit

    sync_task = loop.run_in_executor(None, _run_sync_checks)
    name_result, sync_results = await asyncio.gather(name_consistency_task, sync_task)
    kyb_result, kyc_results, sanctions, biz_risk, ubo_audit = sync_results

    # ---- Cross-check inconsistencies -----------------------------------
    inconsistencies = _detect_inconsistencies(
        request, name_result, kyb_result, kyc_results, sanctions, ubo_audit,
    )

    # ---- Recommend additional documentation ----------------------------
    recommended_docs = _recommend_documents(
        request, biz_risk, ubo_audit, sanctions, kyb_result, name_result,
    )

    # ---- Roll up follow-up questions -----------------------------------
    follow_ups = list(ubo_audit.follow_up_questions)
    if name_result.status == "mismatch":
        follow_ups.insert(
            0,
            f"The company name on the application ('{name_result.applicant_name}') does not "
            f"match the name on the uploaded formation document ('{name_result.document_name or 'unknown'}'). "
            "Please confirm the correct legal name and re-upload the matching formation document.",
        )
    elif name_result.status == "minor_variation":
        follow_ups.insert(
            0,
            f"The legal name on the formation document ('{name_result.document_name}') differs "
            f"slightly from the application ('{name_result.applicant_name}'). Please confirm "
            "this is the same entity (e.g. d/b/a, recent re-naming).",
        )

    # ---- Aggregate overall risk ----------------------------------------
    overall_risk, summary = _grade_overall_risk(
        biz_risk, sanctions, kyb_result, kyc_results, ubo_audit, name_result,
    )

    processing_ms = int((time.time() - start) * 1000)
    return ApplicationAssessment(
        application_id=request.applicationId,
        applicant_email=request.applicantEmail,
        company_name=applicant_name,
        assessed_at=datetime.now(timezone.utc).isoformat(),
        processing_ms=processing_ms,
        overall_risk=overall_risk,
        risk_summary=summary,
        name_consistency=name_result,
        data_inconsistencies=inconsistencies,
        business_risk=biz_risk,
        ubo_completeness=ubo_audit,
        kyb_result=kyb_result,
        kyc_results=kyc_results,
        sanctions_screening=sanctions,
        recommended_documents=recommended_docs,
        follow_up_questions=follow_ups,
    )


# ---------------------------------------------------------------------------
# Sanctions screening — wraps the existing OFAC / PEP / Adverse-Media stubs
# but presents them as one LexisNexis bundle per individual.
# ---------------------------------------------------------------------------

def _screen_owner(owner: WebhookBeneficialOwner) -> ScreeningBundle:
    name = owner.name or "Unknown"
    ofac: OFACResult = ofac_service.screen(owner.id, name)
    pep: PEPResult = pep_service.screen(owner.id, name)
    adverse: AdverseMediaResult = adverse_media_service.screen(owner.id, name)

    # Stamp a LexisNexis remark prefix to keep the front-end label honest.
    ofac.remarks = _prepend_provider("LexisNexis Bridger", ofac.remarks)
    pep.remarks = _prepend_provider("LexisNexis Bridger", pep.remarks)
    adverse.remarks = _prepend_provider("LexisNexis Adverse Media Intelligence", adverse.remarks)

    return ScreeningBundle(entity_id=owner.id, name=name, ofac=ofac, pep=pep, adverse_media=adverse)


def _prepend_provider(provider: str, remarks: str | None) -> str:
    base = remarks or ""
    if provider.lower() in base.lower():
        return base
    if not base:
        return f"[via {provider}]"
    return f"[via {provider}] {base}"


# ---------------------------------------------------------------------------
# Inconsistency detection
# ---------------------------------------------------------------------------

def _detect_inconsistencies(
    request: AssessApplicationRequest,
    name_result: NameConsistencyResult,
    kyb: "kyb_service.KYBResult",  # type: ignore[name-defined]
    kyc_results: List[KYCResult],
    sanctions: List[ScreeningBundle],
    ubo_audit: UBOCompletenessResult,
) -> List[Inconsistency]:
    out: List[Inconsistency] = []
    company = request.companyInfo

    # Name mismatch surfaces as its own field — the inconsistency record is
    # there so it shows up in the data-quality strip on the UI.
    if name_result.status == "mismatch":
        out.append(Inconsistency(
            field="company_name",
            severity="high",
            description=(
                f"Application name '{name_result.applicant_name}' does not appear in the "
                f"uploaded formation document (closest match: '{name_result.document_name}', "
                f"similarity {name_result.similarity:.2f})."
            ),
            suggested_action="Re-upload the formation document or correct the company name.",
        ))
    elif name_result.status == "minor_variation":
        out.append(Inconsistency(
            field="company_name",
            severity="low",
            description=(
                f"Slight difference between application name '{name_result.applicant_name}' "
                f"and document name '{name_result.document_name}'."
            ),
            suggested_action="Confirm both names refer to the same legal entity.",
        ))

    # EIN format
    if company.ein and not _ein_format_ok(company.ein):
        out.append(Inconsistency(
            field="ein",
            severity="medium",
            description=f"EIN '{company.ein}' is not in valid 9-digit format.",
            suggested_action="Request a corrected EIN or IRS CP-575/147C confirmation letter.",
        ))

    # Country / state mismatch — US country with no state, or non-US country with US state
    country = (company.countryOfFormation or "").upper()
    state = (company.stateOfFormation or "").strip()
    if country in ("US", "USA", "UNITED STATES") and not state:
        out.append(Inconsistency(
            field="state_of_formation",
            severity="medium",
            description="U.S. entity declared without a state of formation.",
            suggested_action="Capture the correct state of formation from the formation document.",
        ))

    # KYB warnings → inconsistencies
    if kyb.status in ("warning", "failed"):
        for finding in kyb.findings[:3]:
            out.append(Inconsistency(
                field="kyb",
                severity="medium" if kyb.status == "warning" else "high",
                description=finding,
                suggested_action="Review and reconcile the KYB finding before progressing.",
            ))

    # Sanctions hits
    for bundle in sanctions:
        if bundle.ofac.status in ("potential_match", "confirmed_hit"):
            out.append(Inconsistency(
                field=f"ofac:{bundle.entity_id}",
                severity="high" if bundle.ofac.status == "confirmed_hit" else "medium",
                description=(
                    f"OFAC screening returned '{bundle.ofac.status}' for {bundle.name} "
                    f"(score {bundle.ofac.match_score})."
                ),
                suggested_action="Manual disposition required before approving.",
            ))
        if bundle.pep.status in ("potential_match", "confirmed_pep"):
            out.append(Inconsistency(
                field=f"pep:{bundle.entity_id}",
                severity="medium",
                description=f"PEP screening returned '{bundle.pep.status}' for {bundle.name}.",
                suggested_action="Document source-of-wealth and apply EDD per FATF Recommendation 12.",
            ))
        if bundle.adverse_media.status == "potential_match":
            out.append(Inconsistency(
                field=f"adverse_media:{bundle.entity_id}",
                severity="medium",
                description=f"Adverse media findings for {bundle.name}: "
                            f"{', '.join(bundle.adverse_media.categories) or 'unspecified'}.",
                suggested_action="Review adverse-media articles and document banker disposition.",
            ))

    # KYC / Socure red flags
    for kyc in kyc_results:
        if kyc.overall_status == "fail":
            out.append(Inconsistency(
                field=f"kyc:{kyc.entity_id}",
                severity="high",
                description=f"Identity verification failed for {kyc.name}.",
                suggested_action="Block onboarding pending refreshed identity documents.",
            ))
        elif kyc.overall_status == "review":
            out.append(Inconsistency(
                field=f"kyc:{kyc.entity_id}",
                severity="medium",
                description=f"Identity verification needs review for {kyc.name} "
                            f"(ID-V {kyc.id_verification_score}, Sigma {kyc.sigma_fraud_score}).",
                suggested_action="Obtain additional KYC documentation per Socure guidance.",
            ))

    # UBO arithmetic / coverage
    if ubo_audit.coverage_status == "over_allocated":
        out.append(Inconsistency(
            field="ubo_total",
            severity="high",
            description=f"Beneficial ownership totals {ubo_audit.total_ownership_pct}% (>100%).",
            suggested_action="Request a re-attested beneficial-ownership form.",
        ))
    elif ubo_audit.coverage_status == "incomplete" and ubo_audit.total_ownership_pct < 75:
        out.append(Inconsistency(
            field="ubo_total",
            severity="medium",
            description=f"Beneficial ownership totals only {ubo_audit.total_ownership_pct}% — "
                        "more than 25% of the company is unaccounted for.",
            suggested_action="Ask the applicant to identify the missing owners or attest to "
                             "the residual being held by employees / option pool / treasury.",
        ))

    return out


def _ein_format_ok(ein: str) -> bool:
    import re
    return bool(re.match(r"^\d{2}-?\d{7}$", ein.strip()))


# ---------------------------------------------------------------------------
# Recommended-documents synthesis
# ---------------------------------------------------------------------------

def _recommend_documents(
    request: AssessApplicationRequest,
    biz_risk: BusinessRiskAssessment,
    ubo_audit: UBOCompletenessResult,
    sanctions: List[ScreeningBundle],
    kyb,
    name_result: NameConsistencyResult,
) -> List[RecommendedDocument]:
    recs: List[RecommendedDocument] = []
    have_doc_types = {(d.type or "").lower() for d in request.documents if d.status == "uploaded"}

    def add(label: str, rationale: str, priority: str, triggered_by: List[str]) -> None:
        # Avoid exact duplicates
        if any(r.label == label for r in recs):
            return
        recs.append(RecommendedDocument(
            label=label, rationale=rationale, priority=priority, triggered_by=triggered_by,
        ))

    # Always need formation + IDs (from CDD baseline) — surface as "required" if missing
    if "company_formation_docs" not in have_doc_types:
        add(
            "Articles of Organization / Certificate of Incorporation",
            "FinCEN CDD Rule baseline — every entity must have its formation document on file.",
            "required",
            ["cdd_baseline"],
        )
    if "owner_ids" not in have_doc_types:
        add(
            "Government-issued ID for every UBO ≥ 25%",
            "FinCEN CDD Rule baseline — beneficial owners crossing the 25% threshold "
            "must be identity-verified.",
            "required",
            ["cdd_baseline"],
        )

    # Missing financial baseline
    if "tax_returns" not in have_doc_types:
        add(
            "2 most recent business tax returns",
            "Required to corroborate revenue, ownership, and entity continuity.",
            "required",
            ["financial_baseline"],
        )
    if "bank_statements" not in have_doc_types:
        add(
            "Last 3 months of business bank statements",
            "Required to verify cash-flow patterns and source of funds.",
            "required",
            ["financial_baseline"],
        )

    # Foreign entity
    if biz_risk.is_foreign_entity:
        add(
            "Apostilled / certified Certificate of Good Standing from foreign registry",
            f"Foreign-formed entity ({request.companyInfo.countryOfFormation}) — domestic "
            "Secretary-of-State verification is unavailable; apostilled registry extract required.",
            "required",
            ["foreign_entity"],
        )
        add(
            "Foreign tax-ID / VAT registration certificate",
            "Confirms tax status in formation jurisdiction; proxy for the U.S. EIN.",
            "required",
            ["foreign_entity"],
        )
        add(
            "W-8BEN-E for the entity",
            "Required for U.S. payor reporting on a non-U.S. entity (IRS Chapter 3/4).",
            "required",
            ["foreign_entity"],
        )

    # Regulated business
    if biz_risk.is_regulated:
        add(
            "Copy of every applicable regulatory license / registration",
            "Self-attested regulated business — confirm primary regulator and active license status.",
            "required",
            ["regulated_business"],
        )
        add(
            "Most recent regulatory examination letter or audit report",
            "Validates that the regulator considers the entity in good standing.",
            "recommended",
            ["regulated_business"],
        )

    # High-risk industry
    if biz_risk.is_high_risk_industry:
        add(
            "Source-of-funds attestation + supporting documentation",
            "High-risk industry — banker must document the source of operating funds beyond "
            "the standard cash-flow narrative.",
            "required",
            ["high_risk_industry"],
        )
        add(
            "BSA / AML compliance program (if entity is a covered business)",
            "Customer entities classed as MSBs / DPMS / casinos must maintain their own AML "
            "program; obtain a copy for the credit file.",
            "recommended",
            ["high_risk_industry"],
        )

    # Specific industry triggers
    industry_text = " ".join(filter(None, [request.companyInfo.industry, request.companyInfo.description])).lower()
    if any(t in industry_text for t in ("crypto", "digital asset", "virtual currency")):
        add(
            "FinCEN MSB registration confirmation",
            "Crypto / digital-asset business — must be registered with FinCEN as an MSB.",
            "required",
            ["crypto"],
        )
        add(
            "Travel-rule compliance attestation",
            "Crypto entity — confirm policies meet 31 CFR § 1010.410(f) thresholds.",
            "recommended",
            ["crypto"],
        )
    if any(t in industry_text for t in ("cannabis", "marijuana", "hemp")):
        add(
            "State cannabis license + seed-to-sale tracking attestation",
            "Cannabis-related business — FinCEN 2014 guidance requires SAR filing posture; "
            "confirm state license and tracking system.",
            "required",
            ["cannabis"],
        )
    if any(t in industry_text for t in ("money transmit", "remittance", "msb")):
        add(
            "List of every state MTL (money transmitter license)",
            "MSB / money transmitter — confirm state-level licensing in every operating state.",
            "required",
            ["msb"],
        )

    # UBO incompleteness
    if ubo_audit.coverage_status in ("incomplete", "over_allocated"):
        add(
            "Re-attested FinCEN CTA Beneficial Ownership Information (BOI) form",
            "Declared ownership total does not reconcile to 100% — re-attestation required to "
            "satisfy the Corporate Transparency Act reporting standard.",
            "required",
            ["ubo_incomplete"],
        )
    if ubo_audit.above_threshold_count == 0:
        add(
            "Statement of Significant Responsibility (control prong)",
            "No 25% owner is declared — banker needs an attested individual exercising "
            "substantial control per FinCEN CDD Rule control prong.",
            "required",
            ["control_prong"],
        )

    # Sanctions hits / adverse media
    for bundle in sanctions:
        if bundle.ofac.status in ("potential_match", "confirmed_hit"):
            add(
                f"OFAC false-positive disposition memo — {bundle.name}",
                "Sanctions hit must be cleared with documented disposition (4-eye review).",
                "required",
                ["sanctions"],
            )
        if bundle.pep.status in ("potential_match", "confirmed_pep"):
            add(
                f"Source-of-wealth questionnaire — {bundle.name}",
                "PEP exposure — FATF Recommendation 12 source-of-wealth required.",
                "required",
                ["pep"],
            )
        if bundle.adverse_media.status == "potential_match":
            add(
                f"Banker disposition note on adverse media — {bundle.name}",
                "Adverse media surfaced — banker must document review and disposition.",
                "recommended",
                ["adverse_media"],
            )

    # Name mismatch
    if name_result.status in ("mismatch", "minor_variation"):
        add(
            "Reconciled formation document with the applicant's legal name",
            "Application name and formation-document name do not match — request the "
            "correct formation document.",
            "required",
            ["name_mismatch"],
        )

    # KYB warnings (e.g. newly formed, no EIN, foreign)
    if kyb.status == "warning" and "newly formed" in " ".join(kyb.findings).lower():
        add(
            "Source-of-funds and pro-forma financials",
            "Newly formed entity with limited operating history — formal source-of-funds "
            "documentation required in lieu of historical financials.",
            "recommended",
            ["new_entity"],
        )

    return recs


# ---------------------------------------------------------------------------
# Overall risk grading
# ---------------------------------------------------------------------------

def _grade_overall_risk(
    biz_risk: BusinessRiskAssessment,
    sanctions: List[ScreeningBundle],
    kyb,
    kyc_results: List[KYCResult],
    ubo_audit: UBOCompletenessResult,
    name_result: NameConsistencyResult,
) -> Tuple[str, str]:
    # Confirmed sanctions hit or KYC fail → critical, no question.
    if any(b.ofac.status == "confirmed_hit" for b in sanctions):
        return ("critical", "Confirmed OFAC SDN match on a beneficial owner — block onboarding.")
    if any(k.overall_status == "fail" for k in kyc_results):
        return ("critical", "Identity verification failed for one or more beneficial owners.")
    if biz_risk.risk_level == "critical":
        return ("critical", biz_risk.rationale)

    high_signals = []
    if any(b.ofac.status == "potential_match" for b in sanctions):
        high_signals.append("OFAC potential match")
    if any(b.pep.status in ("potential_match", "confirmed_pep") for b in sanctions):
        high_signals.append("PEP exposure")
    if any(b.adverse_media.status == "potential_match" for b in sanctions):
        high_signals.append("adverse media")
    if name_result.status == "mismatch":
        high_signals.append("name mismatch")
    if biz_risk.risk_level == "high":
        high_signals.append("high-risk business profile")
    if ubo_audit.coverage_status == "over_allocated":
        high_signals.append("UBO over-allocation")

    if high_signals:
        return ("high", "Elevated risk: " + ", ".join(high_signals) + ".")

    medium_signals = []
    if biz_risk.risk_level == "medium":
        medium_signals.append("medium business risk")
    if ubo_audit.coverage_status == "incomplete":
        medium_signals.append("incomplete UBO disclosure")
    if any(k.overall_status == "review" for k in kyc_results):
        medium_signals.append("KYC review")
    if kyb.status == "warning":
        medium_signals.append("KYB warning")
    if name_result.status == "minor_variation":
        medium_signals.append("name variation")

    if medium_signals:
        return ("medium", "Several review items: " + ", ".join(medium_signals) + ".")

    return ("low", "All baseline checks passed without elevated risk indicators.")
