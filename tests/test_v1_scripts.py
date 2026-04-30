import asyncio
import json
import sqlite3
from argparse import Namespace

import pytest
import run_v1_experiment as v1_runner
from run_v1_experiment import PreflightError, candle_count, missing_ollama_models, selected_models
from scripts.confidence_analysis import (
    calibration_rows,
    correlation_summary,
    load_decision_outcomes,
    pearson,
    signed_next_return,
    spearman,
)
from scripts.regime_analysis import load_regime_outcomes, summarize_by_regime
from scripts.v1_compare import (
    append_checkpoint_decision,
    collect_model_decisions,
    load_checkpointed_decisions,
    load_price_series,
)


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_confidence_correlations_and_signed_returns():
    assert pearson([0.1, 0.2, 0.3], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert spearman([30.0, 10.0, 20.0], [3.0, 1.0, 2.0]) == pytest.approx(1.0)
    assert signed_next_return("BUY", 100.0, 110.0) == pytest.approx(0.1)
    assert signed_next_return("SELL", 100.0, 110.0) == pytest.approx(-0.1)
    assert signed_next_return("BUY", None, 110.0) is None


def test_confidence_calibration_groups_by_model_and_bucket():
    rows = [
        {"model_name": "alpha", "confidence": 0.61, "realized_pnl": 2.0, "realized_return": 0.01},
        {"model_name": "alpha", "confidence": 0.69, "realized_pnl": -1.0, "realized_return": -0.02},
        {"model_name": "beta", "confidence": 0.92, "realized_pnl": 3.0, "realized_return": 0.03},
    ]

    result = calibration_rows(rows)

    alpha = next(row for row in result if row["model"] == "alpha")
    beta = next(row for row in result if row["model"] == "beta")
    assert alpha["confidence_bucket"] == "0.6-0.7"
    assert alpha["count"] == 2
    assert alpha["mean_realized_pnl"] == pytest.approx(0.5)
    assert beta["confidence_bucket"] == "0.9-1.0"


def test_regime_summary_uses_fill_pnls_only_for_outcome_metrics():
    rows = [
        {"regime": "bull", "model_name": "alpha", "confidence": 0.7, "realized_pnl": 2.0},
        {"regime": "bull", "model_name": "alpha", "confidence": 0.9, "realized_pnl": -1.0},
        {"regime": "bear", "model_name": "alpha", "confidence": 0.4, "realized_pnl": None},
    ]

    result = summarize_by_regime(rows)

    bull = next(row for row in result if row["regime"] == "bull")
    bear = next(row for row in result if row["regime"] == "bear")
    assert bull["n"] == 2
    assert bull["fills"] == 2
    assert bull["return"] == pytest.approx(1.0)
    assert bull["win_rate"] == pytest.approx(0.5)
    assert bear["n"] == 1
    assert bear["fills"] == 0


def test_v1_compare_checkpoint_reuses_matching_prefix(tmp_path):
    checkpoint = tmp_path / "qwen_decisions.jsonl"
    append_checkpoint_decision(
        checkpoint,
        index=0,
        price=100.0,
        decision={"action": "BUY", "confidence": 0.7, "position_size_pct": 0.1},
    )
    append_checkpoint_decision(
        checkpoint,
        index=1,
        price=101.0,
        decision={"action": "HOLD", "confidence": 0.4, "position_size_pct": 0.0},
    )

    matching = load_checkpointed_decisions(checkpoint, expected_prices=[100.0, 101.0])
    mismatched = load_checkpointed_decisions(checkpoint, expected_prices=[100.0, 102.0])

    assert [row["action"] for row in matching] == ["BUY", "HOLD"]
    assert [row["action"] for row in mismatched] == ["BUY"]
    assert all(json.dumps(row) for row in matching)


def test_v1_runner_prefers_qwen_default_when_no_model_env(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    args = Namespace(all_models=False, models=None, model=None)

    assert selected_models(args) == ["qwen2.5:7b"]


def test_v1_runner_prefill_count_handles_missing_and_populated_db(tmp_path):
    missing = tmp_path / "missing.db"
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE candles (close FLOAT)")
        connection.executemany("INSERT INTO candles (close) VALUES (?)", [(100.0,), (0.0,), (101.0,)])

    assert candle_count(missing) == 0
    assert candle_count(db_path) == 2


def test_v1_runner_reports_missing_ollama_models():
    missing = missing_ollama_models({"qwen2.5:7b", "phi3:mini"}, ["qwen2.5:7b", "mistral:7b"])

    assert missing == ["mistral:7b"]


def test_v1_preflight_success_and_prefill_failure(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE candles (close FLOAT)")
        connection.executemany("INSERT INTO candles (close) VALUES (?)", [(100.0,), (101.0,)])
    args = Namespace(
        db_path=str(db_path),
        min_prefill_candles=2,
        skip_prefill_check=False,
        skip_ollama_preflight=True,
        skip_market_preflight=True,
        ollama_url="http://127.0.0.1:11434",
        ollama_timeout=1.0,
    )

    v1_runner.run_preflight(["qwen2.5:7b"], args)
    args.min_prefill_candles = 3
    with pytest.raises(PreflightError, match="Only 2 candle"):
        v1_runner.run_preflight(["qwen2.5:7b"], args)


def test_v1_preflight_ollama_and_dns_branches(monkeypatch):
    monkeypatch.setattr(
        v1_runner,
        "urlopen",
        lambda _url, timeout: _FakeResponse(b'{"models":[{"name":"qwen2.5:7b"}]}'),
    )
    monkeypatch.setattr(v1_runner.socket, "getaddrinfo", lambda host, port: [(host, port)])

    assert v1_runner.fetch_ollama_models("http://ollama.local", timeout=1.0) == {"qwen2.5:7b"}
    v1_runner.check_binance_dns(("stream.binance.com",))

    def fail_urlopen(_url, timeout):
        raise OSError("down")

    def fail_dns(_host, _port):
        raise OSError("no dns")

    monkeypatch.setattr(v1_runner, "urlopen", fail_urlopen)
    with pytest.raises(PreflightError, match="Cannot reach Ollama"):
        v1_runner.fetch_ollama_models("http://ollama.local", timeout=1.0)
    monkeypatch.setattr(v1_runner.socket, "getaddrinfo", fail_dns)
    with pytest.raises(PreflightError, match="Cannot resolve"):
        v1_runner.check_binance_dns(("stream.binance.com",))


def test_v1_main_preflight_only_uses_cli_args(tmp_path, monkeypatch):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE candles (close FLOAT)")
        connection.execute("INSERT INTO candles (close) VALUES (100.0)")
    monkeypatch.setattr(
        v1_runner.sys,
        "argv",
        [
            "run_v1_experiment.py",
            "--preflight-only",
            "--db-path",
            str(db_path),
            "--min-prefill-candles",
            "1",
            "--skip-ollama-preflight",
            "--skip-market-preflight",
        ],
    )

    v1_runner.main()


def test_v1_run_model_uses_live_runner_config(monkeypatch):
    captured = {}

    class FakeRunner:
        def __init__(self, config):
            captured["config"] = config

        async def start(self):
            return Namespace(cycles_completed=1, experiment_id=2, model_run_id=3)

    monkeypatch.setattr(v1_runner, "LiveExperimentRunner", FakeRunner)
    args = Namespace(
        experiment_prefix="smoke",
        symbol="BTCUSDT",
        description="",
        cycle_interval_seconds=0,
        max_cycles=1,
        starting_balance=10_000.0,
        starting_btc=0.0,
        fee_bps=10.0,
        temperature=0.0,
        hardware_tag="ci",
        market_warmup_seconds=0,
    )

    asyncio.run(v1_runner.run_model("qwen2.5:7b", args))

    assert captured["config"].experiment_name == "smoke-qwen2-5-7b"
    assert captured["config"].dry_run is True


def test_confidence_analysis_loads_joined_outcomes(tmp_path):
    db_path = tmp_path / "research.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE experiments (id INTEGER, name TEXT)")
        connection.execute("CREATE TABLE model_runs (id INTEGER, experiment_id INTEGER)")
        connection.execute(
            "CREATE TABLE inference_logs ("
            "id INTEGER, model_run_id INTEGER, timestamp INTEGER, model_name TEXT, "
            "parsed_action TEXT, confidence FLOAT, market_tick_id INTEGER)"
        )
        connection.execute(
            "CREATE TABLE market_ticks (id INTEGER, model_run_id INTEGER, cycle_index INTEGER, last_price FLOAT)"
        )
        connection.execute(
            "CREATE TABLE execution_fills ("
            "id INTEGER, model_run_id INTEGER, timestamp INTEGER, side TEXT, realized_pnl FLOAT, "
            "slippage_bps FLOAT, latency_ms INTEGER)"
        )
        connection.execute("INSERT INTO experiments VALUES (1, 'v1-live-qwen')")
        connection.execute("INSERT INTO model_runs VALUES (2, 1)")
        connection.executemany(
            "INSERT INTO market_ticks VALUES (?, 2, ?, ?)",
            [(10, 0, 100.0), (11, 1, 110.0)],
        )
        connection.execute("INSERT INTO inference_logs VALUES (20, 2, 1000, 'qwen2.5:7b', 'BUY', 0.8, 10)")
        connection.execute("INSERT INTO execution_fills VALUES (30, 2, 1001, 'BUY', 5.0, 1.0, 20)")

    rows = load_decision_outcomes(db_path, experiment_name="v1-live")
    summary = correlation_summary(rows)

    assert rows[0]["realized_return"] == pytest.approx(0.1)
    assert rows[0]["realized_pnl"] == pytest.approx(5.0)
    assert summary["overall"]["decisions"] == 1


def test_regime_analysis_loads_joined_outcomes(tmp_path):
    db_path = tmp_path / "research.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE experiments (id INTEGER, name TEXT)")
        connection.execute("CREATE TABLE model_runs (id INTEGER, experiment_id INTEGER)")
        connection.execute(
            "CREATE TABLE inference_logs ("
            "id INTEGER, model_run_id INTEGER, timestamp INTEGER, model_name TEXT, "
            "parsed_action TEXT, confidence FLOAT, cycle_indicator_id INTEGER)"
        )
        connection.execute("CREATE TABLE cycle_indicators (id INTEGER, regime TEXT)")
        connection.execute(
            "CREATE TABLE execution_fills ("
            "id INTEGER, model_run_id INTEGER, timestamp INTEGER, side TEXT, realized_pnl FLOAT, "
            "slippage_bps FLOAT, latency_ms INTEGER)"
        )
        connection.execute("INSERT INTO experiments VALUES (1, 'v1-live-qwen')")
        connection.execute("INSERT INTO model_runs VALUES (2, 1)")
        connection.execute("INSERT INTO cycle_indicators VALUES (12, 'bull')")
        connection.execute("INSERT INTO inference_logs VALUES (20, 2, 1000, 'qwen2.5:7b', 'SELL', 0.8, 12)")
        connection.execute("INSERT INTO execution_fills VALUES (30, 2, 1001, 'SELL', -2.0, 1.0, 20)")

    rows = load_regime_outcomes(db_path, experiment_name="v1-live")
    summary = summarize_by_regime(rows)

    assert rows[0]["regime"] == "bull"
    assert summary[0]["fills"] == 1
    assert summary[0]["return"] == pytest.approx(-2.0)


def test_v1_compare_loads_prices_and_collects_checkpointed_decisions(tmp_path, monkeypatch):
    db_path = tmp_path / "candles.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE candles (ts INTEGER, close FLOAT)")
        connection.executemany("INSERT INTO candles VALUES (?, ?)", [(1, 100.0), (2, 101.0), (3, 102.0)])

    class FakeDecision:
        def model_dump(self):
            return {"action": "HOLD", "confidence": 0.5, "position_size_pct": 0.0}

    class FakeClient:
        def __init__(self, model):
            self.model = model

        def decide(self, _prompt, fallback_on_error):
            return FakeDecision()

    monkeypatch.setattr("scripts.v1_compare.OllamaClient", FakeClient)

    prices = load_price_series(db_path, max_points=2)
    decisions = collect_model_decisions(
        model="qwen2.5:7b",
        prices=prices,
        checkpoint_dir=tmp_path / "checkpoints",
        fallback_on_error=False,
    )

    assert prices == [101.0, 102.0]
    assert len(decisions) == 2
    with pytest.raises(RuntimeError, match="Only 3 usable"):
        load_price_series(db_path, max_points=4)
