from fastapi import APIRouter
from db.database import SessionLocal
from db import models

router = APIRouter()


@router.get("/candles")
def get_candles(limit: int = 200):
    with SessionLocal() as db:
        rows = (
            db.query(models.Candle)
            .order_by(models.Candle.ts.desc())
            .limit(limit)
            .all()
        )
    rows = list(reversed(rows))
    return [
        {
            "time": r.ts,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "source": r.source,
        }
        for r in rows
    ]
