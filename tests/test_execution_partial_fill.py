from services.execution import ExecutionSimulator, SimulatedOrder
from services.fees import FeeModel
from services.latency import FixedLatencyModel
from services.order_book import OrderBookSnapshot


def test_market_order_partial_fill_reports_fees_and_slippage():
    book = OrderBookSnapshot.from_depth(
        bids=[(99.0, 1.0)],
        asks=[(101.0, 0.25), (102.0, 0.25)],
    )
    simulator = ExecutionSimulator(
        fee_model=FeeModel(rate_bps=10),
        latency_model=FixedLatencyModel(25),
    )
    order = SimulatedOrder(side="BUY", order_type="MARKET", quantity=1.0)

    report = simulator.execute(order, book)

    assert report.status == "PARTIAL"
    assert report.filled_quantity == 0.5
    assert report.remaining_quantity == 0.5
    assert report.average_price == 101.5
    assert report.fee_total == 0.05075
    assert report.slippage_bps == 150.0
    assert report.latency_ms == 25
    assert len(report.fills) == 2


def test_limit_order_respects_price_and_partially_fills():
    book = OrderBookSnapshot.from_depth(
        bids=[(99.0, 1.0)],
        asks=[(100.5, 0.1), (101.5, 1.0)],
    )
    simulator = ExecutionSimulator()
    order = SimulatedOrder(side="BUY", order_type="LIMIT", quantity=0.5, limit_price=101.0)

    report = simulator.execute(order, book)

    assert report.status == "PARTIAL"
    assert report.filled_quantity == 0.1
    assert report.average_price == 100.5
