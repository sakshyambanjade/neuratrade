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
) -> models.ModelRun:
    model_run = models.ModelRun(
        experiment_id=experiment_id,
        model_name=model_name,
        status=status,
        started_at=_now(),
        ended_at=None,
        seed=seed,
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
) -> models.InferenceLog:
    row = models.InferenceLog(
        model_run_id=model_run_id,
        timestamp=_now(),
        model_name=model_name,
        prompt_hash=prompt_hash,
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
