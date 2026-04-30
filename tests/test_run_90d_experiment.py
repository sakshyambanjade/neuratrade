import json

from scripts.run_90d_experiment import (
    MODELS,
    _confidence_rows,
    _regime_segments,
    append_checkpoint_decision,
    decision_checkpoint_path,
    load_checkpointed_decisions,
)


def _decision(action="HOLD"):
    return {
        "action": action,
        "confidence": 0.5,
        "position_size_pct": 0.0,
        "reasoning": "checkpoint test",
        "stop_loss": 0.0,
        "take_profit": 0.0,
    }


def test_checkpoint_loader_returns_contiguous_prefix(tmp_path):
    path = tmp_path / "decisions.jsonl"
    append_checkpoint_decision(path, index=0, price=100.0, decision=_decision())
    append_checkpoint_decision(path, index=2, price=102.0, decision=_decision("BUY"))

    decisions = load_checkpointed_decisions(path, expected_prices=[100.0, 101.0, 102.0])

    assert len(decisions) == 1
    assert decisions[0]["action"] == "HOLD"


def test_checkpoint_loader_ignores_stale_price_window(tmp_path):
    path = tmp_path / "decisions.jsonl"
    append_checkpoint_decision(path, index=0, price=99.0, decision=_decision("BUY"))

    assert load_checkpointed_decisions(path, expected_prices=[100.0]) == []


def test_decision_checkpoint_path_uses_model_safe_name():
    path = decision_checkpoint_path("qwen2.5:7b")

    assert path.name == "qwen2_5_7b_decisions.jsonl"


def test_checkpoint_file_is_jsonl(tmp_path):
    path = tmp_path / "decisions.jsonl"
    append_checkpoint_decision(path, index=0, price=100.0, decision=_decision())

    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["index"] == 0
    assert row["decision"]["action"] == "HOLD"


def test_default_model_lineup_covers_parameter_range():
    assert len(MODELS) == 7
    assert "tinyllama:1.1b" in MODELS
    assert "llama3.1:8b" in MODELS


def test_confidence_rows_use_action_signed_next_return():
    rows = _confidence_rows("alpha", [100.0, 110.0, 99.0], [_decision("BUY"), _decision("SELL")])

    assert rows[0]["realized_return"] > 0
    assert rows[1]["realized_return"] > 0


def test_regime_segments_cover_full_window():
    segments = _regime_segments([100, 110, 120, 119, 118, 117, 117, 117, 118])

    assert segments[0][1] == 0
    assert segments[-1][2] == 9
    assert {segment[0] for segment in segments} == {"bull", "bear", "sideways"}
