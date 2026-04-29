import json

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Trade(Base):
    __tablename__ = "trades"
    id = Column(String, primary_key=True)
    opened_at = Column(Integer, nullable=False)
    closed_at = Column(Integer, nullable=True)
    symbol = Column(String, default="BTCUSDT")
    action = Column(String, nullable=False)  # BUY or SELL
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    size_btc = Column(Float, nullable=False)
    size_usdt = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    pnl_usdt = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    close_reason = Column(String, nullable=True)
    status = Column(String, default="open")  # open | closed | opening
    confidence = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    indicator_snapshot = Column(Text, nullable=True)  # JSON string
    memories_used = Column(Text, nullable=True)  # JSON array
    brain_memory_id = Column(String, nullable=True)

    def indicator_snapshot_dict(self):
        return json.loads(self.indicator_snapshot or "{}")

    def memories_used_list(self):
        return json.loads(self.memories_used or "[]")


class Candle(Base):
    __tablename__ = "candles"
    ts = Column(Integer, primary_key=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    source = Column(String, default="binance")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    ts = Column(Integer, primary_key=True)
    cash = Column(Float)
    btc_held = Column(Float)
    total_value = Column(Float)
    daily_pnl = Column(Float)


class DecisionRecord(Base):
    __tablename__ = "decisions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=True)
    memories_used = Column(Text, nullable=True)


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    config_json = Column(Text, nullable=False)
    created_at = Column(Integer, nullable=False)

    model_runs = relationship(
        "ModelRun",
        back_populates="experiment",
        cascade="all, delete-orphan",
    )


class ModelRun(Base):
    __tablename__ = "model_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False, index=True)
    model_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    started_at = Column(Integer, nullable=False)
    ended_at = Column(Integer, nullable=True)
    seed = Column(Integer, nullable=True)
    prompt_version = Column(String, nullable=False, default="v1")
    system_prompt_hash = Column(String, nullable=False, default="")
    temperature = Column(Float, nullable=False, default=0.0)
    ollama_model_tag = Column(String, nullable=False, default="")
    hardware_tag = Column(String, nullable=False, default="")

    experiment = relationship("Experiment", back_populates="model_runs")
    inference_logs = relationship(
        "InferenceLog",
        back_populates="model_run",
        cascade="all, delete-orphan",
    )
    execution_fills = relationship(
        "ExecutionFill",
        back_populates="model_run",
        cascade="all, delete-orphan",
    )
    metric_snapshots = relationship(
        "MetricSnapshot",
        back_populates="model_run",
        cascade="all, delete-orphan",
    )
    risk_events = relationship(
        "RiskEvent",
        back_populates="model_run",
        cascade="all, delete-orphan",
    )
    market_ticks = relationship(
        "MarketTick",
        back_populates="model_run",
        cascade="all, delete-orphan",
    )
    cycle_indicators = relationship(
        "CycleIndicator",
        back_populates="model_run",
        cascade="all, delete-orphan",
    )
    experiment_artifacts = relationship(
        "ExperimentArtifact",
        back_populates="model_run",
        cascade="all, delete-orphan",
    )


class InferenceLog(Base):
    __tablename__ = "inference_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_run_id = Column(Integer, ForeignKey("model_runs.id"), nullable=False, index=True)
    timestamp = Column(Integer, nullable=False)
    model_name = Column(String, nullable=False)
    prompt_hash = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False, default="v1")
    system_prompt_hash = Column(String, nullable=False, default="")
    temperature = Column(Float, nullable=False, default=0.0)
    ollama_model_tag = Column(String, nullable=False, default="")
    hardware_tag = Column(String, nullable=False, default="")
    market_tick_id = Column(Integer, ForeignKey("market_ticks.id"), nullable=True, index=True)
    cycle_indicator_id = Column(Integer, ForeignKey("cycle_indicators.id"), nullable=True, index=True)
    data_quality = Column(String, nullable=False, default="valid")
    raw_response = Column(Text, nullable=False)
    parsed_action = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    success = Column(Boolean, nullable=False)
    error = Column(Text, nullable=False, default="")

    model_run = relationship("ModelRun", back_populates="inference_logs")


