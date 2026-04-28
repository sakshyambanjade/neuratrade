import math

from services.execution import ExecutionSimulator, OrderRequest


def test_buy_reduces_cash_and_increases_btc():
    simulator = ExecutionSimulator()
    report = simulator.execute_market_order(
        OrderRequest(
            side="BUY",
            quantity=0.1,
            price=50_000,
            cash_balance=10_000,
            btc_balance=0,
            spread_bps=0,
            minute_volume=100,
            volatility=0,
            fee_bps=0,
        )
    )

    assert report.status == "FILLED"
    assert report.cash_after == 5_000
    assert report.btc_after == 0.1


def test_sell_reduces_btc_and_increases_cash():
    simulator = ExecutionSimulator()
    report = simulator.execute_market_order(
        OrderRequest(
            side="SELL",
            quantity=0.1,
            price=50_000,
            cash_balance=1_000,
            btc_balance=0.2,
            spread_bps=0,
            minute_volume=100,
            volatility=0,
            fee_bps=0,
        )
    )

    assert report.status == "FILLED"
    assert report.btc_after == 0.1
    assert report.cash_after == 6_000


def test_fee_is_deducted_from_buy_cash():
    simulator = ExecutionSimulator()
    report = simulator.execute_market_order(
        OrderRequest(
            side="BUY",
            quantity=1,
            price=100,
            cash_balance=1_000,
            btc_balance=0,
            spread_bps=0,
            minute_volume=100,
            volatility=0,
            fee_bps=10,
        )
    )

    assert report.fee == 0.1
    assert report.cash_after == 899.9


def test_slippage_worsens_buy_and_sell_prices():
    simulator = ExecutionSimulator()
    buy = simulator.execute_market_order(
        OrderRequest(
            side="BUY",
            quantity=1,
            price=100,
            cash_balance=1_000,
            btc_balance=0,
            spread_bps=10,
            minute_volume=100,
            volatility=0,
            fee_bps=0,
        )
    )
    sell = simulator.execute_market_order(
        OrderRequest(
            side="SELL",
            quantity=1,
            price=100,
            cash_balance=0,
            btc_balance=1,
            spread_bps=10,
            minute_volume=100,
            volatility=0,
            fee_bps=0,
        )
    )

    assert buy.average_fill_price > 100
    assert sell.average_fill_price < 100


def test_insufficient_balance_rejects_order():
    simulator = ExecutionSimulator()
    report = simulator.execute_market_order(
        OrderRequest(
            side="BUY",
            quantity=1,
            price=100,
            cash_balance=50,
            btc_balance=0,
            spread_bps=0,
            minute_volume=100,
            volatility=0,
            fee_bps=0,
        )
    )

    assert report.status == "REJECTED"
    assert report.error_reason.startswith("INSUFFICIENT_CASH")
    assert report.cash_after == 50
    assert report.btc_after == 0


def test_zero_quantity_rejects_order():
    simulator = ExecutionSimulator()
    report = simulator.execute_market_order(
        OrderRequest(
            side="BUY",
            quantity=0,
            price=100,
            cash_balance=1_000,
            btc_balance=0,
        )
    )

    assert report.status == "REJECTED"
    assert report.error_reason.startswith("INVALID_QUANTITY")


def test_no_nan_values_allowed():
    simulator = ExecutionSimulator()
    report = simulator.execute_market_order(
        OrderRequest(
            side="SELL",
            quantity=0.5,
            price=100,
            cash_balance=1_000,
            btc_balance=1,
            avg_entry_price=90,
            spread_bps=0,
            minute_volume=0,
            volatility=0,
            fee_bps=10,
        )
    )

    values = [
        report.requested_quantity,
        report.filled_quantity,
        report.average_fill_price,
        report.gross_notional,
        report.fee,
        report.slippage_bps,
        report.cash_after,
        report.btc_after,
        report.realized_pnl,
        report.latency_ms,
    ]
    assert all(value is not None and math.isfinite(value) for value in values)
