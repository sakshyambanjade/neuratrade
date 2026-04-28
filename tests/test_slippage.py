from services.slippage import calculate_slippage_bps, estimate_slippage_bps


def test_buy_slippage_bps_is_positive_when_execution_is_worse():
    assert calculate_slippage_bps(side="BUY", reference_price=100.0, execution_price=101.0) == 100.0


def test_sell_slippage_bps_is_positive_when_execution_is_worse():
    assert calculate_slippage_bps(side="SELL", reference_price=100.0, execution_price=99.0) == 100.0


def test_estimated_slippage_handles_zero_volume_without_nan():
    slippage = estimate_slippage_bps(spread_bps=8, order_size=1, minute_volume=0, volatility=0.01)

    assert slippage == 100.0


def test_estimated_slippage_increases_with_participation():
    small = estimate_slippage_bps(spread_bps=8, order_size=1, minute_volume=100, volatility=0.01)
    large = estimate_slippage_bps(spread_bps=8, order_size=50, minute_volume=100, volatility=0.01)

    assert large > small
