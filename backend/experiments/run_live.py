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
from services.llm_quality import ActionDistributionMonitor, HallucinationEvent, validate_decision_payload
from services.market_ws import BinanceMarketWebSocket, MarketSnapshot, TickValidator
from services.metrics import cumulative_return, max_drawdown, profit_factor, sharpe_ratio, win_rate
from services.ollama_client import OllamaClient, OllamaDecision, fallback_decision
from services.prompting import PROMPT_TEMPLATE, PROMPT_VERSION, render_prompt, template_hash
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
    seed: int | None = None
    prompt_version: str = PROMPT_VERSION
    system_prompt_hash: str = ""
    temperature: float = Field(default=0.0, ge=0.0)
    ollama_model_tag: str = ""
    hardware_tag: str = ""
    fee_bps: float = Field(default=10.0, ge=0)
    minute_volume_default: float = Field(default=100.0, ge=0)
    volatility_default: float = Field(default=0.0, ge=0)
    slippage_model: str = "sqrt_impact"
    average_daily_volume_usd: float = Field(default=1_000_000_000.0, ge=0)
    tick_staleness_max_sec: float = Field(default=5.0, gt=0)
    max_spread_pct: float = Field(default=0.005, gt=0)
    data_gap_multiplier: float = Field(default=2.0, gt=0)
    market_warmup_seconds: float = Field(default=15.0, ge=0)
    resume_model_run_id: int | None = Field(default=None, ge=1)

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
    data_gap_cycles: int = 0
    prompt_template_id: int | None = None


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
        tick_validator: TickValidator | None = None,
    ) -> None:
        self.config = config
        self.market_feed = market_feed or BinanceMarketWebSocket(symbol=config.symbol.lower())
        self.ollama_client = ollama_client or OllamaClient(model=config.model_name)
        self.risk_engine = risk_engine or RiskEngine()
        self.execution_simulator = execution_simulator or ExecutionSimulator()
        self.session_factory = session_factory
        self.repo = repo
        self.tick_validator = tick_validator or TickValidator(
            max_spread_pct=config.max_spread_pct,
            max_staleness_sec=config.tick_staleness_max_sec,
            data_gap_sec=max(config.tick_staleness_max_sec, config.cycle_interval_seconds * config.data_gap_multiplier),
        )
        self.action_monitor = ActionDistributionMonitor()
        self.state = LiveRunState(cash=config.starting_balance, btc=config.starting_btc)
        self._stop_event = asyncio.Event()
        self._market_task: asyncio.Task | None = None

    async def start(self) -> LiveRunState:
        init_db()
        self._install_signal_handlers()
        self._ensure_research_run()
        self.state.running = True
        if self.config.max_cycles is not None and self.state.cycles_completed >= self.config.max_cycles:
            await self.stop()
            return self.state
        if hasattr(self.market_feed, "run"):
            self._market_task = asyncio.create_task(self.market_feed.run())
            await self._wait_for_market_warmup()

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

    async def _wait_for_market_warmup(self) -> None:
        deadline = time.monotonic() + self.config.market_warmup_seconds
        while time.monotonic() < deadline:
            snapshot = self.market_feed.get_snapshot()
            if snapshot.heartbeat_ts is not None and _snapshot_price(snapshot) is not None:
                return
            await asyncio.sleep(0.25)

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
        validation = self.tick_validator.validate(snapshot)
        market_tick_id = self._log_market_tick(snapshot, validation)
        price = _snapshot_price(snapshot)
        if validation.data_gap:
            self.state.data_gap_cycles += 1
        if not validation.valid or price is None:
            self.state.cycles_completed += 1
            return self.state

        indicator_values = _cycle_indicator_values(snapshot)
        cycle_indicator_id = self._log_cycle_indicators(
            snapshot, market_tick_id=market_tick_id, indicators=indicator_values
        )
        prompt = self._build_prompt(snapshot, indicator_values)
        started = time.perf_counter()
        try:
            decision = self.ollama_client.decide(prompt, fallback_on_error=False)
            success = True
            error = ""
        except Exception as exc:
            decision = fallback_decision(str(exc))
            success = False
            error = str(exc)
        inference_latency_ms = int((time.perf_counter() - started) * 1000)
        decision_data = _decision_dict(decision)
        hallucinations = validate_decision_payload(decision_data, current_price=price)
        self.action_monitor.observe(str(decision_data["action"]))
        inference_log_id = self._log_inference(
            prompt,
            decision_data,
            inference_latency_ms,
            success,
            error,
            market_tick_id=market_tick_id,
            cycle_indicator_id=cycle_indicator_id,
            data_quality=validation.status,
        )
        self._log_hallucinations(
            hallucinations, inference_log_id=inference_log_id, raw_output=json.dumps(decision_data)
        )
        if hallucinations:
            decision_data = _decision_dict(fallback_decision("Hallucination detected; holding"))

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
                slippage_model=self.config.slippage_model,
                average_daily_volume_usd=self.config.average_daily_volume_usd,
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
        if self.config.resume_model_run_id is not None:
            self._resume_research_run()
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
                seed=self.config.seed,
                prompt_version=self.config.prompt_version,
                system_prompt_hash=self.config.system_prompt_hash,
                temperature=self.config.temperature,
                ollama_model_tag=self.config.ollama_model_tag or self.config.model_name,
                hardware_tag=self.config.hardware_tag,
            )
            prompt_template = self.repo.upsert_prompt_template(
                db,
                version=self.config.prompt_version,
                template_text=PROMPT_TEMPLATE,
                template_hash=template_hash(PROMPT_TEMPLATE),
                metadata={"execution_mode": "paper_trading"},
            )
            self.state.experiment_id = experiment.id
            self.state.model_run_id = model_run.id
            self.state.prompt_template_id = prompt_template.id

        self._with_db(create)

    def _resume_research_run(self) -> None:
        resume_model_run_id = self.config.resume_model_run_id
        if resume_model_run_id is None:
            return

        data = self._with_db(lambda db: self.repo.load_live_run_resume_state(db, model_run_id=resume_model_run_id))
        model_name = str(data["model_name"])
        if model_name != self.config.model_name:
            raise ValueError(
                f"Cannot resume model_run_id={resume_model_run_id}: DB model is {model_name!r}, "
                f"but config model is {self.config.model_name!r}."
            )

        def mark_running(db: Any) -> Any:
            self.repo.mark_model_run_running(db, model_run_id=resume_model_run_id)
            prompt_template = self.repo.upsert_prompt_template(
                db,
                version=self.config.prompt_version,
                template_text=PROMPT_TEMPLATE,
                template_hash=template_hash(PROMPT_TEMPLATE),
                metadata={"execution_mode": "paper_trading", "resumed_model_run_id": resume_model_run_id},
            )
            return prompt_template.id

        prompt_template_id = self._with_db(mark_running)

        stored_config = data.get("config", {})
        starting_cash = _finite(stored_config.get("starting_balance", self.config.starting_balance))
        starting_btc = _finite(stored_config.get("starting_btc", self.config.starting_btc))
        portfolio = _portfolio_from_fills(
            fills=data["fills"],
            starting_cash=starting_cash,
            starting_btc=starting_btc,
        )
        trade_pnls = [
            _finite(fill["realized_pnl"])
            for fill in data["fills"]
            if str(fill["side"]).upper() == "SELL" and _finite(fill["filled_qty"]) > 0
        ]
        self.state.experiment_id = int(data["experiment_id"])
        self.state.model_run_id = resume_model_run_id
        self.state.prompt_template_id = prompt_template_id
        self.state.cash = _finite(portfolio["cash"])
        self.state.btc = _finite(portfolio["btc"])
        self.state.avg_entry_price = portfolio["avg_entry_price"]
        self.state.cycles_completed = int(data["next_cycle_index"])
        self.state.equity_series = [_finite(value) for value in data["equity_series"]]
        self.state.trade_pnls = trade_pnls
        self.state.consecutive_losses = _consecutive_losses(trade_pnls)
        self.state.data_gap_cycles = int(data["data_gap_cycles"])

    def _log_inference(
        self,
        prompt: str,
        decision_data: dict[str, Any],
        latency_ms: int,
        success: bool,
        error: str,
        *,
        market_tick_id: int | None = None,
        cycle_indicator_id: int | None = None,
        data_quality: str = "valid",
    ) -> int | None:
        model_run_id = self._model_run_id()
        row = self._with_db(
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
                prompt_version=self.config.prompt_version,
                system_prompt_hash=self.config.system_prompt_hash,
                temperature=self.config.temperature,
                ollama_model_tag=self.config.ollama_model_tag or self.config.model_name,
                hardware_tag=self.config.hardware_tag,
                market_tick_id=market_tick_id,
                cycle_indicator_id=cycle_indicator_id,
                prompt_template_id=self.state.prompt_template_id,
                rendered_prompt=prompt,
                data_quality=data_quality,
            )
        )
        return getattr(row, "id", None)

    def _log_market_tick(self, snapshot: MarketSnapshot, validation: Any) -> int | None:
        model_run_id = self._model_run_id()

        def log_tick(db: Any) -> Any:
            return self.repo.log_market_tick(
                db,
                model_run_id=model_run_id,
                experiment_id=self.state.experiment_id,
                cycle_index=self.state.cycles_completed,
                timestamp_utc=float(snapshot.heartbeat_ts or time.time()),
                received_at=time.time(),
                symbol=snapshot.symbol,
                bid=snapshot.bid,
                ask=snapshot.ask,
                last_price=snapshot.last_price,
                volume_24h=snapshot.volume,
                spread_bps=snapshot.spread_bps,
                source="binance_ws",
                raw_json=snapshot.model_dump(mode="json"),
                validation_status=validation.status,
                validation_reason=validation.reason,
                data_gap=validation.data_gap,
            )

        row = self._with_db(log_tick)
        return getattr(row, "id", None)

    def _log_cycle_indicators(
        self, snapshot: MarketSnapshot, *, market_tick_id: int | None, indicators: dict[str, Any]
    ) -> int | None:
        model_run_id = self._model_run_id()

        def log_indicators(db: Any) -> Any:
            return self.repo.log_cycle_indicators(
                db,
                model_run_id=model_run_id,
                experiment_id=self.state.experiment_id,
                market_tick_id=market_tick_id,
                cycle_index=self.state.cycles_completed,
                timestamp_utc=float(snapshot.heartbeat_ts or time.time()),
                **indicators,
            )

        row = self._with_db(log_indicators)
        return getattr(row, "id", None)

    def _log_hallucinations(
        self, events: list[HallucinationEvent], *, inference_log_id: int | None, raw_output: str
    ) -> None:
        if not events:
            return
        model_run_id = self._model_run_id()
        for event in events:

            def log_event(db: Any, hallucination: HallucinationEvent = event) -> Any:
                return self.repo.log_llm_hallucination(
                    db,
                    experiment_id=self.state.experiment_id,
                    model_run_id=model_run_id,
                    inference_log_id=inference_log_id,
                    cycle_index=self.state.cycles_completed,
                    timestamp_utc=time.time(),
                    model_name=self.config.model_name,
                    raw_output=raw_output,
                    hallucination_type=hallucination.hallucination_type,
                    field_name=hallucination.field_name,
                    field_value=hallucination.field_value,
                    corrective_action=hallucination.corrective_action,
                )

            self._with_db(log_event)

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

    def _log_metrics(self, *, price: float, data_gap: bool = False) -> None:
        model_run_id = self._model_run_id()
        if data_gap:
            return
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
                data_gap=data_gap,
                **metric_values,
            )
        )

    def _build_prompt(self, snapshot: MarketSnapshot, indicators: dict[str, Any]) -> str:
        return render_prompt(
            market={
                "symbol": snapshot.symbol,
                "last_price": snapshot.last_price,
                "bid": snapshot.bid,
                "ask": snapshot.ask,
                "spread_bps": snapshot.spread_bps,
                "volume": snapshot.volume,
                "top_bids": [level.model_dump() for level in snapshot.bids[:5]],
                "top_asks": [level.model_dump() for level in snapshot.asks[:5]],
                "closed_candles": [candle.model_dump() for candle in snapshot.candles[-15:]],
            },
            indicators=indicators,
            portfolio={
                "cash": self.state.cash,
                "btc": self.state.btc,
                "avg_entry_price": self.state.avg_entry_price,
                "equity": self._equity(_snapshot_price(snapshot) or 0.0),
            },
            risk={
                "dry_run": self.config.dry_run,
                "execution_mode": "paper_trading",
                "consecutive_losses": self.state.consecutive_losses,
                "data_gap_cycles": self.state.data_gap_cycles,
            },
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


def _cycle_indicator_values(snapshot: MarketSnapshot) -> dict[str, Any]:
    candles = [candle for candle in snapshot.candles if candle.closed]
    closes = [_finite(candle.close) for candle in candles if _finite(candle.close) > 0]
    highs = [_finite(candle.high) for candle in candles if _finite(candle.high) > 0]
    lows = [_finite(candle.low) for candle in candles if _finite(candle.low) > 0]
    volumes = [_finite(candle.volume) for candle in candles]
    price = _snapshot_price(snapshot)

    if not closes and price is not None:
        closes = [price]
        highs = [price]
        lows = [price]
        volumes = [max(_finite(snapshot.volume), 0.0)]

    ema_9 = _ema(closes, 9)
    ema_21 = _ema(closes, 21)
    bb_upper, bb_middle, bb_lower = _bollinger(closes)
    rsi_14 = _rsi(closes)
    vwap = _vwap(candles)
    adx_14 = _adx(highs, lows, closes)
    regime = _regime(closes, ema_21, adx_14, volumes)
    return {
        "rsi_14": rsi_14,
        "ema_9": ema_9,
        "ema_21": ema_21,
        "vwap": vwap,
        "bb_upper": bb_upper,
        "bb_middle": bb_middle,
        "bb_lower": bb_lower,
        "adx_14": adx_14,
        "regime": regime,
        "source_data": {
            "closed_candles": len(candles),
            "bid_depth_levels": len(snapshot.bids),
            "ask_depth_levels": len(snapshot.asks),
        },
    }


def _ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    window = values[-max(period * 3, period) :]
    k = 2 / (period + 1)
    result = window[0]
    for value in window[1:]:
        result = value * k + result * (1 - k)
    return _finite(result)


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for previous, current in zip(values[-(period + 1) :], values[-period:], strict=False):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return _finite(100 - (100 / (1 + rs)))


def _bollinger(
    values: list[float], period: int = 20, mult: float = 2.0
) -> tuple[float | None, float | None, float | None]:
    if len(values) < period:
        return None, None, None
    window = values[-period:]
    middle = sum(window) / period
    variance = sum((value - middle) ** 2 for value in window) / period
    std = math.sqrt(variance)
    return _finite(middle + mult * std), _finite(middle), _finite(middle - mult * std)


def _vwap(candles: list[Any], period: int = 20) -> float | None:
    window = candles[-period:]
    weighted_total = 0.0
    volume_total = 0.0
    for candle in window:
        typical = (_finite(candle.high) + _finite(candle.low) + _finite(candle.close)) / 3
        volume = max(_finite(candle.volume), 0.0)
        weighted_total += typical * volume
        volume_total += volume
    if volume_total <= 0:
        return None
    return _finite(weighted_total / volume_total)


def _adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None
    true_ranges = []
    for index in range(1, len(closes)):
        true_ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )
    avg_true_range = sum(true_ranges[-period:]) / period
    if avg_true_range <= 0:
        return 0.0
    directional_move = abs(closes[-1] - closes[-period])
    return _finite(min(100.0, directional_move / avg_true_range * 100 / period))


