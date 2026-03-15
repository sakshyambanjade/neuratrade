from services import decision_service as ds


def test_fallback_rule_buy():
    indicators = {"rsi": 25, "macd": 0.01}
    d = ds._fallback_rule(indicators)  # type: ignore
    assert d.action == "BUY"
