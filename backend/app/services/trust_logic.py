"""
Trust look-through logic implementing FinCEN beneficial ownership rules.

Rules:
  - Revocable trust: grantor retains full beneficial ownership → substitute
    grantor(s) directly, passing ownership pct through at 100%.
  - Irrevocable trust: look to trustee (controlling party) and named
    beneficiaries with determinable economic interests.
  - Joint revocable trust: both co-grantors pass through at their respective
    grantor_pcts.
  - Discretionary irrevocable trust: treat trustee as UBO by control;
    still look through to listed beneficiaries for economic interest.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.models import FixtureEntity


def should_look_through(entity: FixtureEntity) -> bool:
    """Return True for any trust entity that requires look-through."""
    return entity.entity_type == "trust"


def is_revocable(entity: FixtureEntity) -> bool:
    return entity.entity_subtype == "revocable_trust"


def is_irrevocable(entity: FixtureEntity) -> bool:
    return entity.entity_subtype == "irrevocable_trust"


def resolve_grantor_passthrough(
    trust: FixtureEntity,
    entities_by_id: Dict[str, FixtureEntity],
    incoming_pct: float,
) -> List[Tuple[FixtureEntity, float]]:
    """
    For revocable trusts: return (grantor_entity, effective_pct) pairs.
    Ownership passes through 100% to grantor(s) weighted by grantor_pcts.
    """
    if not trust.grantor_ids:
        return []

    result: List[Tuple[FixtureEntity, float]] = []
    grantor_pcts = trust.grantor_pcts or {gid: 1.0 / len(trust.grantor_ids) for gid in trust.grantor_ids}

    for grantor_id in trust.grantor_ids:
        grantor = entities_by_id.get(grantor_id)
        if grantor is None:
            continue
        share = grantor_pcts.get(grantor_id, 0.0)
        result.append((grantor, incoming_pct * share))

    return result


def resolve_irrevocable_controlling_parties(
    trust: FixtureEntity,
    entities_by_id: Dict[str, FixtureEntity],
    incoming_pct: float,
) -> List[Tuple[FixtureEntity, float, bool]]:
    """
    For irrevocable trusts: return (entity, effective_pct, is_control_only) tuples.

    - Trustees with disposition authority → UBO by control (pct = incoming_pct, control flag True)
    - Named beneficiaries with determinable economic interests → UBO by ownership
    """
    result: List[Tuple[FixtureEntity, float, bool]] = []

    # Grantor_ids on an irrevocable trust hold trustee IDs (modelled this way in fixtures)
    if trust.grantor_ids:
        for trustee_id in trust.grantor_ids:
            trustee = entities_by_id.get(trustee_id)
            if trustee is None:
                continue
            # Mark trustee as having control rights
            trustee.has_control_rights = True
            result.append((trustee, incoming_pct, True))  # control-only

    # Named beneficiaries with economic pcts
    if trust.beneficiary_ids and trust.beneficiary_pcts:
        for ben_id in trust.beneficiary_ids:
            ben = entities_by_id.get(ben_id)
            if ben is None:
                continue
            ben_pct = trust.beneficiary_pcts.get(ben_id, 0.0)
            if ben_pct > 0:
                result.append((ben, incoming_pct * ben_pct, False))

    return result
