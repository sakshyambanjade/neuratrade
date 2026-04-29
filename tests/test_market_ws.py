import math
import time

from services.market_ws import BinanceMarketWebSocket, MarketSnapshot, TickValidator


def test_trade_message_updates_last_price():
    feed = BinanceMarketWebSocket()

    feed.process_message({"data": {"e": "trade", "p": "50123.45", "q": "0.25"}})

    snapshot = feed.get_snapshot()
    assert snapshot.last_price == 50123.45
    assert snapshot.volume == 0.25
    assert snapshot.heartbeat_ts is not None


def test_book_ticker_updates_bid_ask_and_spread_bps():
    feed = BinanceMarketWebSocket()

    feed.process_message({"data": {"e": "bookTicker", "b": "100.0", "a": "101.0"}})

    snapshot = feed.get_snapshot()
    assert snapshot.bid == 100.0
    assert snapshot.ask == 101.0
    assert snapshot.spread_bps == (1.0 / 100.5) * 10_000


def test_depth20_updates_top_order_book_levels():
    feed = BinanceMarketWebSocket()

    feed.process_message(
        {
            "data": {
                "e": "depthUpdate",
                "b": [["100.0", "0.5"], ["101.0", "0.25"], ["99.0", "0.1"]],
                "a": [["102.0", "0.4"], ["103.0", "0.2"], ["101.5", "0.3"]],
            }
        }
    )

    snapshot = feed.get_snapshot()
    assert snapshot.bid == 101.0
    assert snapshot.ask == 101.5
    assert [level.price for level in snapshot.bids] == [101.0, 100.0, 99.0]
    assert [level.price for level in snapshot.asks] == [101.5, 102.0, 103.0]
    assert snapshot.spread_bps == (0.5 / 101.25) * 10_000


def test_kline_closed_candle_updates_history():
    feed = BinanceMarketWebSocket()

    feed.process_message(
        {
            "data": {
                "e": "kline",
                "k": {
                    "t": 1_700_000_000_000,
                    "o": "100.0",
                    "h": "105.0",
                    "l": "95.0",
                    "c": "102.0",
                    "v": "12.5",
                    "x": True,
                },
            }
        }
    )

    snapshot = feed.get_snapshot()
    assert len(snapshot.candles) == 1
    assert snapshot.candles[0].close == 102.0
    assert snapshot.candles[0].closed is True
    assert snapshot.last_price == 102.0


def test_malformed_message_does_not_crash():
    feed = BinanceMarketWebSocket()

    feed.process_message("{not-json")
    feed.process_message({"data": {"e": "trade", "p": "nan"}})
    feed.process_message({"data": {"e": "bookTicker", "b": "101", "a": "100"}})

    snapshot = feed.get_snapshot()
    assert snapshot.last_price is None
    assert snapshot.bid is None
    assert snapshot.ask is None


def test_get_snapshot_returns_valid_data():
    feed = BinanceMarketWebSocket()
    feed.process_message({"data": {"e": "trade", "p": "50000", "q": "1"}})
    feed.process_message({"data": {"e": "bookTicker", "b": "49999", "a": "50001"}})

    snapshot = feed.get_snapshot()

    assert isinstance(snapshot, MarketSnapshot)
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.last_price == 50000
    assert math.isfinite(snapshot.spread_bps)
    assert snapshot.spread_bps > 0


def test_tick_validator_accepts_fresh_valid_snapshot():
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        last_price=100.0,
        bid=99.9,
        ask=100.1,
        spread_bps=20.0,
        heartbeat_ts=time.time(),
    )

    result = TickValidator(max_staleness_sec=5, data_gap_sec=120).validate(snapshot)

    assert result.valid is True
    assert result.status == "valid"
    assert result.data_gap is False


def test_tick_validator_rejects_stale_data_gap():
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        last_price=100.0,
        bid=99.9,
        ask=100.1,
        spread_bps=20.0,
        heartbeat_ts=time.time() - 180,
    )

    result = TickValidator(max_staleness_sec=5, data_gap_sec=120).validate(snapshot)

    assert result.valid is False
    assert result.status == "stale"
    assert result.data_gap is True


def test_tick_validator_rejects_crossed_spread():
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        last_price=100.0,
        bid=101.0,
        ask=100.0,
        spread_bps=0.0,
        heartbeat_ts=time.time(),
    )

    result = TickValidator().validate(snapshot)

    assert result.valid is False
    assert result.status == "crossed"
