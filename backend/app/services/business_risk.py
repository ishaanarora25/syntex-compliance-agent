"""
Business-risk classification for application assessment.

Combines NAICS / industry inference, foreign-entity status, regulated-business
indicators, and funding-stage signals to produce an overall risk grading and
list of risk factors. Rules are intentionally conservative — anything that
would normally trigger enhanced due diligence at a U.S. commercial bank.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from app.models import BusinessRiskAssessment, WebhookCompanyInfo, WebhookRegulatedCheck

logger = logging.getLogger(__name__)


# High-risk industry keywords keyed to FFIEC BSA/AML manual categories.
_HIGH_RISK_INDUSTRY_KEYWORDS: dict[str, str] = {
    "money services": "MSB — money services business; FinCEN registration required",
    "msb": "MSB — money services business; FinCEN registration required",
    "money transmit": "Money transmitter — state-by-state licensing required",
    "remittance": "Cross-border remittance — high BSA/AML scrutiny",
    "currency exchange": "Currency exchange / forex — designated MSB activity",
    "check cashing": "Check cashing — designated MSB activity",
    "crypto": "Virtual-asset / crypto — convertible-virtual-currency MSB",
    "cryptocurrency": "Virtual-asset / crypto — convertible-virtual-currency MSB",
    "digital asset": "Virtual-asset / crypto — convertible-virtual-currency MSB",
    "virtual currency": "Virtual-asset / crypto — convertible-virtual-currency MSB",
    "cannabis": "Cannabis-related business — federally illegal; FinCEN 2014 guidance applies",
    "marijuana": "Cannabis-related business — federally illegal; FinCEN 2014 guidance applies",
    "hemp": "Hemp/CBD — controlled-substance interface",
    "gambling": "Gaming / gambling — high BSA scrutiny",
    "casino": "Casino — covered financial institution under BSA Title 31",
    "gaming": "Online gaming — high BSA scrutiny",
    "firearm": "Firearms / ammunition dealer — ATF regulated",
    "weapon": "Firearms / ammunition dealer — ATF regulated",
    "ammunition": "Firearms / ammunition dealer — ATF regulated",
    "pawn": "Pawnbroker — designated covered business",
    "precious metal": "Precious metals / dealers in precious metals — covered DPMS",
    "jewelry": "Precious metals / jewelry — covered DPMS over $50k",
    "art deal": "Art / antiquities dealer — Bank-Secrecy-Act extension under AMLA 2020",
    "antiquities": "Art / antiquities dealer — Bank-Secrecy-Act extension under AMLA 2020",
    "shell": "Suspected shell-entity language in description",
    "import export": "Import/export — heightened trade-based money-laundering risk",
    "sanctions": "Self-described sanctions exposure",
    "private military": "Private military / security — defense-controlled exports",
    "real estate fund": "Real estate investment fund — geographic targeting orders may apply",
    "atm": "ATM / IAD operator — designated MSB activity",
}


# Country codes / names that drive a foreign-entity flag.
_US_COUNTRY_TOKENS = {"", "US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}

# Loose proxy for FATF / OFAC comprehensive-sanctioned jurisdictions.
_HIGH_RISK_JURISDICTIONS = {
    "iran", "north korea", "syria", "cuba", "russia", "belarus", "venezuela", "myanmar",
    "afghanistan", "yemen", "somalia",
}


def _scan_keywords(text: str) -> List[Tuple[str, str]]:
    """Return [(keyword, rationale), ...] hits for the high-risk industry table."""
    if not text:
        return []
    lower = text.lower()
    return [(kw, reason) for kw, reason in _HIGH_RISK_INDUSTRY_KEYWORDS.items() if kw in lower]


def assess(
    company_info: WebhookCompanyInfo,
    regulated_check: Optional[WebhookRegulatedCheck],
) -> BusinessRiskAssessment:
    risk_factors: List[str] = []

    # --- Foreign entity --------------------------------------------------
    country = (company_info.countryOfFormation or "").strip().upper()
    is_foreign = country not in _US_COUNTRY_TOKENS
    if is_foreign:
        risk_factors.append(
            f"Foreign-formed entity ({company_info.countryOfFormation}). "
            "Cross-border CDD applies; verify legal existence with foreign registrar."
        )

    country_lower = (company_info.countryOfFormation or "").lower()
    high_risk_jurisdiction = any(j in country_lower for j in _HIGH_RISK_JURISDICTIONS)
    if high_risk_jurisdiction:
        risk_factors.append(
            f"Formation country ({company_info.countryOfFormation}) overlaps with FATF / OFAC "
            "comprehensively-sanctioned jurisdictions — escalate to BSA officer."
        )

    # --- Industry / description / NAICS inference ------------------------
    blended = " ".join(filter(None, [company_info.industry, company_info.description])).strip()
    industry_hits = _scan_keywords(blended)
    is_high_risk_industry = bool(industry_hits)
    if is_high_risk_industry:
        for kw, rationale in industry_hits[:5]:
            risk_factors.append(f"High-risk industry signal ('{kw}') — {rationale}")

    # --- Regulated-business attestation ----------------------------------
    is_regulated = bool(regulated_check and regulated_check.isRegulated)
    if is_regulated:
        cats = ", ".join(regulated_check.selectedCategories) if regulated_check.selectedCategories else "unspecified"
        risk_factors.append(
            f"Applicant self-attested as a regulated business ({cats}). "
            "Confirm relevant licenses and primary regulator before approval."
        )

    # --- Funding stage / amount sanity -----------------------------------
    if company_info.fundingAmount:
        try:
            amount = float(company_info.fundingAmount)
            if amount >= 50_000_000:
                risk_factors.append(
                    f"Large requested facility (${amount:,.0f}). Triggers EDD per "
                    "internal policy (>$50M)."
                )
        except (TypeError, ValueError):
            pass

    # --- NAICS inference (simple keyword fallback) -----------------------
    naics_code, naics_title = _infer_naics(blended)

    # --- Aggregate risk grade -------------------------------------------
    if high_risk_jurisdiction or any(
        kw in {"crypto", "cryptocurrency", "cannabis", "marijuana", "casino", "msb", "money transmit"}
        for kw, _ in industry_hits
    ):
        risk_level = "critical"
    elif is_high_risk_industry or (is_foreign and is_regulated):
        risk_level = "high"
    elif is_foreign or is_regulated or len(risk_factors) >= 2:
        risk_level = "medium"
    else:
        risk_level = "low"

    rationale = (
        f"Risk grade: {risk_level.upper()}. "
        f"Foreign entity: {is_foreign}. "
        f"High-risk industry: {is_high_risk_industry}. "
        f"Self-attested regulated: {is_regulated}. "
        f"{len(risk_factors)} risk factor(s) identified."
    )

    if not risk_factors:
        risk_factors.append("No elevated business-risk indicators detected.")

    return BusinessRiskAssessment(
        risk_level=risk_level,
        is_foreign_entity=is_foreign,
        is_high_risk_industry=is_high_risk_industry,
        is_regulated=is_regulated,
        naics_code=naics_code,
        naics_title=naics_title,
        risk_factors=risk_factors,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Lightweight NAICS inference (mirrors the onboarding-manager naics.ts table
# but kept minimal — only the subset needed for risk grading).
# ---------------------------------------------------------------------------

_NAICS_RULES: list[tuple[list[str], str, str]] = [
    (["software", "saas", "platform", "api", "developer"], "541511", "Custom Computer Programming Services"),
    (["fintech", "payment", "merchant services"], "522320", "Financial Transaction Processing"),
    (["bank", "lending", "loan origination"], "522110", "Commercial Banking"),
    (["crypto", "digital asset", "virtual currency"], "523999", "Other Financial Investment Activities"),
    (["money transmit", "remittance", "msb", "money services"], "522390", "Other Activities Related to Credit Intermediation"),
    (["cannabis", "marijuana", "hemp"], "111998", "All Other Miscellaneous Crop Farming"),
    (["casino", "gambling", "gaming"], "713210", "Casinos (except Casino Hotels)"),
    (["firearm", "ammunition", "weapon"], "423910", "Sporting & Recreational Goods Wholesalers"),
    (["precious metal", "jewelry"], "423940", "Jewelry, Watch, Precious Stone Wholesalers"),
    (["real estate", "property management"], "531110", "Lessors of Residential Buildings"),
    (["construction", "general contractor"], "236220", "Commercial & Institutional Building Construction"),
    (["restaurant", "dining", "cafe", "food service"], "722511", "Full-Service Restaurants"),
    (["e-commerce", "ecommerce", "online retail"], "454110", "Electronic Shopping & Mail-Order Houses"),
    (["consulting", "advisory"], "541610", "Management Consulting Services"),
    (["healthcare", "medical center", "hospital"], "622110", "General Medical & Surgical Hospitals"),
    (["biotech", "biotechnology", "life sciences"], "541714", "Research & Development in Biotechnology"),
    (["import export", "import/export"], "425110", "Business-to-Business Electronic Markets"),
    (["nonprofit", "non-profit", "charity"], "813319", "Other Social Advocacy Organizations"),
]


def _infer_naics(text: str) -> Tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    lower = text.lower()
    for keywords, code, title in _NAICS_RULES:
        if any(kw in lower for kw in keywords):
            return code, title
    return None, None
