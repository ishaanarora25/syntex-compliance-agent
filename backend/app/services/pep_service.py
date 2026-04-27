"""
Politically Exposed Persons (PEP) stub screening service.

DEMO STUB — no real network calls are made. Results are deterministic based
on a hardcoded stub list and simple name-matching logic. All results carry a
"DEMO STUB" disclaimer in the remarks field.

In production this would call a commercial screening provider (Dow Jones
Risk Center, Refinitiv World-Check, LexisNexis) or a government PEP list.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import datetime, timezone
from typing import Dict, Optional

from app.models import PEPResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stub PEP list — mirrors OFAC stub to keep demo scenarios interconnected.
# Keys are lowercase normalised names; category values use FATF definitions.
# ---------------------------------------------------------------------------

_STUB_LIST: Dict[str, Dict] = {
    # Confirmed foreign PEP — demo scenario B style
    "elena maria vargas": {
        "role": "Close associate of former SICT sub-secretary (alleged, 2019-2021)",
        "country": "Mexico",
        "category": "family_associate",
        "source": "[DEMO STUB] World-Check — Mexican PEP Register",
        "match_score": 0.82,
        "status": "potential_match",
        "remarks": (
            "[DEMO STUB] Named in FGR investigation documents as a close associate of a "
            "former SICT sub-secretary. Not a PEP by direct office, but triggers "
            "family/associate enhanced due diligence per FATF Recommendation 12."
        ),
    },
    # Hard-confirmed hit — for potential future scenarios
    "klaus heinrich bergmann": {
        "role": None,
        "country": "Germany",
        "category": None,
        "source": None,
        "match_score": None,
        "status": "clear",
        "remarks": "[DEMO STUB] No PEP match found on foreign or domestic lists.",
    },
}


def _normalize(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_name.lower().strip()


def _fuzzy_match(name: str) -> Optional[Dict]:
    norm = _normalize(name)
    for key, entry in _STUB_LIST.items():
        if key == norm:
            return entry
        parts = key.split()
        if len(parts) > 1 and all(p in norm for p in parts):
            return entry
    return None


def screen(entity_id: str, name: str) -> PEPResult:
    """Screen a single individual against the stub PEP list."""
    checked_at = datetime.now(timezone.utc).isoformat()
    match = _fuzzy_match(name)

    if match and match.get("status") != "clear":
        logger.info(
            "PEP stub: %s match for entity %s (name=%s) role=%s",
            match["status"], entity_id, name, match.get("role"),
        )
        return PEPResult(
            entity_id=entity_id,
            name=name,
            status=match["status"],
            match_score=match.get("match_score"),
            role=match.get("role"),
            country=match.get("country"),
            category=match.get("category"),
            source=match.get("source"),
            remarks=match.get("remarks"),
            checked_at=checked_at,
        )

    logger.info("PEP stub: clear for entity %s (name=%s)", entity_id, name)
    return PEPResult(
        entity_id=entity_id,
        name=name,
        status="clear",
        source="[DEMO STUB] World-Check",
        remarks="[DEMO STUB] No PEP match found on foreign or domestic lists.",
        checked_at=checked_at,
    )
