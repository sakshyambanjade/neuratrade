from db import models, research_repo
from db.database import SessionLocal, init_db


def setup_function(_):
    init_db()
    with SessionLocal() as db:
        db.query(models.ExperimentArtifact).delete()
        db.query(models.CycleIndicator).delete()
        db.query(models.MarketTick).delete()
        db.query(models.RiskEvent).delete()
        db.query(models.MetricSnapshot).delete()
        db.query(models.ExecutionFill).delete()
        db.query(models.InferenceLog).delete()
        db.query(models.ModelRun).delete()
        db.query(models.Experiment).delete()
        db.commit()


def test_research_logging_end_to_end_relationship_counts():
    with SessionLocal() as db:
        experiment = research_repo.create_experiment(
            db,
            name="comparison",
            description="unit test",
            config={"models": ["alpha"]},
        )
        model_run = research_repo.create_model_run(
            db,
            experiment_id=experiment.id,
            model_name="alpha",
            seed=7,
            prompt_version="ntb-v1",
            system_prompt_hash="system123",
            temperature=0.0,
            ollama_model_tag="alpha:latest",
            hardware_tag="ci",
        )

        inference = research_repo.log_inference(
            db,
            model_run_id=model_run.id,
            model_name="alpha",
            prompt_hash="abc123",
            raw_response='{"action":"BUY"}',
            parsed_action="BUY",
            confidence=0.9,
            latency_ms=12,
            success=True,
            prompt_version="ntb-v1",
            system_prompt_hash="system123",
            temperature=0.0,
            ollama_model_tag="alpha:latest",
            hardware_tag="ci",
            market_tick_id=None,
            cycle_indicator_id=None,
            data_quality="valid",
        )
        fill = research_repo.log_execution_fill(
            db,
            model_run_id=model_run.id,
            side="BUY",
            requested_qty=0.1,
            filled_qty=0.1,
            decision_price=100.0,
            fill_price=100.1,
            fee=0.01,
            slippage_bps=10.0,
            latency_ms=3,
            realized_pnl=0.0,
        )
        metric = research_repo.log_metric_snapshot(
            db,
            model_run_id=model_run.id,
            equity=10_100.0,
            cumulative_return=0.01,
            sharpe=1.2,
            max_drawdown=0.0,
            win_rate=1.0,
            profit_factor=2.0,
        )
        risk = research_repo.log_risk_event(
            db,
            model_run_id=model_run.id,
            rule_name="confidence_threshold",
            blocked=False,
            reason="passed",
            input_data={"confidence": 0.9},
        )
        finished = research_repo.finish_model_run(db, model_run_id=model_run.id)

        db.expire_all()
        stored_experiment = db.get(models.Experiment, experiment.id)
        stored_run = db.get(models.ModelRun, model_run.id)

        assert stored_experiment is not None
        assert stored_run is not None
        assert len(stored_experiment.model_runs) == 1
        assert len(stored_run.inference_logs) == 1
        assert len(stored_run.execution_fills) == 1
        assert len(stored_run.metric_snapshots) == 1
        assert len(stored_run.risk_events) == 1
        assert finished.status == "completed"
        assert finished.ended_at is not None

        assert inference.id is not None
        assert inference.prompt_version == "ntb-v1"
        assert inference.system_prompt_hash == "system123"
        assert inference.ollama_model_tag == "alpha:latest"
        assert inference.hardware_tag == "ci"
        assert fill.id is not None
        assert metric.id is not None
        assert risk.id is not None


def test_research_logging_persists_market_context_and_artifacts():
    with SessionLocal() as db:
        experiment = research_repo.create_experiment(db, name="phase1", config={"execution_mode": "paper_trading"})
        model_run = research_repo.create_model_run(db, experiment_id=experiment.id, model_name="alpha")
        tick = research_repo.log_market_tick(
            db,
            model_run_id=model_run.id,
            experiment_id=experiment.id,
            cycle_index=0,
            timestamp_utc=123.0,
            received_at=124.0,
            symbol="BTCUSDT",
            bid=99.0,
            ask=101.0,
            last_price=100.0,
            volume_24h=10.0,
            spread_bps=200.0,
            source="binance_ws",
            raw_json={"price": 100.0},
            validation_status="valid",
            validation_reason="",
            data_gap=False,
        )
        indicators = research_repo.log_cycle_indicators(
            db,
            model_run_id=model_run.id,
            experiment_id=experiment.id,
            market_tick_id=tick.id,
            cycle_index=0,
            timestamp_utc=123.0,
            rsi_14=50.0,
            ema_9=100.0,
            ema_21=99.0,
            vwap=100.2,
            bb_upper=105.0,
            bb_middle=100.0,
            bb_lower=95.0,
            adx_14=20.0,
            regime="ranging",
            source_data={"closed_candles": 20},
        )
        inference = research_repo.log_inference(
            db,
            model_run_id=model_run.id,
            model_name="alpha",
            prompt_hash="hash",
            raw_response='{"action":"HOLD"}',
            parsed_action="HOLD",
            confidence=0.5,
            latency_ms=10,
            success=True,
            market_tick_id=tick.id,
            cycle_indicator_id=indicators.id,
            data_quality="valid",
        )
        artifact = research_repo.log_experiment_artifact(
            db,
            experiment_id=experiment.id,
            model_run_id=model_run.id,
            artifact_type="data_manifest",
            path="data/manifest.sha256",
            sha256="abc",
            metadata={"execution_mode": "paper_trading"},
        )

        assert tick.id is not None
        assert indicators.market_tick_id == tick.id
        assert inference.market_tick_id == tick.id
        assert inference.cycle_indicator_id == indicators.id
        assert artifact.artifact_type == "data_manifest"


def test_required_research_fields_are_populated():
    with SessionLocal() as db:
        experiment = research_repo.create_experiment(db, name="required", config={})
        model_run = research_repo.create_model_run(db, experiment_id=experiment.id, model_name="alpha")

        assert experiment.id is not None
        assert experiment.name
        assert experiment.description is not None
        assert experiment.config_json
        assert experiment.created_at is not None

        assert model_run.id is not None
        assert model_run.experiment_id == experiment.id
        assert model_run.model_name
        assert model_run.status
        assert model_run.started_at is not None
        assert model_run.prompt_version == "v1"
        assert model_run.system_prompt_hash == ""
        assert model_run.temperature == 0.0
        assert model_run.ollama_model_tag == "alpha"
        assert model_run.hardware_tag == ""
