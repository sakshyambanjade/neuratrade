from services import risk_service


def test_risk_engine_blocks_low_confidence():
    ok, reason = risk_service.validate(
        risk_service.RiskContext(
            equity=10_000,
            open_trades=0,
            daily_trade_count=0,
            drawdown_pct=0,
            confidence=0.0,
        )
    )

    assert ok is False
    assert "Confidence" in reason


def test_risk_engine_allows_nominal_context():
    ok, reason = risk_service.validate(
        risk_service.RiskContext(
            equity=10_000,
            open_trades=0,
            daily_trade_count=0,
            drawdown_pct=0,
            confidence=1.0,
        )
    )

    assert ok is True
    assert "Within limits" in reason
