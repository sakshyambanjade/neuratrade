import pytest
from db.database import init_db, SessionLocal


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    init_db()
    yield
    with SessionLocal() as db:
        db.close()
