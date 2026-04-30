import json

import pytest
from scripts.confidence_analysis import calibration_rows, pearson, signed_next_return, spearman
from scripts.regime_analysis import summarize_by_regime
from scripts.v1_compare import append_checkpoint_decision, load_checkpointed_decisions


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
