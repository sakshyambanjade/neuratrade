"""
Research metrics for equity curves and trade outcomes.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from statistics import mean, pstdev


def _finite_series(values: Iterable[float]) -> list[float]:
    return [float(value) for value in values if math.isfinite(float(value))]


def _safe_number(value: float) -> float:
    return value if math.isfinite(value) else 0.0


def cumulative_return(equity_series: Iterable[float]) -> float:
    values = _finite_series(equity_series)
    if len(values) < 2 or values[0] <= 0:
        return 0.0
    return _safe_number(values[-1] / values[0] - 1)


def simple_returns(equity_series: Iterable[float]) -> list[float]:
    values = _finite_series(equity_series)
    if len(values) < 2:
        return []

    returns: list[float] = []
    for previous, current in zip(values, values[1:], strict=False):
        if previous <= 0:
            returns.append(0.0)
            continue
        returns.append(_safe_number(current / previous - 1))
    return returns


def max_drawdown(equity_series: Iterable[float]) -> float:
    values = _finite_series(equity_series)
    if not values:
        return 0.0

    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak <= 0:
            continue
        drawdown = (peak - value) / peak
        worst = max(worst, drawdown)
    return _safe_number(worst)


def sharpe_ratio(equity_series: Iterable[float], periods_per_year: int = 525_600) -> float:
    returns = simple_returns(equity_series)
    if len(returns) < 2 or periods_per_year <= 0:
        return 0.0

    volatility = pstdev(returns)
    if volatility <= 0:
        return 0.0
    return _safe_number(mean(returns) / volatility * math.sqrt(periods_per_year))


def win_rate(trade_pnls: Iterable[float]) -> float:
    pnls = _finite_series(trade_pnls)
    if not pnls:
        return 0.0
    wins = sum(1 for pnl in pnls if pnl > 0)
    return wins / len(pnls)


def profit_factor(trade_pnls: Iterable[float]) -> float:
    pnls = _finite_series(trade_pnls)
    if not pnls:
        return 0.0

    gross_profit = sum(pnl for pnl in pnls if pnl > 0)
    gross_loss = abs(sum(pnl for pnl in pnls if pnl < 0))
    if gross_loss == 0:
        return 0.0
    return _safe_number(gross_profit / gross_loss)
