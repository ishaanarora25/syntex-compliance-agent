"""
FinCEN rules digest loader.

Reads `backend/fixtures/fincen_rules.md` once at import and exposes:

- `RULES_MARKDOWN`: the full digest as a string (embedded in agent system prompt).
- `SECTIONS`: tag → SectionMeta index keyed by `[tag]` markers in the digest.
- `lookup(tag)`: resolve a citation tag to its section title + first-paragraph snippet.

The digest is curated and refreshed manually — we ship it with the repo so the agent
always has FinCEN rules in-context without a network call.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


_DIGEST_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "fincen_rules.md"


@dataclass(frozen=True)
class SectionMeta:
    tag: str           # e.g. "31CFR1010.230"
    title: str         # e.g. "Customer Due Diligence (CDD) Rule — 31 CFR § 1010.230"
    snippet: str       # first non-heading paragraph; suitable as a citation excerpt


# Matches lines like:  ## [31CFR1010.230] Customer Due Diligence (CDD) Rule — ...
_HEADING_RE = re.compile(r"^##\s+\[([^\]]+)\]\s+(.+)$")


def _load() -> tuple[str, Dict[str, SectionMeta]]:
    if not _DIGEST_PATH.exists():
        logger.warning("FinCEN digest not found at %s", _DIGEST_PATH)
        return "", {}

    raw = _DIGEST_PATH.read_text(encoding="utf-8")

    sections: Dict[str, SectionMeta] = {}
    current_tag: Optional[str] = None
    current_title: Optional[str] = None
    current_body: list[str] = []

    def flush() -> None:
        if current_tag and current_title:
            snippet = _first_paragraph(current_body)
            sections[current_tag] = SectionMeta(
                tag=current_tag,
                title=current_title,
                snippet=snippet,
            )

    for line in raw.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            current_tag = m.group(1).strip()
            current_title = m.group(2).strip()
            current_body = []
        else:
            if current_tag is not None:
                current_body.append(line)
    flush()

    logger.info("Loaded FinCEN digest: %d sections, %d chars", len(sections), len(raw))
    return raw, sections


def _first_paragraph(body_lines: list[str]) -> str:
    """Return the first non-empty paragraph, stripped of markdown bold and capped."""
    paragraph: list[str] = []
    started = False
    for line in body_lines:
        stripped = line.strip()
        if not started:
            if not stripped:
                continue
            started = True
            paragraph.append(stripped)
        else:
            if not stripped:
                break
            paragraph.append(stripped)
    text = " ".join(paragraph)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    if len(text) > 280:
        text = text[:277] + "…"
    return text


RULES_MARKDOWN, SECTIONS = _load()


def lookup(tag: str) -> Optional[SectionMeta]:
    """Resolve a citation tag to its section, or None if unknown."""
    return SECTIONS.get(tag)


def known_tags() -> list[str]:
    return list(SECTIONS.keys())
