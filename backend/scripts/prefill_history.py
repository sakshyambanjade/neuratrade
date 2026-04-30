"""
Pre-fill historical Binance candles for paper-trading research runs.

The default target is 90 days of 1-minute BTCUSDT candles: 129,600 data
points. The loader is resumable: it inspects the DB first and fetches only
missing candle timestamps, so an interrupted run continues at the next gap.

Usage from the repository root:
    make prefill

Usage from backend/:
    python scripts/prefill_history.py
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import BINANCE_BASE, SYMBOL  # noqa: E402

from db import models  # noqa: E402
from db.database import SessionLocal, init_db  # noqa: E402
from services.market_service import persist_candles  # noqa: E402

DEFAULT_INTERVAL = "1m"
DEFAULT_DAYS = 90.0
DEFAULT_TARGET_POINTS = 129_600
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


def expected_points(days: float, interval: str = DEFAULT_INTERVAL) -> int:
    interval_ms = _interval_ms(interval)
    return int(days * 24 * 60 * 60 * 1000 / interval_ms)


def target_window(
    *,
    days: float = DEFAULT_DAYS,
    interval: str = DEFAULT_INTERVAL,
    target_points: int | None = DEFAULT_TARGET_POINTS,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> tuple[int, int, int]:
    interval_ms = _interval_ms(interval)
    if end_ms is None:
        now_ms = int(time.time() * 1000)
        last_open_ms = ((now_ms // interval_ms) - 1) * interval_ms
    else:
        last_open_ms = (end_ms // interval_ms) * interval_ms

    if start_ms is None:
        points = target_points or expected_points(days, interval)
        first_open_ms = last_open_ms - (points - 1) * interval_ms
    else:
        first_open_ms = ((start_ms + interval_ms - 1) // interval_ms) * interval_ms
        points = ((last_open_ms - first_open_ms) // interval_ms) + 1

    if points <= 0 or first_open_ms > last_open_ms:
        raise ValueError("target window contains no candles")
    return first_open_ms, last_open_ms, points


def existing_candle_timestamps(*, start_ms: int, end_ms: int) -> set[int]:
    start_ts = start_ms // 1000
    end_ts = end_ms // 1000
    with SessionLocal() as db:
        rows = db.execute(
            select(models.Candle.ts).where(models.Candle.ts >= start_ts, models.Candle.ts <= end_ts)
        ).scalars()
        return {int(ts) for ts in rows}


def missing_ranges(
    *,
    existing_ts: set[int],
    start_open_ms: int,
    last_open_ms: int,
    interval: str = DEFAULT_INTERVAL,
) -> list[tuple[int, int]]:
    interval_ms = _interval_ms(interval)
    ranges: list[tuple[int, int]] = []
    missing_start: int | None = None
    open_ms = start_open_ms
    while open_ms <= last_open_ms:
        if open_ms // 1000 not in existing_ts:
            if missing_start is None:
                missing_start = open_ms
        elif missing_start is not None:
            ranges.append((missing_start, open_ms - 1))
            missing_start = None
        open_ms += interval_ms
    if missing_start is not None:
        ranges.append((missing_start, last_open_ms + interval_ms - 1))
    return ranges


def prefill_history(
    *,
    days: float = DEFAULT_DAYS,
    symbol: str = SYMBOL,
    interval: str = DEFAULT_INTERVAL,
    target_points: int | None = DEFAULT_TARGET_POINTS,
    limit: int = DEFAULT_LIMIT,
    base_url: str = BINANCE_BASE,
    start_ms: int | None = None,
    end_ms: int | None = None,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    dry_run: bool = False,
    existing_ts: set[int] | None = None,
    fetcher: Fetcher = fetch_chunk,
) -> int:
    if days <= 0:
        raise ValueError("days must be positive")
    if limit <= 0 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    if target_points is not None and target_points <= 0:
        raise ValueError("target_points must be positive")

    start_open_ms, last_open_ms, expected = target_window(
        days=days,
        interval=interval,
        target_points=target_points,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    interval_ms = _interval_ms(interval)
    candles_loaded = 0

    if not dry_run:
        init_db()
    existing = set(existing_ts) if existing_ts is not None else set()
    if not dry_run and existing_ts is None:
        existing = existing_candle_timestamps(start_ms=start_open_ms, end_ms=last_open_ms)

    print(
        f"Target window: {expected} candles from {start_open_ms // 1000} "
        f"to {last_open_ms // 1000}. Existing: {len(existing)}."
    )
    ranges = missing_ranges(
        existing_ts=existing,
        start_open_ms=start_open_ms,
        last_open_ms=last_open_ms,
        interval=interval,
    )
    if not ranges:
        print(f"Already complete: {len(existing)}/{expected} candles present.")
        return 0

    for range_start_ms, range_end_ms in ranges:
        next_start_ms = range_start_ms
        while next_start_ms <= range_end_ms:
            rows = fetcher(
                start_ms=next_start_ms,
                end_ms=range_end_ms,
                symbol=symbol,
                interval=interval,
                limit=limit,
                base_url=base_url,
            )
            rows = [row for row in rows if next_start_ms <= int(row[0]) <= range_end_ms]
            if not rows:
                break

            new_rows = [row for row in rows if int(row[0]) // 1000 not in existing]
            candles = rows_to_candles(new_rows)
            if candles and not dry_run:
                with SessionLocal() as db:
                    persist_candles(db, candles)

            for row in new_rows:
                existing.add(int(row[0]) // 1000)
            candles_loaded += len(candles)
            print(f"Loaded {len(existing)}/{expected} candles...", end="\r")

            candidate_next_start_ms = int(rows[-1][0]) + interval_ms
            if candidate_next_start_ms <= next_start_ms:
                break
            next_start_ms = candidate_next_start_ms

            if len(rows) < limit:
                break
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    print()
    return candles_loaded


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pre-fill Binance historical candles into the SQLite research DB.")
    parser.add_argument("--days", type=float, default=DEFAULT_DAYS, help="Historical window length in days.")
    parser.add_argument("--symbol", default=SYMBOL, help="Binance symbol, e.g. BTCUSDT.")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, help="Binance kline interval, e.g. 1m.")
    parser.add_argument("--target-points", type=int, default=DEFAULT_TARGET_POINTS, help="Exact candle target.")
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
        target_points=args.target_points,
        limit=args.limit,
        base_url=args.base_url,
        sleep_seconds=args.sleep_seconds,
        dry_run=args.dry_run,
    )
    suffix = " (dry run; DB unchanged)" if args.dry_run else ""
    expected = args.target_points or expected_points(args.days, args.interval)
    print(f"Done. Loaded {loaded} new candles{suffix}. Target: {expected}.")


def _interval_ms(interval: str) -> int:
    try:
        return INTERVAL_MS[interval]
    except KeyError as exc:
        supported = ", ".join(sorted(INTERVAL_MS))
        raise ValueError(f"unsupported interval {interval!r}; supported: {supported}") from exc


if __name__ == "__main__":
    main()
