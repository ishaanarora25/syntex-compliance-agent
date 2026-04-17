"""
OFAC / SDN stub screening service.

This is a DEMO STUB — no real network calls are made. Results are
deterministic based on a hardcoded stub list and name-matching logic.
All results carry a clear "DEMO STUB" disclaimer in the remarks field.

In production this would call the OFAC SDN API or a third-party
sanctions screening provider (e.g. Dow Jones, Refinitiv World-Check).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from app.models import OFACResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stub SDN/Consolidated list entries.
# Keys are lowercase normalized names for fuzzy matching.
# ---------------------------------------------------------------------------

_STUB_LIST: Dict[str, Dict] = {
    # Exact-match entries (match_score = 1.0)
    "ivan nikolaevich petrov": {
        "sdn_name": "PETROV, Ivan Nikolaevich",
        "program": "UKRAINE-EO13662",
        "list_type": "SDN",
        "remarks": "[DEMO STUB] DOB 15 Mar 1972; POB Moscow, Russia.",
        "match_score": 1.0,
        "status": "confirmed_hit",
    },
    # Partial / fuzzy-match entry — Elena Vargas gets a potential match
    # to demonstrate the OFAC check UI (not a confirmed SDN listing).
    "vargas elena": {
        "sdn_name": "VARGAS, Elena M.",
        "program": "OFAC-CONSOLIDATED",
        "list_type": "Consolidated",
        "remarks": (
            "[DEMO STUB] Fuzzy name match (score 0.73). "
            "Different date of birth and passport on record. "
            "Manual verification required before clearing."
        ),
        "match_score": 0.73,
        "status": "potential_match",
    },
}


def _normalize(name: str) -> str:
    """Lowercase and strip accents/punctuation for matching."""
    import unicodedata
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_name.lower().strip()


def _fuzzy_match(name: str) -> Optional[Dict]:
    """Check if any stub entry is a substring match of the normalized name."""
    norm = _normalize(name)
    for key, entry in _STUB_LIST.items():
        # Exact match
        if key == norm:
            return entry
        # Partial key match (e.g. "vargas elena" in "elena maria vargas")
        parts = key.split()
        if all(p in norm for p in parts):
            return entry
    return None


def screen(entity_id: str, name: str) -> OFACResult:
    """
    Screen a single individual against the stub OFAC list.

    Args:
        entity_id: Internal entity ID for logging.
        name: Full legal name to screen.

    Returns:
        OFACResult with status "clear", "potential_match", or "confirmed_hit".
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    match = _fuzzy_match(name)

    if match:
        logger.info(
            "OFAC stub: %s match for entity %s (name=%s) program=%s score=%.2f",
            match["status"],
            entity_id,
            name,
            match.get("program"),
            match.get("match_score", 0),
        )
        return OFACResult(
            entity_id=entity_id,
            name=name,
            status=match["status"],
            match_score=match.get("match_score"),
            sdn_name=match.get("sdn_name"),
            program=match.get("program"),
            list_type=match.get("list_type"),
            remarks=match.get("remarks"),
            checked_at=checked_at,
        )

    logger.info("OFAC stub: clear for entity %s (name=%s)", entity_id, name)
    return OFACResult(
        entity_id=entity_id,
        name=name,
        status="clear",
        remarks="[DEMO STUB] No matches found in SDN or Consolidated Sanctions List.",
        checked_at=checked_at,
    )
