"""
Binance WebSocket live market feed.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any

import websockets
from pydantic import BaseModel, ConfigDict, Field

BINANCE_WS_BASE = "wss://stream.binance.com:9443/stream"
DEFAULT_STREAMS = ("btcusdt@trade", "btcusdt@bookTicker", "btcusdt@kline_1m", "btcusdt@depth20@100ms")


class CandleSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool


class OrderBookLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float
    quantity: float


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread_bps: float = 0.0
    volume: float = 0.0
    heartbeat_ts: float | None = None
    reconnect_count: int = 0
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)
    candles: list[CandleSnapshot] = Field(default_factory=list)


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    status: str
    reason: str = ""
    data_gap: bool = False
    age_seconds: float | None = None


class TickValidator:
    def __init__(
        self,
        *,
        max_spread_pct: float = 0.005,
        max_staleness_sec: float = 5.0,
        data_gap_sec: float | None = None,
    ) -> None:
        self.max_spread_pct = max_spread_pct
        self.max_staleness_sec = max_staleness_sec
        self.data_gap_sec = data_gap_sec

    def validate(self, snapshot: MarketSnapshot, *, now: float | None = None) -> ValidationResult:
        now = time.time() if now is None else now
        heartbeat_ts = snapshot.heartbeat_ts
        age_seconds = None if heartbeat_ts is None else max(0.0, now - heartbeat_ts)
        data_gap = bool(
            heartbeat_ts is None
            or (self.data_gap_sec is not None and age_seconds is not None and age_seconds > self.data_gap_sec)
        )

        if heartbeat_ts is None:
            return ValidationResult(
                valid=False,
                status="missing",
                reason="no market heartbeat has been received",
                data_gap=data_gap,
                age_seconds=age_seconds,
            )
        if age_seconds is not None and age_seconds > self.max_staleness_sec:
            return ValidationResult(
                valid=False,
                status="stale",
                reason=f"market heartbeat age {age_seconds:.3f}s exceeds {self.max_staleness_sec:.3f}s",
                data_gap=data_gap,
                age_seconds=age_seconds,
            )
        if snapshot.bid is not None and snapshot.ask is not None and snapshot.bid >= snapshot.ask:
            return ValidationResult(
                valid=False,
                status="crossed",
                reason="bid is greater than or equal to ask",
                data_gap=data_gap,
                age_seconds=age_seconds,
            )
        if snapshot.last_price is not None and (not math.isfinite(snapshot.last_price) or snapshot.last_price <= 0):
            return ValidationResult(
                valid=False,
                status="zero_price",
                reason="last price is not finite and positive",
                data_gap=data_gap,
                age_seconds=age_seconds,
            )
        if snapshot.bid is not None and (not math.isfinite(snapshot.bid) or snapshot.bid <= 0):
            return ValidationResult(
                valid=False,
                status="invalid_bid",
                reason="bid is not finite and positive",
                data_gap=data_gap,
                age_seconds=age_seconds,
            )
        if snapshot.ask is not None and (not math.isfinite(snapshot.ask) or snapshot.ask <= 0):
            return ValidationResult(
                valid=False,
                status="invalid_ask",
                reason="ask is not finite and positive",
                data_gap=data_gap,
                age_seconds=age_seconds,
            )
        if snapshot.bid is None and snapshot.ask is None and snapshot.last_price is None:
            return ValidationResult(
                valid=False,
                status="missing_price",
                reason="snapshot has no price, bid, or ask",
                data_gap=data_gap,
                age_seconds=age_seconds,
            )

        spread_pct = snapshot.spread_bps / 10_000
        if spread_pct > self.max_spread_pct:
            return ValidationResult(
                valid=False,
                status="wide_spread",
                reason=f"spread {spread_pct:.6f} exceeds {self.max_spread_pct:.6f}",
                data_gap=data_gap,
                age_seconds=age_seconds,
            )

        return ValidationResult(valid=True, status="valid", data_gap=data_gap, age_seconds=age_seconds)


class BinanceMarketWebSocket:
    def __init__(
        self,
        *,
        symbol: str = "btcusdt",
        streams: tuple[str, ...] | None = None,
        max_candles: int = 500,
        backoff_initial: float = 1.0,
        backoff_max: float = 30.0,
    ) -> None:
        self.symbol = symbol.lower()
        self.streams = streams or DEFAULT_STREAMS
        self.max_candles = max_candles
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.last_price: float | None = None
        self.bid: float | None = None
        self.ask: float | None = None
        self.spread_bps = 0.0
        self.volume = 0.0
        self.heartbeat_ts: float | None = None
        self.reconnect_count = 0
        self.bids: list[OrderBookLevel] = []
        self.asks: list[OrderBookLevel] = []
        self.candle_history: list[CandleSnapshot] = []
        self._shutdown = asyncio.Event()
        self._ws: Any | None = None

    @property
    def url(self) -> str:
        stream_path = "/".join(self.streams)
        return f"{BINANCE_WS_BASE}?streams={stream_path}"

    async def run(self) -> None:
        backoff = self.backoff_initial
        while not self._shutdown.is_set():
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as websocket:
                    self._ws = websocket
                    backoff = self.backoff_initial
                    async for message in websocket:
                        if self._shutdown.is_set():
                            break
                        self.process_message(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._shutdown.is_set():
                    break
                self.reconnect_count += 1
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.backoff_max)
            finally:
                self._ws = None

    async def shutdown(self) -> None:
        self._shutdown.set()
        if self._ws is not None:
            await self._ws.close()

    def process_message(self, message: str | bytes | dict[str, Any]) -> None:
        try:
            payload = self._decode_message(message)
            data = payload.get("data", payload)
            event_type = data.get("e")
            if event_type == "trade":
                self._handle_trade(data)
            elif event_type == "bookTicker":
                self._handle_book_ticker(data)
            elif event_type == "kline":
                self._handle_kline(data)
            elif event_type == "depthUpdate":
                self._handle_depth(data)
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return

    def get_snapshot(self) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=self.symbol.upper(),
            last_price=self.last_price,
            bid=self.bid,
            ask=self.ask,
            spread_bps=self.spread_bps,
            volume=self.volume,
            heartbeat_ts=self.heartbeat_ts,
            reconnect_count=self.reconnect_count,
            bids=list(self.bids),
            asks=list(self.asks),
            candles=list(self.candle_history),
        )

    def _decode_message(self, message: str | bytes | dict[str, Any]) -> dict[str, Any]:
        if isinstance(message, dict):
            return message
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        decoded = json.loads(message)
        if not isinstance(decoded, dict):
            raise TypeError("message must decode to an object")
        return decoded

    def _handle_trade(self, data: dict[str, Any]) -> None:
        price = _finite_float(data["p"])
        quantity = _finite_float(data.get("q", 0.0))
        if price <= 0:
            return
        self.last_price = price
        self.volume = max(0.0, quantity)
        self._heartbeat()

    def _handle_book_ticker(self, data: dict[str, Any]) -> None:
        bid = _finite_float(data["b"])
        ask = _finite_float(data["a"])
        if bid <= 0 or ask <= 0 or ask < bid:
            return
        self.bid = bid
        self.ask = ask
        midpoint = (bid + ask) / 2
        self.spread_bps = (ask - bid) / midpoint * 10_000 if midpoint > 0 else 0.0
        self._heartbeat()

    def _handle_depth(self, data: dict[str, Any]) -> None:
        bids = _levels(data.get("b", []), reverse=True)
        asks = _levels(data.get("a", []), reverse=False)
        if bids:
            self.bids = bids[:20]
            self.bid = self.bids[0].price
        if asks:
            self.asks = asks[:20]
            self.ask = self.asks[0].price
        if self.bid is not None and self.ask is not None and self.ask >= self.bid:
            midpoint = (self.bid + self.ask) / 2
            self.spread_bps = (self.ask - self.bid) / midpoint * 10_000 if midpoint > 0 else 0.0
        self._heartbeat()

    def _handle_kline(self, data: dict[str, Any]) -> None:
        kline = data["k"]
        candle = CandleSnapshot(
            ts=int(kline["t"] / 1000),
            open=_finite_float(kline["o"]),
            high=_finite_float(kline["h"]),
            low=_finite_float(kline["l"]),
            close=_finite_float(kline["c"]),
            volume=_finite_float(kline["v"]),
            closed=bool(kline["x"]),
        )
        self.last_price = candle.close
        self.volume = candle.volume
        if candle.closed:
            self.candle_history.append(candle)
            self.candle_history = self.candle_history[-self.max_candles :]
        self._heartbeat()

    def _heartbeat(self) -> None:
        self.heartbeat_ts = time.time()


def _finite_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("value must be finite")
    return number


def _levels(raw_levels: Any, *, reverse: bool) -> list[OrderBookLevel]:
    levels: list[OrderBookLevel] = []
    for raw_level in raw_levels:
        if not isinstance(raw_level, (list, tuple)) or len(raw_level) < 2:
            continue
        price = _finite_float(raw_level[0])
        quantity = _finite_float(raw_level[1])
        if price <= 0 or quantity <= 0:
            continue
        levels.append(OrderBookLevel(price=price, quantity=quantity))
    return sorted(levels, key=lambda level: level.price, reverse=reverse)
