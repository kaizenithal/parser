from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def load_fixture():
    """Returns a callable that reads a fixture file by name."""

    def _load(filename: str) -> str:
        path = FIXTURES_DIR / filename
        return path.read_text(encoding="utf-8")

    return _load