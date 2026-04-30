from scripts.prefill_history import prefill_history, rows_to_candles


def _row(open_ms, close):
    return [
        open_ms,
        str(close - 1),
        str(close + 2),
        str(close - 3),
        str(close),
        "12.5",
        open_ms + 59_999,
        "0",
        0,
        "0",
        "0",
        "0",
    ]


def test_rows_to_candles_maps_binance_kline_shape():
    candles = rows_to_candles([_row(60_000, 101.5)])

    assert candles == [
        {
            "ts": 60,
            "open": 100.5,
            "high": 103.5,
            "low": 98.5,
            "close": 101.5,
            "volume": 12.5,
            "source": "binance",
        }
    ]


def test_prefill_history_paginates_without_db_writes_in_dry_run():
    chunks = {
        0: [_row(0, 100), _row(60_000, 101)],
        120_000: [_row(120_000, 102), _row(180_000, 103)],
        240_000: [],
    }
    starts = []

    def fake_fetcher(**kwargs):
        starts.append(kwargs["start_ms"])
        return chunks[kwargs["start_ms"]]

    loaded = prefill_history(
        days=1,
        start_ms=0,
        end_ms=240_000,
        limit=2,
        sleep_seconds=0,
        dry_run=True,
        fetcher=fake_fetcher,
    )

    assert loaded == 4
    assert starts == [0, 120_000, 240_000]
