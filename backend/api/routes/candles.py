from fastapi import APIRouter
from db.database import SessionLocal
from db import models
from services import market_service

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

    # Seed database on empty installs using the live market feed
    if not rows:
        candles = market_service.get_candles(limit=limit)
        # Persist best-effort (don't fail the request if DB write fails)
        try:
            with SessionLocal() as db:
                market_service.persist_candles(db, candles)
        except Exception:
            pass
        # Return the freshly fetched candles immediately
        rows = [
            models.Candle(
                ts=c["ts"],
                open=c["open"],
                high=c["high"],
                low=c["low"],
                close=c["close"],
                volume=c.get("volume"),
                source=c.get("source", "binance"),
            )
            for c in candles
        ]

    rows = list(reversed(rows))[:limit]
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
