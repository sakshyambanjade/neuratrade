"""
Slippage calculations in basis points.
"""

from __future__ import annotations

from services.order_book import Side


def estimate_slippage_bps(
    *,
    spread_bps: float,
    order_size: float,
    minute_volume: float,
    volatility: float,
) -> float:
    if spread_bps < 0 or order_size < 0 or volatility < 0:
        raise ValueError("spread, order size, and volatility cannot be negative")
    if spread_bps == 0 and volatility == 0:
        return 0.0
    if minute_volume <= 0:
        return max(spread_bps / 2, volatility * 10_000)

    participation = min(order_size / minute_volume, 1.0)
    spread_cost = spread_bps / 2
    impact_cost = participation * 75
    volatility_cost = volatility * 10_000 * 0.10
    return max(0.0, spread_cost + impact_cost + volatility_cost)


def calculate_slippage_bps(*, side: Side, reference_price: float, execution_price: float) -> float:
    if reference_price <= 0 or execution_price <= 0:
        raise ValueError("prices must be positive")
    if side == "BUY":
        return (execution_price - reference_price) / reference_price * 10_000
    return (reference_price - execution_price) / reference_price * 10_000
