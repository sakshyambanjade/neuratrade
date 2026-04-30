"""
Compare multiple local LLM models on the same price series.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from experiments.baselines import BaselineConfig, run_baselines
from experiments.runner import ExperimentConfig, run_mock_experiment
from services.ollama_client import OllamaClient
from services.statistics import bootstrap_confidence_intervals, pairwise_return_test


class ModelComparisonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[str]
    prices: list[float]
    mocked_decisions_by_model: dict[str, list[Any]] = Field(default_factory=dict)
    output_csv_path: str | None = None
    initial_cash: float = Field(default=10_000.0, gt=0)
    initial_btc: float = Field(default=0.0, ge=0)
    fee_bps: float = Field(default=10.0, ge=0)
    spread_bps: float = Field(default=0.0, ge=0)
    minute_volume: float = Field(default=100.0, ge=0)
    volatility: float = Field(default=0.0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    periods_per_year: int = Field(default=525_600, gt=0)
    include_baselines: bool = True
    seed: int = 42
    statistics_resamples: int = Field(default=1000, ge=100)

    @field_validator("models")
    @classmethod
    def validate_models(cls, models: list[str]) -> list[str]:
        cleaned = [model.strip() for model in models if model.strip()]
        if not cleaned:
            raise ValueError("at least one model is required")
        return cleaned

    @field_validator("prices")
    @classmethod
    def validate_prices(cls, prices: list[float]) -> list[float]:
        if not prices:
            raise ValueError("prices cannot be empty")
        if any(not math.isfinite(price) or price <= 0 for price in prices):
            raise ValueError("prices must be finite and positive")
        return prices


class ModelRunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    rank: int
    price_series: list[float]
    cumulative_return: float
    sharpe: float
    sortino: float
    calmar: float
    value_at_risk_95: float
    conditional_value_at_risk_95: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    avg_latency_ms: float
    fills: int
    rejected: int
    risk_blocked: int
    fee_drag_pct: float = 0.0
    return_ci_low: float = 0.0
    return_ci_high: float = 0.0
    sharpe_ci_low: float = 0.0
    sharpe_ci_high: float = 0.0
    win_rate_ci_low: float = 0.0
    win_rate_ci_high: float = 0.0


class ModelComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[ModelRunMetrics]
    ranked_models: list[str]
    csv_path: str | None = None


def compare_models(config: ModelComparisonConfig) -> ModelComparisonResult:
    rows: list[ModelRunMetrics] = []
    experiments: dict[str, Any] = {}
    for model in config.models:
        decisions = config.mocked_decisions_by_model.get(model)
        if decisions is None:
            decisions = _decisions_from_ollama(model, config.prices)

        experiment = run_mock_experiment(
            ExperimentConfig(
                name=model,
                prices=list(config.prices),
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
        experiments[model] = experiment
        rows.append(
            _metrics_row(
                model=model,
                experiment=experiment,
                price_series=list(config.prices),
                fee_drag_pct=0.0,
                statistics_resamples=config.statistics_resamples,
                statistics_seed=config.seed,
                periods_per_year=config.periods_per_year,
            )
        )

    if config.include_baselines:
        for baseline in run_baselines(
            BaselineConfig(
                prices=list(config.prices),
                seed=config.seed,
                initial_cash=config.initial_cash,
                initial_btc=config.initial_btc,
                fee_bps=config.fee_bps,
                spread_bps=config.spread_bps,
                minute_volume=config.minute_volume,
                volatility=config.volatility,
                latency_ms=config.latency_ms,
                periods_per_year=config.periods_per_year,
            )
        ):
            name = f"baseline:{baseline.name}"
            experiments[name] = baseline.result
            rows.append(
                _metrics_row(
                    model=name,
                    experiment=baseline.result,
                    price_series=list(config.prices),
                    fee_drag_pct=baseline.fee_drag_pct,
                    statistics_resamples=config.statistics_resamples,
                    statistics_seed=config.seed,
                    periods_per_year=config.periods_per_year,
                )
            )

    ranked = sorted(rows, key=lambda row: (-row.sharpe, row.max_drawdown, -row.cumulative_return))
    ranked_rows = [row.model_copy(update={"rank": index + 1}) for index, row in enumerate(ranked)]

    csv_path = config.output_csv_path
    if csv_path:
        _write_csv(Path(csv_path), ranked_rows)
        _write_statistics(Path(csv_path).with_name("model_comparison_statistics.json"), ranked_rows, experiments)

    return ModelComparisonResult(
        results=ranked_rows,
        ranked_models=[row.model for row in ranked_rows],
        csv_path=csv_path,
    )


def _metrics_row(
    *,
    model: str,
    experiment: Any,
    price_series: list[float],
    fee_drag_pct: float,
    statistics_resamples: int,
    statistics_seed: int,
    periods_per_year: int,
) -> ModelRunMetrics:
    intervals = {
        ci.metric: ci
        for ci in bootstrap_confidence_intervals(
            experiment.equity_series,
            experiment.trade_pnls,
            resamples=statistics_resamples,
            seed=statistics_seed,
            periods_per_year=periods_per_year,
        )
    }
    return ModelRunMetrics(
        model=model,
        rank=0,
        price_series=price_series,
        cumulative_return=_finite(experiment.cumulative_return),
        sharpe=_finite(experiment.sharpe),
        sortino=_finite(experiment.sortino),
        calmar=_finite(experiment.calmar),
        value_at_risk_95=_finite(experiment.value_at_risk_95),
        conditional_value_at_risk_95=_finite(experiment.conditional_value_at_risk_95),
        max_drawdown=_finite(experiment.max_drawdown),
        win_rate=_finite(experiment.win_rate),
        profit_factor=_finite(experiment.profit_factor),
        avg_latency_ms=_finite(experiment.avg_latency_ms),
        fills=experiment.fills,
        rejected=experiment.rejected,
        risk_blocked=experiment.risk_blocked,
        fee_drag_pct=_finite(fee_drag_pct),
        return_ci_low=_finite(intervals["return"].lower),
        return_ci_high=_finite(intervals["return"].upper),
        sharpe_ci_low=_finite(intervals["sharpe"].lower),
        sharpe_ci_high=_finite(intervals["sharpe"].upper),
        win_rate_ci_low=_finite(intervals["win_rate"].lower),
        win_rate_ci_high=_finite(intervals["win_rate"].upper),
    )


def _decisions_from_ollama(model: str, prices: list[float]) -> list[dict[str, Any]]:
    client = OllamaClient(model=model)
    decisions: list[dict[str, Any]] = []
    for index, price in enumerate(prices):
        decision = client.decide(
            f"Return a JSON trading decision for tick {index} with BTCUSDT price {price}.",
            fallback_on_error=True,
        )
        decisions.append(decision.model_dump())
    return decisions


def _write_csv(path: Path, rows: list[ModelRunMetrics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rank",
                "model",
                "return",
                "sharpe",
                "sortino",
                "calmar",
                "value_at_risk_95",
                "conditional_value_at_risk_95",
                "max_drawdown",
                "win_rate",
                "profit_factor",
                "avg_latency_ms",
                "fee_drag_pct",
                "return_ci_low",
                "return_ci_high",
                "sharpe_ci_low",
                "sharpe_ci_high",
                "win_rate_ci_low",
                "win_rate_ci_high",
                "fills",
                "rejected",
                "risk_blocked",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "rank": row.rank,
                    "model": row.model,
                    "return": row.cumulative_return,
                    "sharpe": row.sharpe,
                    "sortino": row.sortino,
                    "calmar": row.calmar,
                    "value_at_risk_95": row.value_at_risk_95,
                    "conditional_value_at_risk_95": row.conditional_value_at_risk_95,
                    "max_drawdown": row.max_drawdown,
                    "win_rate": row.win_rate,
                    "profit_factor": row.profit_factor,
                    "avg_latency_ms": row.avg_latency_ms,
                    "fee_drag_pct": row.fee_drag_pct,
                    "return_ci_low": row.return_ci_low,
                    "return_ci_high": row.return_ci_high,
                    "sharpe_ci_low": row.sharpe_ci_low,
                    "sharpe_ci_high": row.sharpe_ci_high,
                    "win_rate_ci_low": row.win_rate_ci_low,
                    "win_rate_ci_high": row.win_rate_ci_high,
                    "fills": row.fills,
                    "rejected": row.rejected,
                    "risk_blocked": row.risk_blocked,
                }
            )


def _write_statistics(path: Path, rows: list[ModelRunMetrics], experiments: dict[str, Any]) -> None:
    payload: dict[str, Any] = {
        "bootstrap_intervals": {
            row.model: {
                "return": [row.return_ci_low, row.return_ci_high],
                "sharpe": [row.sharpe_ci_low, row.sharpe_ci_high],
                "win_rate": [row.win_rate_ci_low, row.win_rate_ci_high],
            }
            for row in rows
        },
        "pairwise_tests": [],
    }
    comparisons = max(1, len(rows) * (len(rows) - 1) // 2)
    for left_index, left in enumerate(rows):
        for right in rows[left_index + 1 :]:
            left_result = experiments[left.model]
            right_result = experiments[right.model]
            test = pairwise_return_test(
                left_result.equity_series,
                right_result.equity_series,
                comparisons=comparisons,
            )
            payload["pairwise_tests"].append(
                {
                    "left": left.model,
                    "right": right.model,
                    "sample": "period_returns",
                    "test_name": test.test_name,
                    "statistic": test.statistic,
                    "p_value": test.p_value,
                    "corrected_p_value": test.corrected_p_value,
                    "effect_size": test.effect_size,
                    "n": test.n,
                }
            )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _finite(value: float) -> float:
    return value if math.isfinite(value) else 0.0
