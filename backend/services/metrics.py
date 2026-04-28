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


def sortino_ratio(equity_series: Iterable[float], periods_per_year: int = 525_600) -> float:
    returns = simple_returns(equity_series)
    downside_returns = [value for value in returns if value < 0]
    if len(returns) < 2 or not downside_returns or periods_per_year <= 0:
        return 0.0

    downside_deviation = math.sqrt(mean([value * value for value in downside_returns]))
    if downside_deviation <= 0:
        return 0.0
    return _safe_number(mean(returns) / downside_deviation * math.sqrt(periods_per_year))


def calmar_ratio(equity_series: Iterable[float], periods_per_year: int = 525_600) -> float:
    returns = simple_returns(equity_series)
    if not returns or periods_per_year <= 0:
        return 0.0

    drawdown = max_drawdown(equity_series)
    if drawdown <= 0:
        return 0.0
    annualized_return = mean(returns) * periods_per_year
    return _safe_number(annualized_return / drawdown)


def value_at_risk_95(equity_series: Iterable[float]) -> float:
    returns = sorted(simple_returns(equity_series))
    if not returns:
        return 0.0

    index = max(0, math.ceil(len(returns) * 0.05) - 1)
    return _safe_number(abs(min(returns[index], 0.0)))


def conditional_value_at_risk_95(equity_series: Iterable[float]) -> float:
    returns = sorted(simple_returns(equity_series))
    if not returns:
        return 0.0

    index = max(0, math.ceil(len(returns) * 0.05) - 1)
    tail = returns[: index + 1]
    if not tail:
        return 0.0
    return _safe_number(abs(min(mean(tail), 0.0)))


def average_latency(latencies_ms: Iterable[float]) -> float:
    values = _finite_series(latencies_ms)
    if not values:
        return 0.0
    return _safe_number(mean(values))


def average_slippage(slippages_bps: Iterable[float]) -> float:
    values = _finite_series(slippages_bps)
    if not values:
        return 0.0
    return _safe_number(mean(values))


def confidence_return_correlation(
    confidences: Iterable[float],
    returns: Iterable[float],
) -> float:
    confidence_values = _finite_series(confidences)
    return_values = _finite_series(returns)
    size = min(len(confidence_values), len(return_values))
    if size < 2:
        return 0.0

    confidence_values = confidence_values[:size]
    return_values = return_values[:size]
    confidence_mean = mean(confidence_values)
    return_mean = mean(return_values)
    numerator = sum(
        (x - confidence_mean) * (y - return_mean) for x, y in zip(confidence_values, return_values, strict=False)
    )
    confidence_variance = sum((x - confidence_mean) ** 2 for x in confidence_values)
    return_variance = sum((y - return_mean) ** 2 for y in return_values)
    denominator = math.sqrt(confidence_variance * return_variance)
    if denominator <= 0:
        return 0.0
    return _safe_number(numerator / denominator)


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
