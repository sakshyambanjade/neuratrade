from fastapi import APIRouter
from db.database import SessionLocal
from db import models
from services.indicator_service import latest_indicators
from services.market_service import get_candles

router = APIRouter()


@router.get("/indicators/latest")
def latest_indicators():
    with SessionLocal() as db:
        rows = (
            db.query(models.Candle)
            .order_by(models.Candle.ts.desc())
            .limit(100)
            .all()
        )
    if not rows:
        candles = get_candles(limit=100)
    else:
        candles = [
            {"ts": r.ts, "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume, "source": r.source}
            for r in rows
        ][::-1]
    inds = latest_indicators(candles)
    inds["ts"] = candles[-1]["ts"] if candles else None
    return inds
