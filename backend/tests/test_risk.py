from services import risk_service as rs


def test_risk_blocks_confidence():
    ctx = rs.RiskContext(equity=10000, open_trades=0, daily_trade_count=0, drawdown_pct=0, confidence=0.1)
    ok, _ = rs.validate(ctx)
    assert not ok


def test_risk_allows_nominal():
    ctx = rs.RiskContext(equity=10000, open_trades=0, daily_trade_count=0, drawdown_pct=0.01, confidence=0.8)
    ok, _ = rs.validate(ctx)
    assert ok
