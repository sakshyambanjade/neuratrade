"""
Repository helpers for research-grade experiment logs.
"""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from db import models


def _now() -> int:
    return int(time.time())


def _json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def create_experiment(
    db: Session,
    *,
    name: str,
    description: str = "",
    config: dict[str, Any] | None = None,
) -> models.Experiment:
    experiment = models.Experiment(
        name=name,
        description=description,
        config_json=_json(config or {}),
        created_at=_now(),
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return experiment


def create_model_run(
    db: Session,
    *,
    experiment_id: int,
    model_name: str,
    status: str = "running",
    seed: int | None = None,
    prompt_version: str = "v1",
    system_prompt_hash: str = "",
    temperature: float = 0.0,
    ollama_model_tag: str = "",
    hardware_tag: str = "",
) -> models.ModelRun:
    model_run = models.ModelRun(
        experiment_id=experiment_id,
        model_name=model_name,
        status=status,
        started_at=_now(),
        ended_at=None,
        seed=seed,
        prompt_version=prompt_version,
        system_prompt_hash=system_prompt_hash,
        temperature=temperature,
        ollama_model_tag=ollama_model_tag or model_name,
        hardware_tag=hardware_tag,
    )
    db.add(model_run)
    db.commit()
    db.refresh(model_run)
    return model_run


def log_inference(
    db: Session,
    *,
    model_run_id: int,
    model_name: str,
    prompt_hash: str,
    raw_response: str,
    parsed_action: str,
    confidence: float,
    latency_ms: int,
    success: bool,
    error: str = "",
    prompt_version: str = "v1",
    system_prompt_hash: str = "",
    temperature: float = 0.0,
    ollama_model_tag: str = "",
    hardware_tag: str = "",
    market_tick_id: int | None = None,
    cycle_indicator_id: int | None = None,
    data_quality: str = "valid",
) -> models.InferenceLog:
    row = models.InferenceLog(
        model_run_id=model_run_id,
        timestamp=_now(),
        model_name=model_name,
        prompt_hash=prompt_hash,
        prompt_version=prompt_version,
        system_prompt_hash=system_prompt_hash,
        temperature=temperature,
        ollama_model_tag=ollama_model_tag or model_name,
        hardware_tag=hardware_tag,
        market_tick_id=market_tick_id,
        cycle_indicator_id=cycle_indicator_id,
        data_quality=data_quality,
        raw_response=raw_response,
        parsed_action=parsed_action,
        confidence=confidence,
        latency_ms=latency_ms,
        success=success,
        error=error,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def log_execution_fill(
    db: Session,
    *,
    model_run_id: int,
    side: str,
    requested_qty: float,
    filled_qty: float,
    decision_price: float,
    fill_price: float,
    fee: float,
    slippage_bps: float,
    latency_ms: int,
    realized_pnl: float,
) -> models.ExecutionFill:
    row = models.ExecutionFill(
        model_run_id=model_run_id,
        timestamp=_now(),
        side=side,
        requested_qty=requested_qty,
        filled_qty=filled_qty,
        decision_price=decision_price,
        fill_price=fill_price,
        fee=fee,
        slippage_bps=slippage_bps,
        latency_ms=latency_ms,
        realized_pnl=realized_pnl,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def log_metric_snapshot(
    db: Session,
    *,
    model_run_id: int,
    equity: float,
    cumulative_return: float,
    sharpe: float,
    max_drawdown: float,
    win_rate: float,
    profit_factor: float,
    data_gap: bool = False,
) -> models.MetricSnapshot:
    row = models.MetricSnapshot(
        model_run_id=model_run_id,
        timestamp=_now(),
        equity=equity,
        cumulative_return=cumulative_return,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        profit_factor=profit_factor,
        data_gap=data_gap,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def log_risk_event(
    db: Session,
    *,
    model_run_id: int,
    rule_name: str,
    blocked: bool,
    reason: str,
    input_data: dict[str, Any] | None = None,
) -> models.RiskEvent:
    row = models.RiskEvent(
        model_run_id=model_run_id,
        timestamp=_now(),
        rule_name=rule_name,
        blocked=blocked,
        reason=reason,
        input_json=_json(input_data or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def log_market_tick(
    db: Session,
    *,
    model_run_id: int,
    experiment_id: int | None,
    cycle_index: int,
    timestamp_utc: float,
    received_at: float,
    symbol: str,
    bid: float | None,
    ask: float | None,
    last_price: float | None,
    volume_24h: float | None,
    spread_bps: float,
    source: str,
    raw_json: str | dict[str, Any],
    validation_status: str,
    validation_reason: str = "",
    data_gap: bool = False,
) -> models.MarketTick:
    row = models.MarketTick(
        model_run_id=model_run_id,
        experiment_id=experiment_id,
        cycle_index=cycle_index,
        timestamp_utc=timestamp_utc,
        received_at=received_at,
        symbol=symbol,
        bid=bid,
        ask=ask,
        last_price=last_price,
        volume_24h=volume_24h,
        spread_bps=spread_bps,
        source=source,
        raw_json=raw_json if isinstance(raw_json, str) else _json(raw_json),
        validation_status=validation_status,
        validation_reason=validation_reason,
        data_gap=data_gap,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def log_cycle_indicators(
    db: Session,
    *,
    model_run_id: int,
    experiment_id: int | None,
    market_tick_id: int | None,
    cycle_index: int,
    timestamp_utc: float,
    rsi_14: float | None = None,
    ema_9: float | None = None,
    ema_21: float | None = None,
    vwap: float | None = None,
    bb_upper: float | None = None,
    bb_middle: float | None = None,
    bb_lower: float | None = None,
    adx_14: float | None = None,
    regime: str = "unknown",
    source_data: dict[str, Any] | None = None,
) -> models.CycleIndicator:
    row = models.CycleIndicator(
        model_run_id=model_run_id,
        experiment_id=experiment_id,
        market_tick_id=market_tick_id,
        cycle_index=cycle_index,
        timestamp_utc=timestamp_utc,
        rsi_14=rsi_14,
        ema_9=ema_9,
        ema_21=ema_21,
        vwap=vwap,
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
        adx_14=adx_14,
        regime=regime,
        source_json=_json(source_data or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def log_experiment_artifact(
    db: Session,
    *,
    experiment_id: int | None,
    model_run_id: int | None,
    artifact_type: str,
    path: str,
    sha256: str = "",
    metadata: dict[str, Any] | None = None,
) -> models.ExperimentArtifact:
    row = models.ExperimentArtifact(
        experiment_id=experiment_id,
        model_run_id=model_run_id,
        created_at=_now(),
        artifact_type=artifact_type,
        path=path,
        sha256=sha256,
        metadata_json=_json(metadata or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def finish_model_run(
    db: Session,
    *,
    model_run_id: int,
    status: str = "completed",
) -> models.ModelRun:
    model_run = db.get(models.ModelRun, model_run_id)
    if model_run is None:
        raise ValueError(f"model run {model_run_id} not found")
    model_run.status = status
    model_run.ended_at = _now()
    db.commit()
    db.refresh(model_run)
    return model_run
