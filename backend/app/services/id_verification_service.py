"""
KYC / identity-verification stub service (Socure-style).

DEMO STUB — no real network calls. Produces deterministic ID-V + Sigma
fraud scores keyed off the supplied identity attributes. Shaped to match
Socure's `/api/3.0/EmailAuthScore` + `/api/3.0/devicerisk` payloads so a
real integration can drop in without UI changes.

In production this would call:
  POST https://api.socure.com/api/3.0/EmailAuthScore
  POST https://api.socure.com/api/3.0/idplus
  POST https://api.socure.com/api/3.0/devicerisk
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import List

from app.models import KYCResult, WebhookBeneficialOwner

logger = logging.getLogger(__name__)


_DISPOSABLE_EMAIL_PROVIDERS = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
    "yopmail.com", "throwaway.email",
}

_HIGH_RISK_CITIZENSHIP = {
    # Loose proxy — these are flagged for additional review, not declined
    "iran", "north korea", "syria", "cuba", "russia", "belarus", "venezuela", "myanmar",
}


def _stable_score(seed: str, lo: float = 0.6, hi: float = 0.99) -> float:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    n = int(digest[:8], 16)
    bucket = (n % 1000) / 1000.0
    return round(lo + (hi - lo) * bucket, 2)


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[-1].lower().strip()


def _ssn_format_ok(ssn: str | None) -> bool:
    if not ssn:
        return False
    cleaned = re.sub(r"[^0-9]", "", ssn)
    return len(cleaned) == 9


def screen(owner: WebhookBeneficialOwner) -> KYCResult:
    checked_at = datetime.now(timezone.utc).isoformat()
    findings: List[str] = []

    name = (owner.name or "").strip() or "Unknown"
    seed = f"{name}|{owner.dob or ''}|{owner.email or ''}|{owner.ssn or ''}|{owner.passportNumber or ''}"

    # Optimistic base
    id_score = _stable_score(seed + "|idv", 0.85, 0.99)
    sigma_score = _stable_score(seed + "|sigma", 0.05, 0.25)
    address_risk = _stable_score(seed + "|addr", 0.05, 0.25)
    email_risk = _stable_score(seed + "|email", 0.05, 0.30)
    phone_risk = _stable_score(seed + "|phone", 0.05, 0.30)
    synthetic_id_risk = "low"
    document_authenticity = "authentic"
    selfie_match: bool | None = True

    overall = "pass"

    # ID-document upload missing → cannot run DocV
    if not owner.idDocumentUrl:
        document_authenticity = "indeterminate"
        selfie_match = None
        id_score = min(id_score, 0.55)
        findings.append(
            "No government-issued ID image provided — DocV could not be performed. "
            "Request a passport or driver's-license image before clearing."
        )
        overall = "review"

    # SSN missing for U.S. citizen → can't run Socure Address/SSN trace
    if owner.isUSCitizen and not _ssn_format_ok(owner.ssn):
        findings.append(
            "U.S. citizen without a valid SSN on file. SSN trace and ITIN cross-check "
            "could not be completed."
        )
        id_score = min(id_score, 0.65)
        overall = "review"

    # Non-U.S. citizen → expect passport
    if owner.isUSCitizen is False and not owner.passportNumber:
        findings.append(
            "Non-U.S. citizen without a passport number. International ID verification "
            "requires a machine-readable passport."
        )
        id_score = min(id_score, 0.6)
        overall = "review"

    # Disposable / risky email
    domain = _email_domain(owner.email)
    if domain and domain in _DISPOSABLE_EMAIL_PROVIDERS:
        email_risk = 0.92
        findings.append(f"Email domain '{domain}' is a known disposable-email provider.")
        sigma_score = max(sigma_score, 0.7)
        overall = "review"

    # High-risk citizenship → still pass-able but adds Sigma weight
    citizenship_lower = (owner.citizenship or "").lower()
    if any(c in citizenship_lower for c in _HIGH_RISK_CITIZENSHIP):
        sigma_score = max(sigma_score, 0.55)
        synthetic_id_risk = "medium"
        findings.append(
            f"Citizenship listed as '{owner.citizenship}' — elevated jurisdictional risk. "
            "Enhanced identity verification recommended."
        )
        if overall == "pass":
            overall = "review"

    # Date of birth sanity
    if owner.dob:
        try:
            dob = datetime.fromisoformat(owner.dob.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dob.replace(tzinfo=timezone.utc)).days // 365
            if age < 18:
                findings.append(f"Beneficial owner DOB indicates age {age} (under 18). Review required.")
                overall = "fail"
            elif age > 100:
                findings.append(f"Beneficial owner DOB indicates age {age} (>100). Likely data error.")
                overall = "review"
        except Exception:
            findings.append(f"Date of birth '{owner.dob}' could not be parsed.")

    # Promote to fail when sigma very high
    if sigma_score >= 0.85:
        overall = "fail"
        findings.append("Sigma fraud score crossed the auto-fail threshold (0.85).")

    if not findings:
        findings.append("All identity-verification checks passed.")

    remarks = (
        f"[DEMO STUB — Socure ID+ / Sigma] Overall: {overall}. ID-V {id_score:.2f}, "
        f"Sigma {sigma_score:.2f}, address-risk {address_risk:.2f}."
    )

    return KYCResult(
        entity_id=owner.id,
        name=name,
        overall_status=overall,
        id_verification_score=id_score,
        sigma_fraud_score=sigma_score,
        address_risk_score=address_risk,
        email_risk_score=email_risk,
        phone_risk_score=phone_risk,
        synthetic_id_risk=synthetic_id_risk,
        document_authenticity=document_authenticity,
        selfie_match=selfie_match,
        findings=findings,
        checked_at=checked_at,
        remarks=remarks,
    )
