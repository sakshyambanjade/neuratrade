"""
Fetch candles from Binance with CoinGecko fallback. Keeps shapes consistent.
"""
import time
from typing import List
import httpx
from config import BINANCE_BASE, COINGECKO_BASE, SYMBOL
from db import models


def _binance_klines(limit: int = 200) -> List[dict]:
    url = f"{BINANCE_BASE}/api/v3/klines"
    params = {"symbol": SYMBOL, "interval": "5m", "limit": limit}
    with httpx.Client(timeout=10) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    candles = []
    for row in data:
        candles.append(
            {
                "ts": int(row[0] / 1000),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "source": "binance",
            }
        )
    return candles


def _coingecko_ohlc(limit: int = 200) -> List[dict]:
    url = f"{COINGECKO_BASE}/coins/bitcoin/ohlc"
    params = {"vs_currency": "usd", "days": 1}
    with httpx.Client(timeout=10) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    candles = []
    for ts, open_, high, low, close in data[-limit:]:
        candles.append(
            {
                "ts": int(ts / 1000),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": 0.0,
                "source": "coingecko",
            }
        )
    return candles


def get_candles(limit: int = 200) -> List[dict]:
    try:
        return _binance_klines(limit)
    except Exception:
        return _coingecko_ohlc(limit)


def persist_candles(db, candles: List[dict]):
    for c in candles:
        db.merge(
            models.Candle(
                ts=c["ts"],
                open=c["open"],
                high=c["high"],
                low=c["low"],
                close=c["close"],
                volume=c.get("volume"),
                source=c.get("source", "binance"),
            )
        )
    db.commit()


def latest_candle(db) -> dict:
    row = db.query(models.Candle).order_by(models.Candle.ts.desc()).first()
    if not row:
        return {}
    return {
        "ts": row.ts,
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "close": row.close,
        "volume": row.volume,
        "source": row.source,
    }


def latest_price() -> float:
    candles = get_candles(limit=1)
    return candles[-1]["close"] if candles else 0.0
