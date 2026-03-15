import json

import pytest
from fastapi.testclient import TestClient

from main import app
from db.database import SessionLocal
from db import models
from config import API_KEY
from services import market_service


@pytest.fixture(autouse=True)
def clean_candles():
    # Ensure a clean slate for each test
    with SessionLocal() as db:
        db.query(models.Candle).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(models.Candle).delete()
        db.commit()


def test_candles_fallback_seeds_db(monkeypatch):
    stub_candles = [
        {
            "ts": 1710000000,
            "open": 50000.0,
            "high": 50500.0,
            "low": 49900.0,
            "close": 50300.0,
            "volume": 123.0,
            "source": "stub",
        },
        {
            "ts": 1710000300,
            "open": 50300.0,
            "high": 50600.0,
            "low": 50100.0,
            "close": 50450.0,
            "volume": 111.0,
            "source": "stub",
        },
    ]

    def _fake_get_candles(limit=200):
        return stub_candles[:limit]

    monkeypatch.setattr(market_service, "get_candles", _fake_get_candles)

    client = TestClient(app)
    resp = client.get("/candles", headers={"x-api-key": API_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == len(stub_candles)
    # shape verification
    assert {"time", "open", "high", "low", "close", "volume", "source"} <= set(data[0].keys())

    # ensure persistence to DB
    with SessionLocal() as db:
        count = db.query(models.Candle).count()
    assert count == len(stub_candles)
