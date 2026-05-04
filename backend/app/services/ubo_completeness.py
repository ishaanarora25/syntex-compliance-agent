"""
UBO completeness audit for the self-attested beneficial-ownership form.

Given the list of declared beneficial owners on the application, work out:

  - whether the declared ownership percentages plausibly account for the
    company's full equity stack
  - which owners crossed the 25 % FinCEN CDD threshold
  - whether the 25 % control prong has at least one named individual
  - structured follow-up questions the banker should ask the applicant when
    the disclosure looks incomplete

Rules of thumb:
  - Total <  90 %   →  someone(s) own the missing slice; prompt for it
  - Total >  100 %  →  arithmetic mistake; force re-attestation
  - 0 owners ≥ 25 % →  request a control-prong individual
  - Anyone with a missing DOB / address / ID document → individual follow-up
"""

from __future__ import annotations

import logging
from typing import List

from app.models import UBOCompletenessResult, WebhookBeneficialOwner

logger = logging.getLogger(__name__)


_MATERIAL_OWNERSHIP_THRESHOLD = 25.0
_COMPLETE_THRESHOLD = 90.0   # total must reach this for "complete"
_FOLLOWUP_THRESHOLD = 75.0   # below this we explicitly ask "who owns the rest"


def assess(owners: List[WebhookBeneficialOwner]) -> UBOCompletenessResult:
    follow_up: List[str] = []
    gaps: List[str] = []

    total_pct = round(sum((o.ownershipPercent or 0.0) for o in owners), 2)
    above_threshold = sum(1 for o in owners if (o.ownershipPercent or 0.0) >= _MATERIAL_OWNERSHIP_THRESHOLD)

    if not owners:
        gaps.append("No beneficial owners disclosed.")
        follow_up.append(
            "The application lists zero beneficial owners. Per the FinCEN CDD Rule, "
            "the applicant must disclose at least one individual exercising substantial "
            "control over the entity. Please provide the certifying individual."
        )
        return UBOCompletenessResult(
            total_ownership_pct=0.0,
            declared_owner_count=0,
            above_threshold_count=0,
            coverage_status="incomplete",
            gaps=gaps,
            follow_up_questions=follow_up,
        )

    # --- Coverage --------------------------------------------------------
    if total_pct > 100.5:
        coverage = "over_allocated"
        gaps.append(
            f"Declared ownership totals {total_pct}% (>100%). Arithmetic error in the form."
        )
        follow_up.append(
            f"The disclosed ownership percentages add up to {total_pct}%, which exceeds 100%. "
            "Please review and re-submit the beneficial-ownership form with corrected figures."
        )
    elif total_pct >= _COMPLETE_THRESHOLD:
        coverage = "complete"
    else:
        coverage = "incomplete"
        missing = round(100.0 - total_pct, 2)
        gaps.append(f"{missing}% of ownership unaccounted for (declared total: {total_pct}%).")
        if total_pct < _FOLLOWUP_THRESHOLD:
            follow_up.append(
                f"The declared owners cumulatively hold {total_pct}% of the company. "
                f"Who owns the remaining {missing}%? Please name every individual or entity "
                "that owns 25% or more of the company directly or indirectly."
            )
        else:
            follow_up.append(
                f"The declared owners hold {total_pct}% — please confirm whether the remaining "
                f"{missing}% is held by employees / option pools, treasury shares, or other "
                "individuals not yet disclosed."
            )

    # --- 25% control prong ----------------------------------------------
    if above_threshold == 0 and len(owners) > 0:
        gaps.append(
            "No declared owner crosses the 25% material-ownership threshold; CDD "
            "control prong needs an individual exercising substantial control."
        )
        follow_up.append(
            "No single individual holds 25% or more of the company. Per the FinCEN CDD Rule, "
            "please identify one individual with significant responsibility to control, manage, "
            "or direct the entity (e.g. CEO, CFO, COO, Managing Member, or General Partner)."
        )

    # --- Per-owner data quality -----------------------------------------
    for o in owners:
        owner_label = o.name or f"Owner {o.id}"
        missing_fields = []
        if not o.dob:
            missing_fields.append("date of birth")
        if not o.address or not (o.address.street1 if o.address else None):
            missing_fields.append("residential address")
        if o.isUSCitizen and not o.ssn:
            missing_fields.append("SSN")
        if o.isUSCitizen is False and not o.passportNumber:
            missing_fields.append("passport number")
        if not o.idDocumentUrl and (o.ownershipPercent or 0.0) >= _MATERIAL_OWNERSHIP_THRESHOLD:
            missing_fields.append("government-issued ID image")
        if missing_fields:
            joined = ", ".join(missing_fields)
            follow_up.append(
                f"{owner_label}: please provide the missing {joined} required for KYC verification."
            )

    # --- Foreign-citizen specifics --------------------------------------
    foreign_owners = [o for o in owners if o.isUSCitizen is False]
    for o in foreign_owners:
        if o.passportCountry and o.citizenship and o.passportCountry.upper() != (o.citizenship or "").upper()[:3]:
            follow_up.append(
                f"{o.name}: declared citizenship is {o.citizenship} but passport issuing country is "
                f"{o.passportCountry}. Please clarify which country issued the passport on file."
            )

    if not follow_up:
        follow_up.append("No follow-up questions — beneficial-ownership disclosure looks complete.")

    return UBOCompletenessResult(
        total_ownership_pct=total_pct,
        declared_owner_count=len(owners),
        above_threshold_count=above_threshold,
        coverage_status=coverage,
        gaps=gaps,
        follow_up_questions=follow_up,
    )
