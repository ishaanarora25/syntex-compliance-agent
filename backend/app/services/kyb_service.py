"""
KYB / business-verification stub service (Middesk-style).

DEMO STUB — no real network calls. Returns deterministic results based on
the company info supplied. Mirrors the shape of a real Middesk verification
payload so the frontend can mock the integration without changes when a
real provider is wired up.

In production this would call:
  POST https://api.middesk.com/v1/businesses
  -> poll for `business.attributes` and `business.tins`
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import List

from app.models import KYBResult, WebhookCompanyInfo

logger = logging.getLogger(__name__)


_HIGH_RISK_FORMATION_STATES = {"DE", "WY", "NV"}  # commonly used for shell companies — flag for review, not fail
_SHELL_NAME_TOKENS = {"holdings", "ventures", "capital", "international", "global"}


def _stable_score(seed: str, lo: float, hi: float) -> float:
    """Return a stable pseudo-random float in [lo, hi] keyed off the seed."""
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    n = int(digest[:8], 16)
    bucket = (n % 1000) / 1000.0
    return round(lo + (hi - lo) * bucket, 2)


def _ein_format_ok(ein: str | None) -> bool:
    if not ein:
        return False
    cleaned = re.sub(r"[^0-9]", "", ein)
    return len(cleaned) == 9


def screen(company_info: WebhookCompanyInfo) -> KYBResult:
    checked_at = datetime.now(timezone.utc).isoformat()
    findings: List[str] = []
    watchlists: List[str] = []

    company_name = (company_info.companyName or "").strip()
    seed = f"{company_name}|{company_info.ein or ''}|{company_info.stateOfFormation or ''}"

    # Default optimistic baseline
    raw_score = _stable_score(seed, 0.78, 0.97)
    sos_status = "Active — In Good Standing"
    business_address_verified = True
    tin_match_status = "Match" if _ein_format_ok(company_info.ein) else "No EIN provided"
    ein_match = bool(_ein_format_ok(company_info.ein))

    status = "verified"

    # No EIN at all → "warning", but not failure (foreign entity might lack one)
    if not company_info.ein:
        status = "warning"
        findings.append("No EIN supplied — TIN match could not be performed.")
        raw_score = min(raw_score, 0.7)

    # Foreign entity → cannot run U.S. SoS / TIN-Match
    country = (company_info.countryOfFormation or "").strip().upper()
    is_us = country in ("", "US", "USA", "UNITED STATES")
    if not is_us:
        status = "warning"
        sos_status = f"Outside Middesk coverage — {company_info.countryOfFormation}"
        tin_match_status = "Not applicable (foreign entity)"
        ein_match = None
        business_address_verified = None
        findings.append(
            f"Entity is formed in {company_info.countryOfFormation}; U.S. Secretary-of-State "
            "and TIN-Match checks are not available. Manual registry lookup required."
        )

    # Common shell-company shape — flag for review (not auto-fail)
    name_lower = company_name.lower()
    suffix_tokens = [t for t in _SHELL_NAME_TOKENS if t in name_lower]
    if is_us and (company_info.stateOfFormation or "").upper() in _HIGH_RISK_FORMATION_STATES \
            and suffix_tokens:
        findings.append(
            f"Formed in {company_info.stateOfFormation} with holding-company-style name "
            f"({', '.join(suffix_tokens)}). Confirm operating presence and beneficial ownership."
        )
        if status == "verified":
            status = "warning"

    # Formation date sanity
    if company_info.formationDate:
        try:
            formed = datetime.fromisoformat(company_info.formationDate.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - formed.replace(tzinfo=timezone.utc)).days
            if age_days < 90:
                findings.append(
                    f"Newly formed entity ({age_days} days old). Limited operating history "
                    "available — request additional source-of-funds documentation."
                )
                if status == "verified":
                    status = "warning"
        except Exception:
            findings.append(f"Formation date '{company_info.formationDate}' could not be parsed.")

    if not findings:
        findings.append("All KYB checks passed without exceptions.")

    remarks = (
        f"[DEMO STUB — Middesk] Status: {status}. "
        f"{'No issues detected.' if status == 'verified' else 'Manual review of findings required.'}"
    )

    return KYBResult(
        company_name=company_name,
        status=status,
        secretary_of_state_status=sos_status,
        formation_state=company_info.stateOfFormation,
        formation_date=company_info.formationDate,
        ein_match=ein_match,
        registered_agent="Northwest Registered Agent LLC" if is_us else None,
        watchlists_hit=watchlists,
        tin_match_status=tin_match_status,
        business_address_verified=business_address_verified,
        findings=findings,
        raw_score=raw_score,
        checked_at=checked_at,
        remarks=remarks,
    )