def _regime(closes: list[float], ema_21: float | None, adx_14: float | None, volumes: list[float]) -> str:
    if len(volumes) >= 20 and volumes[-1] < sorted(volumes[-20:])[3]:
        return "low_liquidity"
    if len(closes) >= 31:
        returns = [abs(current / previous - 1) for previous, current in zip(closes[-31:-1], closes[-30:], strict=False)]
        recent_vol = sum(returns[-5:]) / 5 if len(returns) >= 5 else 0.0
        avg_vol = sum(returns) / len(returns) if returns else 0.0
        if avg_vol > 0 and recent_vol > avg_vol * 2:
            return "high_volatility"
    if adx_14 is not None and adx_14 < 25:
        return "ranging"
    if ema_21 is not None and closes:
        if closes[-1] > ema_21:
            return "bull"
        if closes[-1] < ema_21:
            return "bear"
    return "unknown"


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


def _portfolio_from_fills(
    *,
    fills: list[dict[str, Any]],
    starting_cash: float,
    starting_btc: float,
) -> dict[str, float | None]:
    cash = _finite(starting_cash)
    btc = _finite(starting_btc)
    avg_entry_price: float | None = None
    for fill in fills:
        side = str(fill.get("side", "")).upper()
        quantity = _finite(fill.get("filled_qty"))
        if quantity <= 0:
            continue
        fill_price = _finite(fill.get("fill_price"))
        fee = _finite(fill.get("fee"))
        if side == "BUY":
            previous_btc = btc
            cash -= quantity * fill_price + fee
            btc += quantity
            avg_entry_price = _weighted_entry_price(
                current_avg=avg_entry_price,
                current_btc=previous_btc,
                fill_price=fill_price,
                fill_quantity=quantity,
            )
        elif side == "SELL":
            cash += quantity * fill_price - fee
            btc -= quantity
            if btc <= 1e-12:
                btc = 0.0
                avg_entry_price = None
    return {
        "cash": _finite(cash),
        "btc": _finite(btc),
        "avg_entry_price": avg_entry_price,
    }


def _consecutive_losses(trade_pnls: list[float]) -> int:
    losses = 0
    for pnl in reversed(trade_pnls):
        if pnl < 0:
            losses += 1
            continue
        break
    return losses


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0
