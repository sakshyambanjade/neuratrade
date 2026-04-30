"""
Paper-trading baseline strategies run on the same price series as LLM experiments.
"""

from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from experiments.runner import ExperimentConfig, ExperimentResult, run_mock_experiment

BaselineName = Literal[
    "random",
    "buy_and_hold",
    "ema_crossover",
    "rsi_mean_reversion",
    "macd_crossover",
    "hindsight_oracle",
    "always_hold",
]


class BaselineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prices: list[float]
    baseline_names: list[BaselineName] = Field(
        default_factory=lambda: [
            "random",
            "buy_and_hold",
            "ema_crossover",
            "rsi_mean_reversion",
            "macd_crossover",
            "hindsight_oracle",
            "always_hold",
        ]
    )
    seed: int = 42
    initial_cash: float = Field(default=10_000.0, gt=0)
    initial_btc: float = Field(default=0.0, ge=0)
    fee_bps: float = Field(default=10.0, ge=0)
    spread_bps: float = Field(default=0.0, ge=0)
    minute_volume: float = Field(default=100.0, ge=0)
    volatility: float = Field(default=0.0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    periods_per_year: int = Field(default=525_600, gt=0)


class BaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: BaselineName
    result: ExperimentResult
    fee_drag_pct: float = 0.0


def run_baselines(config: BaselineConfig) -> list[BaselineResult]:
    hold_result = _run_one(config, "always_hold")
    rows = []
    for name in config.baseline_names:
        result = hold_result if name == "always_hold" else _run_one(config, name)
        rows.append(
            BaselineResult(
                name=name,
                result=result,
                fee_drag_pct=max(0.0, hold_result.cumulative_return - result.cumulative_return),
            )
        )
    return rows


def baseline_decisions(prices: list[float], name: BaselineName, *, seed: int = 42) -> list[dict[str, float | str]]:
    return _decisions(prices, name, seed=seed)


def _run_one(config: BaselineConfig, name: BaselineName) -> ExperimentResult:
    decisions = _decisions(config.prices, name, seed=config.seed)
    return run_mock_experiment(
        ExperimentConfig(
            name=f"baseline:{name}",
            prices=config.prices,
            mocked_decisions=decisions,
            initial_cash=config.initial_cash,
            initial_btc=config.initial_btc,
            fee_bps=config.fee_bps,
            spread_bps=config.spread_bps,
            minute_volume=config.minute_volume,
            volatility=config.volatility,
            latency_ms=config.latency_ms,
            periods_per_year=config.periods_per_year,
        )
    )


def _decisions(prices: list[float], name: BaselineName, *, seed: int) -> list[dict[str, float | str]]:
    if name == "always_hold":
        return [_decision("HOLD", 0.0) for _ in prices]
    if name == "buy_and_hold":
        return [_decision("BUY", 0.95), *[_decision("HOLD", 0.0) for _ in prices[1:]]]
    if name == "random":
        rng = random.Random(seed)
        return [_decision(rng.choice(["BUY", "SELL", "HOLD"]), 0.25) for _ in prices]
    if name == "ema_crossover":
        return _ema_crossover(prices)
    if name == "rsi_mean_reversion":
        return _rsi_mean_reversion(prices)
    if name == "macd_crossover":
        return _macd_crossover(prices)
    return _hindsight_oracle(prices)


def _ema_crossover(prices: list[float]) -> list[dict[str, float | str]]:
    decisions = []
    previous_fast = None
    previous_slow = None
    for index, _price in enumerate(prices):
        fast = _ema(prices[: index + 1], 9)
        slow = _ema(prices[: index + 1], 21)
        action = "HOLD"
        size = 0.0
        if previous_fast is not None and previous_slow is not None:
            if previous_fast <= previous_slow and fast > slow:
                action = "BUY"
                size = 0.25
            elif previous_fast >= previous_slow and fast < slow:
                action = "SELL"
                size = 1.0
        decisions.append(_decision(action, size))
        previous_fast = fast
        previous_slow = slow
    return decisions


def _rsi_mean_reversion(prices: list[float], period: int = 14) -> list[dict[str, float | str]]:
    decisions = []
    for index in range(len(prices)):
        rsi = _rsi(prices[: index + 1], period)
        if rsi < 30:
            decisions.append(_decision("BUY", 0.25))
        elif rsi > 70:
            decisions.append(_decision("SELL", 1.0))
        else:
            decisions.append(_decision("HOLD", 0.0))
    return decisions


def _macd_crossover(prices: list[float]) -> list[dict[str, float | str]]:
    decisions = []
    previous_macd = None
    previous_signal = None
    macd_values: list[float] = []
    for index in range(len(prices)):
        segment = prices[: index + 1]
        macd = _ema(segment, 12) - _ema(segment, 26)
        macd_values.append(macd)
        signal = _ema(macd_values, 9)
        action = "HOLD"
        size = 0.0
        if previous_macd is not None and previous_signal is not None:
            if previous_macd <= previous_signal and macd > signal:
                action = "BUY"
                size = 0.25
            elif previous_macd >= previous_signal and macd < signal:
                action = "SELL"
                size = 1.0
        decisions.append(_decision(action, size))
        previous_macd = macd
        previous_signal = signal
    return decisions


def _hindsight_oracle(prices: list[float]) -> list[dict[str, float | str]]:
    decisions = []
    for current, next_price in zip(prices, prices[1:], strict=False):
        if next_price > current:
            decisions.append(_decision("BUY", 0.95))
        elif next_price < current:
            decisions.append(_decision("SELL", 1.0))
        else:
            decisions.append(_decision("HOLD", 0.0))
    if prices:
        decisions.append(_decision("SELL", 1.0))
    return decisions


def _rsi(values: list[float], period: int) -> float:
    if len(values) <= period:
        return 50.0
    deltas = [current - previous for previous, current in zip(values, values[1:], strict=False)]
    recent = deltas[-period:]
    gains = [delta for delta in recent if delta > 0]
    losses = [-delta for delta in recent if delta < 0]
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss <= 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def _ema(values: list[float], period: int) -> float:
    k = 2 / (period + 1)
    value = values[0]
    for price in values[1:]:
        value = price * k + value * (1 - k)
    return value


def _decision(action: str, size: float) -> dict[str, float | str]:
    return {
        "action": action,
        "confidence": 1.0,
        "position_size_pct": size,
        "reasoning": f"Deterministic {action} baseline decision for paper trading.",
        "stop_loss": 0.02,
        "take_profit": 0.04,
    }
