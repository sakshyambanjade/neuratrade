import math

from services.risk_engine import RiskConfig, RiskEngine, RiskInput


def _input(**overrides):
    data = {
        "action": "BUY",
        "confidence": 0.9,
        "position_size_pct": 0.1,
        "equity": 10_000,
        "entry_price": 100,
        "stop_loss": 95,
        "daily_drawdown_pct": 0.0,
        "total_drawdown_pct": 0.0,
        "spread_bps": 5,
        "volatility": 0.01,
        "consecutive_losses": 0,
    }
    data.update(overrides)
    return RiskInput(**data)


def test_low_confidence_blocked():
    decision = RiskEngine().validate(_input(confidence=0.59))

    assert decision.allowed is False
    assert "min_confidence" in decision.triggered_rules


def test_oversized_position_capped():
    decision = RiskEngine(RiskConfig(max_position_pct=0.25)).validate(_input(position_size_pct=0.9, stop_loss=99))

    assert decision.allowed is True
    assert decision.final_size_pct == 0.25
    assert "max_position_pct" in decision.triggered_rules


def test_high_spread_blocked():
    decision = RiskEngine(RiskConfig(max_spread_bps=20)).validate(_input(spread_bps=21))

    assert decision.allowed is False
    assert "max_spread" in decision.triggered_rules


def test_daily_drawdown_blocked():
    decision = RiskEngine().validate(_input(daily_drawdown_pct=0.03))

    assert decision.allowed is False
    assert "daily_drawdown" in decision.triggered_rules


def test_total_drawdown_blocked():
    decision = RiskEngine().validate(_input(total_drawdown_pct=0.10))

    assert decision.allowed is False
    assert "total_drawdown" in decision.triggered_rules


def test_cooldown_after_losses_blocks():
    decision = RiskEngine().validate(_input(consecutive_losses=3))

    assert decision.allowed is False
    assert "loss_cooldown" in decision.triggered_rules


def test_kill_switch_blocks():
    decision = RiskEngine(RiskConfig(kill_switch_active=True)).validate(_input(action="HOLD"))

    assert decision.allowed is False
    assert decision.final_action == "HOLD"
    assert "kill_switch" in decision.triggered_rules


def test_hold_is_allowed_with_zero_size():
    decision = RiskEngine().validate(_input(action="HOLD", confidence=0.0, position_size_pct=1.0, stop_loss=None))

    assert decision.allowed is True
    assert decision.final_action == "HOLD"
    assert decision.final_size_pct == 0.0


def test_high_volatility_reduces_size():
    decision = RiskEngine(RiskConfig(high_volatility_threshold=0.05)).validate(
        _input(position_size_pct=0.2, volatility=0.05, stop_loss=99)
    )

    assert decision.allowed is True
    assert decision.final_size_pct == 0.1
    assert "high_volatility" in decision.triggered_rules


def test_no_nan_or_inf_allowed():
    decision = RiskEngine().validate(_input(confidence=float("nan")))

    assert decision.allowed is False
    assert "invalid_numeric_input" in decision.triggered_rules
    assert math.isfinite(decision.final_size_pct)


def test_invalid_action_blocked():
    decision = RiskEngine().validate(_input(action="MOON"))

    assert decision.allowed is False
    assert "invalid_action" in decision.triggered_rules
