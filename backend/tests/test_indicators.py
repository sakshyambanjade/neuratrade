from services import indicator_service as ind


def test_macd_signal_stable():
    closes = [i for i in range(1, 60)]
    macd_line, macd_signal = ind.macd(closes)
    assert abs(macd_signal) < abs(macd_line) + 1  # signal should track macd


def test_rsi_bounds():
    closes = [50] * 30
    rsi = ind.rsi(closes)
    assert 0 <= rsi <= 100
