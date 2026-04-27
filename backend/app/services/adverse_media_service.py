"""
Adverse media stub screening service.

DEMO STUB — no real network calls. Results are keyed off hardcoded name
matches so the scenarios reproduce deterministically. In production this
would hit a news aggregator (Dow Jones Factiva, LexisNexis Adverse Media,
RDC, Nexis Diligence) and apply an LLM summarization layer.

Every response carries a "DEMO STUB" disclaimer in remarks.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models import AdverseMediaResult

logger = logging.getLogger(__name__)


_STUB_LIST: Dict[str, Dict[str, Any]] = {
    "elena maria vargas": {
        "status": "potential_match",
        "categories": ["corruption", "regulatory"],
        "severity": "high",
        "articles": [
            {
                "headline": "Constructora ligada a escándalo de sobornos en contratos federales",
                "source": "Reforma (Mexico)",
                "date": "2022-06-14",
                "url": "https://www.reforma.com/" ,
                "disposition": "Investigation opened — charges dropped August 2022",
            },
            {
                "headline": "Mexico drops bribery charges against real estate investor Elena Vargas",
                "source": "Reuters",
                "date": "2022-08-29",
                "url": "https://www.reuters.com/",
                "disposition": "Case closed — subject to reopening",
            },
        ],
        "remarks": (
            "[DEMO STUB] Named in 2022 Mexican federal bribery investigation. "
            "Charges dropped; investigation closed. Elevated BSA risk per FinCEN "
            "guidance on individuals with adverse media history."
        ),
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


def screen(
    entity_id: str,
    name: str,
    fixture_adverse_media: Optional[Dict[str, Any]] = None,
) -> AdverseMediaResult:
    """
    Screen a single individual against the stub adverse media index.

    If the caller passes `fixture_adverse_media` (the dict attached to a
    FixtureEntity in legacy fixtures), that is merged in — we prefer fixture
    data over stub data to keep the demo scenarios narratively consistent.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    match = _fuzzy_match(name)

    if fixture_adverse_media:
        headline = fixture_adverse_media.get("headline", "See report")
        source = fixture_adverse_media.get("source", "Unknown")
        date = fixture_adverse_media.get("date", "Unknown")
        disposition = fixture_adverse_media.get("disposition", "Unknown")
        summary_text = fixture_adverse_media.get("summary", "")
        return AdverseMediaResult(
            entity_id=entity_id,
            name=name,
            status="potential_match",
            categories=["corruption", "regulatory"],
            severity="high",
            articles=[
                {
                    "headline": headline,
                    "source": source,
                    "date": date,
                    "disposition": disposition,
                    "summary": summary_text,
                }
            ],
            remarks=(
                "[DEMO STUB] Adverse media match driven by applicant-submitted "
                "adverse media report. Enhanced Due Diligence required."
            ),
            checked_at=checked_at,
        )

    if match:
        return AdverseMediaResult(
            entity_id=entity_id,
            name=name,
            status=match["status"],
            categories=list(match.get("categories", [])),
            articles=list(match.get("articles", [])),
            severity=match.get("severity"),
            remarks=match.get("remarks"),
            checked_at=checked_at,
        )

    return AdverseMediaResult(
        entity_id=entity_id,
        name=name,
        status="clear",
        categories=[],
        articles=[],
        severity="low",
        remarks="[DEMO STUB] No adverse media matches found across monitored sources.",
        checked_at=checked_at,
    )
