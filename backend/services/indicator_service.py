"""
Basic indicator calculations. Placeholder for full TA; keep side-effect free.
"""
from collections import deque
from typing import List


def ema(values: List[float], period: int) -> float:
    k = 2 / (period + 1)
    ema_val = values[0]
    for price in values[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def rsi(values: List[float], period: int = 14) -> float:
    gains, losses = [], []
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    if len(gains) < period:
        return 50.0
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    if len(values) < slow + signal:
        return 0, 0
    # compute EMA series
    ema_fast_series = []
    ema_slow_series = []
    prev_fast = values[0]
    prev_slow = values[0]
    k_fast = 2 / (fast + 1)
    k_slow = 2 / (slow + 1)
    for price in values:
        prev_fast = price * k_fast + prev_fast * (1 - k_fast)
        prev_slow = price * k_slow + prev_slow * (1 - k_slow)
        ema_fast_series.append(prev_fast)
        ema_slow_series.append(prev_slow)
    macd_series = [f - s for f, s in zip(ema_fast_series, ema_slow_series)]
    macd_line = macd_series[-1]
    signal_line = ema(macd_series[-(signal + 5):], signal)
    return macd_line, signal_line


def bollinger(values: List[float], period: int = 20, mult: float = 2.0):
    if len(values) < period:
        return 0, 0
    window = values[-period:]
    mean = sum(window) / period
    variance = sum((p - mean) ** 2 for p in window) / period
    std = variance ** 0.5
    return mean + mult * std, mean - mult * std


def latest_indicators(candles: List[dict]) -> dict:
    closes = [c["close"] for c in candles]
    if not closes:
        return {}
    macd_line, macd_signal = macd(closes)
    bb_upper, bb_lower = bollinger(closes)
    vols = [c.get("volume") or 0 for c in candles]
    vol_ratio = 0
    if vols and len(vols) >= 20:
        recent = vols[-1]
        avg20 = sum(vols[-20:]) / 20
        vol_ratio = recent / avg20 if avg20 else 0
    return {
        "price": closes[-1],
        "rsi": rsi(closes),
        "macd": macd_line,
        "macd_signal": macd_signal,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "ema9": ema(closes[-30:], 9),
        "ema21": ema(closes[-50:], 21),
        "volume_ratio": vol_ratio,
        "phase": "live",
    }
