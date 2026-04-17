"""
Loads fixture JSON files from disk and exposes them as typed Fixture objects.
Fixtures are cached at module level — they never change at runtime.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

from app.exceptions import FixtureNotFoundError
from app.models import Fixture, FixtureMeta

logger = logging.getLogger(__name__)

_FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"

_FIXTURE_CACHE: Dict[str, Fixture] = {}


def _load_all() -> None:
    for path in sorted(_FIXTURES_DIR.glob("fixture_*.json")):
        try:
            data = json.loads(path.read_text())
            fixture = Fixture(**data)
            _FIXTURE_CACHE[fixture.fixture_id] = fixture
            logger.info("Loaded fixture %s from %s", fixture.fixture_id, path.name)
        except Exception as exc:
            logger.error("Failed to load fixture %s: %s", path.name, exc)


# Load at import time
_load_all()


def get_fixture(fixture_id: str) -> Fixture:
    fixture = _FIXTURE_CACHE.get(fixture_id)
    if fixture is None:
        raise FixtureNotFoundError(fixture_id)
    return fixture


def list_fixtures() -> List[FixtureMeta]:
    return [
        FixtureMeta(
            fixture_id=f.fixture_id,
            label=f.label,
            scenario=f.scenario,
            description=f.description,
        )
        for f in _FIXTURE_CACHE.values()
    ]
