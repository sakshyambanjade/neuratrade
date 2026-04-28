"""
Live dry-run experiment runner.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import signal
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from db import research_repo
from db.database import SessionLocal, init_db
from services.execution import ExecutionSimulator, OrderRequest
from services.market_ws import BinanceMarketWebSocket, MarketSnapshot
from services.metrics import cumulative_return, max_drawdown, profit_factor, sharpe_ratio, win_rate
from services.ollama_client import OllamaClient, OllamaDecision, fallback_decision
from services.risk_engine import RiskEngine, RiskInput


class LiveRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model_name: str
    symbol: str = "BTCUSDT"
    starting_balance: float = Field(default=10_000.0, gt=0)
    starting_btc: float = Field(default=0.0, ge=0)
    cycle_interval_seconds: float = Field(default=60.0, ge=0)
    max_cycles: int | None = Field(default=None, ge=1)
    dry_run: bool = True
    experiment_name: str = "live-dry-run"
    description: str = ""
    fee_bps: float = Field(default=10.0, ge=0)
    minute_volume_default: float = Field(default=100.0, ge=0)
    volatility_default: float = Field(default=0.0, ge=0)

    @field_validator("dry_run")
    @classmethod
    def require_dry_run(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("live experiments only support dry_run=True")
        return value


class LiveRunState(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    cash: float
    btc: float = 0.0
    avg_entry_price: float | None = None
    cycles_completed: int = 0
    running: bool = False
    experiment_id: int | None = None
    model_run_id: int | None = None
    equity_series: list[float] = Field(default_factory=list)
    trade_pnls: list[float] = Field(default_factory=list)
    consecutive_losses: int = 0


class LiveExperimentRunner:
    def __init__(
        self,
        config: LiveRunConfig,
        *,
        market_feed: Any | None = None,
        ollama_client: Any | None = None,
        risk_engine: Any | None = None,
        execution_simulator: Any | None = None,
        session_factory: Callable[[], Any] = SessionLocal,
        repo: Any = research_repo,
    ) -> None:
        self.config = config
        self.market_feed = market_feed or BinanceMarketWebSocket(symbol=config.symbol.lower())
        self.ollama_client = ollama_client or OllamaClient(model=config.model_name)
        self.risk_engine = risk_engine or RiskEngine()
        self.execution_simulator = execution_simulator or ExecutionSimulator()
        self.session_factory = session_factory
        self.repo = repo
        self.state = LiveRunState(cash=config.starting_balance, btc=config.starting_btc)
        self._stop_event = asyncio.Event()
        self._market_task: asyncio.Task | None = None

    async def start(self) -> LiveRunState:
        init_db()
        self._install_signal_handlers()
        self._ensure_research_run()
        self.state.running = True
        if hasattr(self.market_feed, "run"):
            self._market_task = asyncio.create_task(self.market_feed.run())

        try:
            while not self._stop_event.is_set():
                await self.run_cycle()
                if self.config.max_cycles is not None and self.state.cycles_completed >= self.config.max_cycles:
                    break
                await asyncio.sleep(self.config.cycle_interval_seconds)
        except KeyboardInterrupt:
            await self.stop()
        finally:
            await self.stop()
        return self.state

    async def stop(self) -> None:
        self._stop_event.set()
        self.state.running = False
        if hasattr(self.market_feed, "shutdown"):
            await self.market_feed.shutdown()
        if self._market_task is not None:
            self._market_task.cancel()
            try:
                await self._market_task
            except asyncio.CancelledError:
                pass
            self._market_task = None
        if self.state.model_run_id is not None:
            self._with_db(lambda db: self.repo.finish_model_run(db, model_run_id=self.state.model_run_id))

    async def run_cycle(self) -> LiveRunState:
        self._ensure_research_run()
        snapshot = self.market_feed.get_snapshot()
        price = _snapshot_price(snapshot)
        if price is None:
            self._log_metrics(price=0.0)
            self.state.cycles_completed += 1
            return self.state

        prompt = self._build_prompt(snapshot)
        started = time.perf_counter()
        try:
            decision = self.ollama_client.decide(prompt, fallback_on_error=True)
            success = True
            error = ""
        except Exception as exc:
            decision = fallback_decision(str(exc))
            success = False
            error = str(exc)
        inference_latency_ms = int((time.perf_counter() - started) * 1000)
        decision_data = _decision_dict(decision)
        self._log_inference(prompt, decision_data, inference_latency_ms, success, error)

        equity = self._equity(price)
        risk_decision = self.risk_engine.validate(
            RiskInput(
                action=str(decision_data["action"]),
                confidence=float(decision_data["confidence"]),
                position_size_pct=float(decision_data["position_size_pct"]),
                equity=equity,
                entry_price=price,
                stop_loss=_stop_price(str(decision_data["action"]), price, float(decision_data["stop_loss"])),
                daily_drawdown_pct=max_drawdown(self.state.equity_series[-1:]),
                total_drawdown_pct=max_drawdown(self.state.equity_series or [equity]),
                spread_bps=snapshot.spread_bps,
                volatility=self.config.volatility_default,
                consecutive_losses=self.state.consecutive_losses,
            )
        )

        if not risk_decision.allowed:
            self._log_risk_event(risk_decision, decision_data)
        elif risk_decision.final_action != "HOLD":
            self._execute_trade(risk_decision.final_action, risk_decision.final_size_pct, price, snapshot)

        self._log_metrics(price=price)
        self.state.cycles_completed += 1
        return self.state

    def _execute_trade(self, side: str, size_pct: float, price: float, snapshot: MarketSnapshot) -> None:
        if side == "BUY":
            quantity = (self.state.cash * size_pct) / price if price > 0 else 0.0
        else:
            quantity = self.state.btc * size_pct
        report = self.execution_simulator.execute_market_order(
            OrderRequest(
                side=side,
                quantity=quantity,
                price=price,
                cash_balance=self.state.cash,
                btc_balance=self.state.btc,
                avg_entry_price=self.state.avg_entry_price,
                spread_bps=snapshot.spread_bps,
                minute_volume=max(snapshot.volume, self.config.minute_volume_default),
                volatility=self.config.volatility_default,
                fee_bps=self.config.fee_bps,
            )
        )
        self._log_execution(report, decision_price=price)
        if report.status != "FILLED":
            return

        previous_btc = self.state.btc
        self.state.cash = _finite(report.cash_after)
        self.state.btc = _finite(report.btc_after)
        if side == "BUY" and report.average_fill_price is not None:
            self.state.avg_entry_price = _weighted_entry_price(
                current_avg=self.state.avg_entry_price,
                current_btc=previous_btc,
                fill_price=report.average_fill_price,
                fill_quantity=report.filled_quantity,
            )
        if side == "SELL":
            pnl = _finite(report.realized_pnl)
            self.state.trade_pnls.append(pnl)
            self.state.consecutive_losses = self.state.consecutive_losses + 1 if pnl < 0 else 0
            if self.state.btc <= 1e-12:
                self.state.btc = 0.0
                self.state.avg_entry_price = None

    def _ensure_research_run(self) -> None:
        if self.state.model_run_id is not None:
            return

        def create(db: Any) -> None:
            experiment = self.repo.create_experiment(
                db,
                name=self.config.experiment_name,
                description=self.config.description,
                config=self.config.model_dump(),
            )
            model_run = self.repo.create_model_run(
                db,
                experiment_id=experiment.id,
                model_name=self.config.model_name,
            )
            self.state.experiment_id = experiment.id
            self.state.model_run_id = model_run.id

        self._with_db(create)

    def _log_inference(
        self,
        prompt: str,
        decision_data: dict[str, Any],
        latency_ms: int,
        success: bool,
        error: str,
    ) -> None:
        model_run_id = self._model_run_id()
        self._with_db(
            lambda db: self.repo.log_inference(
                db,
                model_run_id=model_run_id,
                model_name=self.config.model_name,
                prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                raw_response=json.dumps(decision_data, sort_keys=True),
                parsed_action=str(decision_data["action"]),
                confidence=float(decision_data["confidence"]),
                latency_ms=latency_ms,
                success=success,
                error=error,
            )
        )

    def _log_execution(self, report: Any, *, decision_price: float) -> None:
        model_run_id = self._model_run_id()
        self._with_db(
            lambda db: self.repo.log_execution_fill(
                db,
                model_run_id=model_run_id,
                side=report.side,
                requested_qty=_finite(report.requested_quantity),
                filled_qty=_finite(report.filled_quantity),
                decision_price=_finite(decision_price),
                fill_price=_finite(report.average_fill_price or 0.0),
                fee=_finite(report.fee),
                slippage_bps=_finite(report.slippage_bps),
                latency_ms=int(report.latency_ms),
                realized_pnl=_finite(report.realized_pnl),
            )
        )

    def _log_risk_event(self, risk_decision: Any, decision_data: dict[str, Any]) -> None:
        model_run_id = self._model_run_id()
        rules = risk_decision.triggered_rules or ["risk_block"]
        for rule_name in rules:

            def log_event(db: Any, rule_name: str = rule_name) -> Any:
                return self.repo.log_risk_event(
                    db,
                    model_run_id=model_run_id,
                    rule_name=rule_name,
                    blocked=True,
                    reason=risk_decision.reason,
                    input_data=decision_data,
                )

            self._with_db(log_event)

    def _log_metrics(self, *, price: float) -> None:
        model_run_id = self._model_run_id()
        equity = self._equity(price) if price > 0 else self.state.cash
        self.state.equity_series.append(_finite(equity))
        metric_values = {
            "equity": _finite(equity),
            "cumulative_return": _finite(cumulative_return(self.state.equity_series)),
            "sharpe": _finite(sharpe_ratio(self.state.equity_series)),
            "max_drawdown": _finite(max_drawdown(self.state.equity_series)),
            "win_rate": _finite(win_rate(self.state.trade_pnls)),
            "profit_factor": _finite(profit_factor(self.state.trade_pnls)),
        }
        self._with_db(
            lambda db: self.repo.log_metric_snapshot(
                db,
                model_run_id=model_run_id,
                **metric_values,
            )
        )

    def _build_prompt(self, snapshot: MarketSnapshot) -> str:
        return (
            f"Model {self.config.model_name} decide {self.config.symbol}. "
            f"price={snapshot.last_price} bid={snapshot.bid} ask={snapshot.ask} "
            f"spread_bps={snapshot.spread_bps:.4f} volume={snapshot.volume:.8f} "
            f"cash={self.state.cash:.8f} btc={self.state.btc:.8f}."
        )

    def _equity(self, price: float) -> float:
        return _finite(self.state.cash + self.state.btc * price)

    def _with_db(self, callback: Callable[[Any], Any]) -> Any:
        with self.session_factory() as db:
            return callback(db)

    def _model_run_id(self) -> int:
        if self.state.model_run_id is None:
            raise RuntimeError("model run has not been initialized")
        return self.state.model_run_id

    def _install_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, self._stop_event.set)
            loop.add_signal_handler(signal.SIGTERM, self._stop_event.set)
        except (NotImplementedError, RuntimeError, ValueError):
            return


def _snapshot_price(snapshot: MarketSnapshot) -> float | None:
    price = snapshot.last_price
    if price is None and snapshot.bid is not None and snapshot.ask is not None:
        price = (snapshot.bid + snapshot.ask) / 2
    if price is None or not math.isfinite(price) or price <= 0:
        return None
    return price


def _decision_dict(decision: Any) -> dict[str, Any]:
    if isinstance(decision, OllamaDecision):
        data = decision.model_dump()
    elif isinstance(decision, dict):
        data = dict(decision)
    else:
        data = {
            "action": getattr(decision, "action", "HOLD"),
            "confidence": getattr(decision, "confidence", 0.0),
            "position_size_pct": getattr(decision, "position_size_pct", 0.0),
            "reasoning": getattr(decision, "reasoning", ""),
            "stop_loss": getattr(decision, "stop_loss", 0.0),
            "take_profit": getattr(decision, "take_profit", 0.0),
        }
    return {
        "action": str(data.get("action", "HOLD")).upper(),
        "confidence": _finite(data.get("confidence", 0.0)),
        "position_size_pct": _finite(data.get("position_size_pct", 0.0)),
        "reasoning": str(data.get("reasoning", "")),
        "stop_loss": _finite(data.get("stop_loss", 0.0)),
        "take_profit": _finite(data.get("take_profit", 0.0)),
    }


def _stop_price(action: str, price: float, stop_loss: float) -> float | None:
    if action == "HOLD":
        return None
    if stop_loss <= 0:
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


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0
