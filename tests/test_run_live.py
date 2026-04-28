import asyncio
import math
from contextlib import nullcontext

from experiments.run_live import LiveExperimentRunner, LiveRunConfig
from services.execution import ExecutionSimulator
from services.market_ws import MarketSnapshot
from services.risk_engine import RiskDecision


class FakeMarket:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or MarketSnapshot(
            symbol="BTCUSDT",
            last_price=100.0,
            bid=99.9,
            ask=100.1,
            spread_bps=20.0,
            volume=100.0,
            heartbeat_ts=1.0,
        )
        self.shutdown_called = False

    def get_snapshot(self):
        return self.snapshot

    async def shutdown(self):
        self.shutdown_called = True


class FakeOllama:
    def __init__(self, decision):
        self.decision = decision

    def decide(self, prompt, fallback_on_error=True):
        return self.decision


class FakeRisk:
    def __init__(self, decision):
        self.decision = decision
        self.inputs = []

    def validate(self, risk_input):
        self.inputs.append(risk_input)
        return self.decision


class FakeRepo:
    def __init__(self):
        self.inferences = []
        self.fills = []
        self.metrics = []
        self.risks = []
        self.finished = []
        self.experiment_id = 1
        self.model_run_id = 2

    def create_experiment(self, db, **kwargs):
        return type("Experiment", (), {"id": self.experiment_id})()

    def create_model_run(self, db, **kwargs):
        return type("ModelRun", (), {"id": self.model_run_id})()

    def log_inference(self, db, **kwargs):
        self.inferences.append(kwargs)

    def log_execution_fill(self, db, **kwargs):
        self.fills.append(kwargs)

    def log_metric_snapshot(self, db, **kwargs):
        self.metrics.append(kwargs)

    def log_risk_event(self, db, **kwargs):
        self.risks.append(kwargs)

    def finish_model_run(self, db, **kwargs):
        self.finished.append(kwargs)


def _session_factory():
    return nullcontext(object())


def _decision(action="BUY", size=0.1, confidence=0.9):
    return {
        "action": action,
        "confidence": confidence,
        "position_size_pct": size,
        "reasoning": "test",
        "stop_loss": 0.02,
        "take_profit": 0.04,
    }


def _runner(*, ollama_decision=None, risk_decision=None, repo=None, max_cycles=None):
    return LiveExperimentRunner(
        LiveRunConfig(model_name="mock", cycle_interval_seconds=0, max_cycles=max_cycles),
        market_feed=FakeMarket(),
        ollama_client=FakeOllama(ollama_decision or _decision()),
        risk_engine=FakeRisk(
            risk_decision
            or RiskDecision(
                allowed=True,
                final_action="BUY",
                final_size_pct=0.1,
                reason="ok",
                triggered_rules=[],
            )
        ),
        execution_simulator=ExecutionSimulator(),
        session_factory=_session_factory,
        repo=repo or FakeRepo(),
    )


def test_one_cycle_completes():
    repo = FakeRepo()
    runner = _runner(repo=repo)

    asyncio.run(runner.run_cycle())

    assert runner.state.cycles_completed == 1
    assert len(repo.inferences) == 1
    assert len(repo.metrics) == 1


def test_hold_does_not_execute_trade():
    repo = FakeRepo()
    runner = _runner(
        ollama_decision=_decision(action="HOLD", size=0.0),
        risk_decision=RiskDecision(
            allowed=True, final_action="HOLD", final_size_pct=0.0, reason="hold", triggered_rules=[]
        ),
        repo=repo,
    )

    asyncio.run(runner.run_cycle())

    assert repo.fills == []
    assert len(repo.metrics) == 1


def test_risk_block_logs_risk_event():
    repo = FakeRepo()
    runner = _runner(
        risk_decision=RiskDecision(
            allowed=False,
            final_action="BUY",
            final_size_pct=0.0,
            reason="blocked",
            triggered_rules=["max_spread"],
        ),
        repo=repo,
    )

    asyncio.run(runner.run_cycle())

    assert len(repo.risks) == 1
    assert repo.risks[0]["rule_name"] == "max_spread"
    assert repo.fills == []


def test_buy_decision_executes_simulated_trade():
    repo = FakeRepo()
    runner = _runner(repo=repo)

    asyncio.run(runner.run_cycle())

    assert len(repo.fills) == 1
    assert repo.fills[0]["side"] == "BUY"
    assert runner.state.btc > 0
    assert runner.state.cash < runner.config.starting_balance


def test_metrics_are_logged():
    repo = FakeRepo()
    runner = _runner(repo=repo)

    asyncio.run(runner.run_cycle())

    metric = repo.metrics[0]
    assert "equity" in metric
    assert "cumulative_return" in metric
    assert "sharpe" in metric
    assert "max_drawdown" in metric
    assert "win_rate" in metric
    assert "profit_factor" in metric


def test_max_cycles_stops_runner():
    repo = FakeRepo()
    runner = _runner(repo=repo, max_cycles=2)

    asyncio.run(runner.start())

    assert runner.state.cycles_completed == 2
    assert runner.state.running is False
    assert len(repo.finished) >= 1


def test_no_nan_or_inf_in_metrics():
    repo = FakeRepo()
    runner = _runner(repo=repo)

    asyncio.run(runner.run_cycle())

    metric = repo.metrics[0]
    values = [
        metric["equity"],
        metric["cumulative_return"],
        metric["sharpe"],
        metric["max_drawdown"],
        metric["win_rate"],
        metric["profit_factor"],
    ]
    assert all(math.isfinite(value) for value in values)
