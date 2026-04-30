"""
Paper-trading baseline strategies run on the same price series as LLM experiments.
"""

from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from experiments.runner import ExperimentConfig, ExperimentResult, run_mock_experiment

BaselineName = Literal["random", "buy_and_hold", "ema_crossover", "always_hold"]


class BaselineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prices: list[float]
    baseline_names: list[BaselineName] = Field(
        default_factory=lambda: ["random", "buy_and_hold", "ema_crossover", "always_hold"]
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
    return _ema_crossover(prices)


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
