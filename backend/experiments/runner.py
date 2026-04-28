"""
Minimal experiment runner for synthetic benchmark passes.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.execution import ExecutionSimulator, OrderRequest
from services.metrics import (
    cumulative_return,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    win_rate,
)
from services.risk_service import RiskContext, validate

Action = Literal["BUY", "SELL", "HOLD"]


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "mock-experiment"
    prices: list[float]
    mocked_decisions: list[Any]
    initial_cash: float = Field(default=10_000.0, gt=0)
    initial_btc: float = Field(default=0.0, ge=0)
    default_position_size_pct: float = Field(default=0.10, ge=0, le=1)
    fee_bps: float = Field(default=10.0, ge=0)
    spread_bps: float = Field(default=0.0, ge=0)
    minute_volume: float = Field(default=100.0, ge=0)
    volatility: float = Field(default=0.0, ge=0)
    latency_ms: int = Field(default=0, ge=0)

    @field_validator("prices")
    @classmethod
    def validate_prices(cls, prices: list[float]) -> list[float]:
        if not prices:
            raise ValueError("prices cannot be empty")
        if any(not math.isfinite(price) or price <= 0 for price in prices):
            raise ValueError("prices must be finite and positive")
        return prices


class ExperimentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ticks: int
    equity_series: list[float]
    trade_pnls: list[float]
    fills: int
    rejected: int
    risk_blocked: int
    avg_latency_ms: float
    cumulative_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    profit_factor: float


def run_mock_experiment(config: ExperimentConfig) -> ExperimentResult:
    simulator = ExecutionSimulator()
    cash = config.initial_cash
    btc = config.initial_btc
    avg_entry_price: float | None = None
    equity_series: list[float] = []
    trade_pnls: list[float] = []
    latencies: list[int] = []
    fills = 0
    rejected = 0
    risk_blocked = 0

    for index, price in enumerate(config.prices):
        decision = _normalize_decision(
            config.mocked_decisions[index] if index < len(config.mocked_decisions) else "HOLD"
        )
        action = decision["action"]
        confidence = decision["confidence"]
        position_size_pct = decision["position_size_pct"]

        if action == "BUY":
            equity = cash + btc * price
            ok, _ = validate(
                RiskContext(
                    equity=equity,
                    open_trades=1 if btc > 0 else 0,
                    daily_trade_count=fills,
                    drawdown_pct=-max_drawdown(equity_series or [equity]),
                    confidence=confidence,
                )
            )
            if not ok:
                risk_blocked += 1
            else:
                spendable_cash = cash * position_size_pct
                quantity = spendable_cash / price if price > 0 else 0.0
                report = simulator.execute_market_order(
                    _order_request(config, "BUY", quantity, price, cash, btc, avg_entry_price)
                )
                if report.status == "FILLED":
                    latencies.append(report.latency_ms)
                    previous_btc = btc
                    cash = report.cash_after
                    btc = report.btc_after
                    avg_entry_price = _weighted_entry_price(
                        current_avg=avg_entry_price,
                        current_btc=previous_btc,
                        fill_price=float(report.average_fill_price),
                        fill_quantity=report.filled_quantity,
                    )
                    fills += 1
                else:
                    latencies.append(report.latency_ms)
                    rejected += 1
        elif action == "SELL" and btc > 0:
            quantity = btc * position_size_pct if position_size_pct > 0 else btc
            quantity = min(quantity, btc)
            report = simulator.execute_market_order(
                _order_request(config, "SELL", quantity, price, cash, btc, avg_entry_price)
            )
            if report.status == "FILLED":
                latencies.append(report.latency_ms)
                cash = report.cash_after
                btc = report.btc_after
                trade_pnls.append(report.realized_pnl)
                if btc <= 1e-12:
                    btc = 0.0
                    avg_entry_price = None
                fills += 1
            else:
                latencies.append(report.latency_ms)
                rejected += 1

        equity_series.append(_finite(cash + btc * price))

    return ExperimentResult(
        name=config.name,
        ticks=len(config.prices),
        equity_series=[_finite(value) for value in equity_series],
        trade_pnls=[_finite(value) for value in trade_pnls],
        fills=fills,
        rejected=rejected,
        risk_blocked=risk_blocked,
        avg_latency_ms=_finite(sum(latencies) / len(latencies)) if latencies else 0.0,
        cumulative_return=_finite(cumulative_return(equity_series)),
        sharpe=_finite(sharpe_ratio(equity_series)),
        max_drawdown=_finite(max_drawdown(equity_series)),
        win_rate=_finite(win_rate(trade_pnls)),
        profit_factor=_finite(profit_factor(trade_pnls)),
    )


def _normalize_decision(decision: Any) -> dict[str, Any]:
    if isinstance(decision, str):
        action = decision.upper()
        confidence = 1.0
        position_size_pct = 1.0
    elif isinstance(decision, dict):
        action = str(decision.get("action", "HOLD")).upper()
        confidence = float(decision.get("confidence", 1.0))
        position_size_pct = float(decision.get("position_size_pct", 0.0 if action == "HOLD" else 1.0))
    else:
        action = str(getattr(decision, "action", "HOLD")).upper()
        confidence = float(getattr(decision, "confidence", 1.0))
        position_size_pct = float(getattr(decision, "position_size_pct", 0.0 if action == "HOLD" else 1.0))

    if action not in {"BUY", "SELL", "HOLD"}:
        action = "HOLD"
    if not math.isfinite(confidence):
        confidence = 0.0
    if not math.isfinite(position_size_pct):
        position_size_pct = 0.0

    return {
        "action": action,
        "confidence": min(max(confidence, 0.0), 1.0),
        "position_size_pct": min(max(position_size_pct, 0.0), 1.0),
    }


def _order_request(
    config: ExperimentConfig,
    side: Action,
    quantity: float,
    price: float,
    cash: float,
    btc: float,
    avg_entry_price: float | None,
) -> OrderRequest:
    return OrderRequest(
        side=side,
        quantity=quantity,
        price=price,
        cash_balance=cash,
        btc_balance=btc,
        avg_entry_price=avg_entry_price,
        spread_bps=config.spread_bps,
        minute_volume=config.minute_volume,
        volatility=config.volatility,
        fee_bps=config.fee_bps,
        latency_ms=config.latency_ms,
    )


def _weighted_entry_price(
    *,
    current_avg: float | None,
    current_btc: float,
    fill_price: float,
    fill_quantity: float,
) -> float:
    if current_avg is None or current_btc <= 0:
        return fill_price
    total_btc = current_btc + fill_quantity
    if total_btc <= 0:
        return fill_price
    return (current_avg * current_btc + fill_price * fill_quantity) / total_btc


def _finite(value: float) -> float:
    return value if math.isfinite(value) else 0.0
