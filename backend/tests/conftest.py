import sys
from pathlib import Path

# Ensure backend package is importable when tests are run from repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from db.database import init_db, SessionLocal


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    init_db()
    yield
    with SessionLocal() as db:
        db.close()
