"""
Compare multiple local LLM models on the same price series.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from experiments.runner import ExperimentConfig, run_mock_experiment
from services.ollama_client import OllamaClient


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
    max_drawdown: float
    win_rate: float
    profit_factor: float
    avg_latency_ms: float
    fills: int
    rejected: int
    risk_blocked: int


class ModelComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[ModelRunMetrics]
    ranked_models: list[str]
    csv_path: str | None = None


def compare_models(config: ModelComparisonConfig) -> ModelComparisonResult:
    rows: list[ModelRunMetrics] = []
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
            )
        )
        rows.append(
            ModelRunMetrics(
                model=model,
                rank=0,
                price_series=list(config.prices),
                cumulative_return=_finite(experiment.cumulative_return),
                sharpe=_finite(experiment.sharpe),
                max_drawdown=_finite(experiment.max_drawdown),
                win_rate=_finite(experiment.win_rate),
                profit_factor=_finite(experiment.profit_factor),
                avg_latency_ms=_finite(experiment.avg_latency_ms),
                fills=experiment.fills,
                rejected=experiment.rejected,
                risk_blocked=experiment.risk_blocked,
            )
        )

    ranked = sorted(rows, key=lambda row: (-row.sharpe, row.max_drawdown, -row.cumulative_return))
    ranked_rows = [
        row.model_copy(update={"rank": index + 1})
        for index, row in enumerate(ranked)
    ]

    csv_path = config.output_csv_path
    if csv_path:
        _write_csv(Path(csv_path), ranked_rows)

    return ModelComparisonResult(
        results=ranked_rows,
        ranked_models=[row.model for row in ranked_rows],
        csv_path=csv_path,
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
                "max_drawdown",
                "win_rate",
                "profit_factor",
                "avg_latency_ms",
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
                    "max_drawdown": row.max_drawdown,
                    "win_rate": row.win_rate,
                    "profit_factor": row.profit_factor,
                    "avg_latency_ms": row.avg_latency_ms,
                    "fills": row.fills,
                    "rejected": row.rejected,
                    "risk_blocked": row.risk_blocked,
                }
            )


def _finite(value: float) -> float:
    return value if math.isfinite(value) else 0.0
