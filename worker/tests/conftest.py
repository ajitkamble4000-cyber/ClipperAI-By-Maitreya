from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "worker"))
FIXTURES = ROOT / "tests" / "fixtures" / "media"


@pytest.fixture(scope="session")
def podcast() -> Path:
    p = FIXTURES / "podcast.mp4"
    if not p.exists():
        pytest.skip("run tests/fixtures/make_fixtures.py first")
    return p


@pytest.fixture(scope="session")
def sports() -> Path:
    p = FIXTURES / "sports.mp4"
    if not p.exists():
        pytest.skip("run tests/fixtures/make_fixtures.py first")
    return p
