import math

from experiments.baselines import BaselineConfig, run_baselines
from services.statistics import bootstrap_confidence_intervals, pairwise_pnl_test, pairwise_return_test


def test_all_baselines_run_on_same_price_series_and_fee_drag_is_finite():
    prices = [100, 101, 102, 101, 103]
    results = run_baselines(BaselineConfig(prices=prices, fee_bps=10, seed=7))
    buy_and_hold = next(row for row in results if row.name == "buy_and_hold")

    assert {row.name for row in results} == {"random", "buy_and_hold", "ema_crossover", "always_hold"}
    assert all(row.result.ticks == len(prices) for row in results)
    assert all(math.isfinite(row.fee_drag_pct) for row in results)
    assert buy_and_hold.result.fills == 1


def test_statistics_helpers_return_finite_values():
    intervals = bootstrap_confidence_intervals([100, 101, 99, 103], [1, -0.5, 2], resamples=50, seed=1)
    pnl_test = pairwise_pnl_test([1, 2, 3], [0.5, 1.5, 2.5], comparisons=3)
    return_test = pairwise_return_test([100, 101, 103, 106], [100, 100.5, 101, 102], comparisons=3)

    assert {interval.metric for interval in intervals} == {"sharpe", "return", "win_rate"}
    assert all(math.isfinite(interval.lower) and math.isfinite(interval.upper) for interval in intervals)
    assert math.isfinite(pnl_test.corrected_p_value)
    assert pnl_test.n == 3
    assert math.isfinite(return_test.corrected_p_value)
    assert return_test.n == 3