class ExecutionFill(Base):
    __tablename__ = "execution_fills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_run_id = Column(Integer, ForeignKey("model_runs.id"), nullable=False, index=True)
    timestamp = Column(Integer, nullable=False)
    side = Column(String, nullable=False)
    requested_qty = Column(Float, nullable=False)
    filled_qty = Column(Float, nullable=False)
    decision_price = Column(Float, nullable=False)
    fill_price = Column(Float, nullable=False)
    fee = Column(Float, nullable=False)
    slippage_bps = Column(Float, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    realized_pnl = Column(Float, nullable=False)

    model_run = relationship("ModelRun", back_populates="execution_fills")


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_run_id = Column(Integer, ForeignKey("model_runs.id"), nullable=False, index=True)
    timestamp = Column(Integer, nullable=False)
    equity = Column(Float, nullable=False)
    cumulative_return = Column(Float, nullable=False)
    sharpe = Column(Float, nullable=False)
    max_drawdown = Column(Float, nullable=False)
    win_rate = Column(Float, nullable=False)
    profit_factor = Column(Float, nullable=False)
    data_gap = Column(Boolean, nullable=False, default=False)

    model_run = relationship("ModelRun", back_populates="metric_snapshots")


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_run_id = Column(Integer, ForeignKey("model_runs.id"), nullable=False, index=True)
    timestamp = Column(Integer, nullable=False)
    rule_name = Column(String, nullable=False)
    blocked = Column(Boolean, nullable=False)
    reason = Column(Text, nullable=False)
    input_json = Column(Text, nullable=False)

    model_run = relationship("ModelRun", back_populates="risk_events")


class MarketTick(Base):
    __tablename__ = "market_ticks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_run_id = Column(Integer, ForeignKey("model_runs.id"), nullable=False, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=True, index=True)
    cycle_index = Column(Integer, nullable=False)
    timestamp_utc = Column(Float, nullable=False)
    received_at = Column(Float, nullable=False)
    symbol = Column(String, nullable=False)
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    last_price = Column(Float, nullable=True)
    volume_24h = Column(Float, nullable=True)
    spread_bps = Column(Float, nullable=False, default=0.0)
    source = Column(String, nullable=False, default="binance_ws")
    raw_json = Column(Text, nullable=False, default="{}")
    validation_status = Column(String, nullable=False)
    validation_reason = Column(Text, nullable=False, default="")
    data_gap = Column(Boolean, nullable=False, default=False)

    model_run = relationship("ModelRun", back_populates="market_ticks")


class CycleIndicator(Base):
    __tablename__ = "cycle_indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_run_id = Column(Integer, ForeignKey("model_runs.id"), nullable=False, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=True, index=True)
    market_tick_id = Column(Integer, ForeignKey("market_ticks.id"), nullable=True, index=True)
    cycle_index = Column(Integer, nullable=False)
    timestamp_utc = Column(Float, nullable=False)
    rsi_14 = Column(Float, nullable=True)
    ema_9 = Column(Float, nullable=True)
    ema_21 = Column(Float, nullable=True)
    vwap = Column(Float, nullable=True)
    bb_upper = Column(Float, nullable=True)
    bb_middle = Column(Float, nullable=True)
    bb_lower = Column(Float, nullable=True)
    adx_14 = Column(Float, nullable=True)
    regime = Column(String, nullable=False, default="unknown")
    source_json = Column(Text, nullable=False, default="{}")

    model_run = relationship("ModelRun", back_populates="cycle_indicators")


class ExperimentArtifact(Base):
    __tablename__ = "experiment_artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=True, index=True)
    model_run_id = Column(Integer, ForeignKey("model_runs.id"), nullable=True, index=True)
    created_at = Column(Integer, nullable=False)
    artifact_type = Column(String, nullable=False)
    path = Column(Text, nullable=False)
    sha256 = Column(String, nullable=False, default="")
    metadata_json = Column(Text, nullable=False, default="{}")

    model_run = relationship("ModelRun", back_populates="experiment_artifacts")
