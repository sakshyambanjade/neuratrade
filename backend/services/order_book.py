"""
Order book primitives for paper execution simulation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Side = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    quantity: float

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")


@dataclass(frozen=True)
class OrderBookSnapshot:
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    symbol: str = "BTCUSDT"
    ts_ms: int | None = None

    @classmethod
    def from_depth(
        cls,
        *,
        bids: Iterable[tuple[float, float]],
        asks: Iterable[tuple[float, float]],
        symbol: str = "BTCUSDT",
        ts_ms: int | None = None,
    ) -> OrderBookSnapshot:
        bid_levels = tuple(
            sorted((OrderBookLevel(price, qty) for price, qty in bids), key=lambda level: level.price, reverse=True)
        )
        ask_levels = tuple(sorted((OrderBookLevel(price, qty) for price, qty in asks), key=lambda level: level.price))
        if not bid_levels or not ask_levels:
            raise ValueError("order book requires at least one bid and one ask")
        if bid_levels[0].price >= ask_levels[0].price:
            raise ValueError("best bid must be below best ask")
        return cls(bids=bid_levels, asks=ask_levels, symbol=symbol, ts_ms=ts_ms)

    @property
    def best_bid(self) -> float:
        return self.bids[0].price

    @property
    def best_ask(self) -> float:
        return self.asks[0].price

    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread_bps(self) -> float:
        return (self.best_ask - self.best_bid) / self.mid_price * 10_000

    def executable_levels(self, side: Side) -> tuple[OrderBookLevel, ...]:
        return self.asks if side == "BUY" else self.bids
