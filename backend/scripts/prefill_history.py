"""
Pre-fill historical Binance candles for paper-trading research runs.

Usage from the repository root:
    make prefill

Usage from backend/:
    python scripts/prefill_history.py --days 7 --symbol BTCUSDT --interval 1m
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import BINANCE_BASE, SYMBOL  # noqa: E402

from db.database import SessionLocal, init_db  # noqa: E402
from services.market_service import persist_candles  # noqa: E402

DEFAULT_INTERVAL = "1m"
DEFAULT_DAYS = 7.0
DEFAULT_LIMIT = 1000
DEFAULT_SLEEP_SECONDS = 0.2
INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
}

RawKline = list[Any]
Fetcher = Callable[..., list[RawKline]]


def fetch_chunk(
    *,
    start_ms: int,
    end_ms: int,
    symbol: str,
    interval: str,
    limit: int,
    base_url: str,
    timeout: float = 15.0,
) -> list[RawKline]:
    url = f"{base_url.rstrip('/')}/api/v3/klines"
    with httpx.Client(timeout=timeout) as client:
        response = client.get(
            url,
            params={
                "symbol": symbol.upper(),
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": limit,
            },
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, list):
        raise TypeError("Binance klines response must be a list")
    return data


def rows_to_candles(rows: list[RawKline]) -> list[dict[str, float | int | str]]:
    candles: list[dict[str, float | int | str]] = []
    for row in rows:
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


def prefill_history(
    *,
    days: float = DEFAULT_DAYS,
    symbol: str = SYMBOL,
    interval: str = DEFAULT_INTERVAL,
    limit: int = DEFAULT_LIMIT,
    base_url: str = BINANCE_BASE,
    start_ms: int | None = None,
    end_ms: int | None = None,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    dry_run: bool = False,
    fetcher: Fetcher = fetch_chunk,
) -> int:
    if days <= 0:
        raise ValueError("days must be positive")
    if limit <= 0 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")

    end_ms = end_ms or int(time.time() * 1000)
    start_ms = start_ms if start_ms is not None else end_ms - int(days * 24 * 60 * 60 * 1000)
    if start_ms >= end_ms:
        raise ValueError("start_ms must be earlier than end_ms")
    interval_ms = INTERVAL_MS.get(interval, 1)
    next_start_ms = start_ms
    candles_loaded = 0

    if not dry_run:
        init_db()

    while next_start_ms <= end_ms:
        rows = fetcher(
            start_ms=next_start_ms,
            end_ms=end_ms,
            symbol=symbol,
            interval=interval,
            limit=limit,
            base_url=base_url,
        )
        rows = [row for row in rows if start_ms <= int(row[0]) <= end_ms]
        if not rows:
            break

        candles = rows_to_candles(rows)
        if not dry_run:
            with SessionLocal() as db:
                persist_candles(db, candles)

        candles_loaded += len(candles)
        last_open_ms = int(rows[-1][0])
        candidate_next_start_ms = last_open_ms + interval_ms
        if candidate_next_start_ms <= next_start_ms:
            break
        next_start_ms = candidate_next_start_ms

        if len(rows) < limit:
            break
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return candles_loaded


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pre-fill Binance historical candles into the SQLite research DB.")
    parser.add_argument("--days", type=float, default=DEFAULT_DAYS, help="Historical window length in days.")
    parser.add_argument("--symbol", default=SYMBOL, help="Binance symbol, e.g. BTCUSDT.")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, help="Binance kline interval, e.g. 1m.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Binance page size, max 1000.")
    parser.add_argument("--base-url", default=BINANCE_BASE, help="Binance REST API base URL.")
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS, help="Pause between pages.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and count candles without writing the DB.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    loaded = prefill_history(
        days=args.days,
        symbol=args.symbol,
        interval=args.interval,
        limit=args.limit,
        base_url=args.base_url,
        sleep_seconds=args.sleep_seconds,
        dry_run=args.dry_run,
    )
    suffix = " (dry run; DB unchanged)" if args.dry_run else ""
    print(f"Loaded {loaded} candles{suffix}")


if __name__ == "__main__":
    main()
