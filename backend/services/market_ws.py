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
DEFAULT_STREAMS = ("btcusdt@trade", "btcusdt@bookTicker", "btcusdt@kline_1m")


class CandleSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread_bps: float = 0.0
    volume: float = 0.0
    heartbeat_ts: float | None = None
    candles: list[CandleSnapshot] = Field(default_factory=list)


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
