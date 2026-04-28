"""
Ablation experiment runner for controlled benchmark variants.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.execution import ExecutionSimulator, OrderRequest
from services.metrics import cumulative_return, max_drawdown, profit_factor, sharpe_ratio, win_rate
from services.risk_engine import RiskEngine, RiskInput

VariantName = Literal["full_system", "no_risk_engine", "no_memory", "no_news", "no_slippage", "no_latency"]


class AblationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prices: list[float]
    decisions: list[Any]
    starting_balance: float = Field(default=10_000.0, gt=0)
    starting_btc: float = Field(default=0.0, ge=0)
    fee_bps: float = Field(default=10.0, ge=0)
    spread_bps: float = Field(default=10.0, ge=0)
    minute_volume: float = Field(default=100.0, ge=0)
    volatility: float = Field(default=0.01, ge=0)
    latency_ms: int = Field(default=25, ge=0)
    output_dir: str | None = None
    variants: list[VariantName] = Field(
        default_factory=lambda: [
            "full_system",
            "no_risk_engine",
            "no_memory",
            "no_news",
            "no_slippage",
            "no_latency",
        ]
    )

    @field_validator("prices")
    @classmethod
    def validate_prices(cls, prices: list[float]) -> list[float]:
        if not prices:
            raise ValueError("prices cannot be empty")
        if any(not math.isfinite(price) or price <= 0 for price in prices):
            raise ValueError("prices must be finite and positive")
        return prices


class AblationVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: VariantName
    use_risk_engine: bool = True
    use_memory: bool = True
    use_news: bool = True
    use_slippage: bool = True
    use_latency: bool = True


class AblationRunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant: VariantName
    price_series: list[float]
    cumulative_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    avg_slippage_bps: float
    avg_latency_ms: float
    trade_count: int
    risk_blocked: int


class AblationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants: list[AblationRunMetrics]
    best_sharpe: str | None
    lowest_drawdown: str | None
    highest_return: str | None
    csv_path: str | None = None
    summary_json_path: str | None = None


def run_ablation(config: AblationConfig) -> AblationResult:
    rows = [_run_variant(config, _variant_from_name(name)) for name in config.variants]
    best_sharpe = max(rows, key=lambda row: row.sharpe).variant if rows else None
    lowest_drawdown = min(rows, key=lambda row: row.max_drawdown).variant if rows else None
    highest_return = max(rows, key=lambda row: row.cumulative_return).variant if rows else None

    csv_path = None
    summary_path = None
    if config.output_dir:
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = str(output_dir / "ablation_results.csv")
        summary_path = str(output_dir / "ablation_summary.json")
        _write_csv(Path(csv_path), rows)
        _write_summary(
            Path(summary_path),
            best_sharpe=best_sharpe,
            lowest_drawdown=lowest_drawdown,
            highest_return=highest_return,
        )

    return AblationResult(
        variants=rows,
        best_sharpe=best_sharpe,
        lowest_drawdown=lowest_drawdown,
        highest_return=highest_return,
        csv_path=csv_path,
        summary_json_path=summary_path,
    )


def _run_variant(config: AblationConfig, variant: AblationVariant) -> AblationRunMetrics:
    simulator = ExecutionSimulator()
    risk_engine = RiskEngine()
    cash = config.starting_balance
    btc = config.starting_btc
    avg_entry_price: float | None = None
    equity_series: list[float] = []
    trade_pnls: list[float] = []
    slippages: list[float] = []
    latencies: list[int] = []
    trade_count = 0
    risk_blocked = 0
    consecutive_losses = 0

    for index, price in enumerate(config.prices):
        decision = _normalize_decision(config.decisions[index] if index < len(config.decisions) else "HOLD")
        action = decision["action"]
        size_pct = decision["position_size_pct"]
        if action in {"BUY", "SELL"} and variant.use_risk_engine:
            risk_decision = risk_engine.validate(
                RiskInput(
                    action=action,
                    confidence=decision["confidence"],
                    position_size_pct=size_pct,
                    equity=_finite(cash + btc * price),
                    entry_price=price,
                    stop_loss=_stop_price(action, price, decision["stop_loss"]),
                    total_drawdown_pct=max_drawdown(equity_series or [cash + btc * price]),
                    spread_bps=config.spread_bps,
                    volatility=config.volatility,
                    consecutive_losses=consecutive_losses,
                )
            )
            if not risk_decision.allowed:
                risk_blocked += 1
                equity_series.append(_finite(cash + btc * price))
                continue
            action = risk_decision.final_action
            size_pct = risk_decision.final_size_pct

        if action == "BUY":
            quantity = (cash * size_pct) / price if price > 0 else 0.0
        elif action == "SELL":
            quantity = btc * size_pct
        else:
            equity_series.append(_finite(cash + btc * price))
            continue

        report = simulator.execute_market_order(
            OrderRequest(
                side=action,
                quantity=quantity,
                price=price,
                cash_balance=cash,
                btc_balance=btc,
                avg_entry_price=avg_entry_price,
                spread_bps=config.spread_bps if variant.use_slippage else 0.0,
                minute_volume=config.minute_volume,
                volatility=config.volatility if variant.use_slippage else 0.0,
                fee_bps=config.fee_bps,
                latency_ms=config.latency_ms if variant.use_latency else 0,
            )
        )
        if report.status == "FILLED":
            previous_btc = btc
            cash = report.cash_after
            btc = report.btc_after
            slippages.append(report.slippage_bps)
            latencies.append(report.latency_ms)
            trade_count += 1
            if action == "BUY" and report.average_fill_price is not None:
                avg_entry_price = _weighted_entry_price(
                    current_avg=avg_entry_price,
                    current_btc=previous_btc,
                    fill_price=report.average_fill_price,
                    fill_quantity=report.filled_quantity,
                )
            if action == "SELL":
                trade_pnls.append(report.realized_pnl)
                consecutive_losses = consecutive_losses + 1 if report.realized_pnl < 0 else 0
                if btc <= 1e-12:
                    btc = 0.0
                    avg_entry_price = None
        elif action in {"BUY", "SELL"}:
            slippages.append(report.slippage_bps)
            latencies.append(report.latency_ms)

        equity_series.append(_finite(cash + btc * price))

    return AblationRunMetrics(
        variant=variant.name,
        price_series=list(config.prices),
        cumulative_return=_finite(cumulative_return(equity_series)),
        sharpe=_finite(sharpe_ratio(equity_series)),
        max_drawdown=_finite(max_drawdown(equity_series)),
        win_rate=_finite(win_rate(trade_pnls)),
        profit_factor=_finite(profit_factor(trade_pnls)),
        avg_slippage_bps=_finite(sum(slippages) / len(slippages)) if slippages else 0.0,
        avg_latency_ms=_finite(sum(latencies) / len(latencies)) if latencies else 0.0,
        trade_count=trade_count,
        risk_blocked=risk_blocked,
    )


def _variant_from_name(name: VariantName) -> AblationVariant:
    return AblationVariant(
        name=name,
        use_risk_engine=name != "no_risk_engine",
        use_memory=name != "no_memory",
        use_news=name != "no_news",
        use_slippage=name != "no_slippage",
        use_latency=name != "no_latency",
    )


def _normalize_decision(decision: Any) -> dict[str, Any]:
    if isinstance(decision, str):
        action = decision.upper()
        return {
            "action": action if action in {"BUY", "SELL", "HOLD"} else "HOLD",
            "confidence": 1.0,
            "position_size_pct": 1.0 if action != "HOLD" else 0.0,
            "stop_loss": 0.02,
        }
    data = (
        dict(decision)
        if isinstance(decision, dict)
        else {
            "action": getattr(decision, "action", "HOLD"),
            "confidence": getattr(decision, "confidence", 1.0),
            "position_size_pct": getattr(decision, "position_size_pct", 0.0),
            "stop_loss": getattr(decision, "stop_loss", 0.02),
        }
    )
    action = str(data.get("action", "HOLD")).upper()
    if action not in {"BUY", "SELL", "HOLD"}:
        action = "HOLD"
    return {
        "action": action,
        "confidence": min(max(_finite(data.get("confidence", 1.0)), 0.0), 1.0),
        "position_size_pct": min(
            max(_finite(data.get("position_size_pct", 1.0 if action != "HOLD" else 0.0)), 0.0), 1.0
        ),
        "stop_loss": _finite(data.get("stop_loss", 0.02)),
    }


def _stop_price(action: str, price: float, stop_loss: float) -> float | None:
    if action == "HOLD" or stop_loss <= 0:
        return None
    if stop_loss < 1:
        return price * (1 - stop_loss) if action == "BUY" else price * (1 + stop_loss)
    return stop_loss


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


def _write_csv(path: Path, rows: list[AblationRunMetrics]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "variant",
                "cumulative_return",
                "sharpe",
                "max_drawdown",
                "win_rate",
                "profit_factor",
                "avg_slippage_bps",
                "avg_latency_ms",
                "trade_count",
                "risk_blocked",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: getattr(row, field) for field in writer.fieldnames})


def _write_summary(
    path: Path,
    *,
    best_sharpe: str | None,
    lowest_drawdown: str | None,
    highest_return: str | None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "best_sharpe": best_sharpe,
                "lowest_drawdown": lowest_drawdown,
                "highest_return": highest_return,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0
