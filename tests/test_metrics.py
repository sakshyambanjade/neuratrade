import math

from api.routes.metrics import metrics
from services.metrics import (
    NO_LOSS_PROFIT_FACTOR,
    average_latency,
    average_slippage,
    calmar_ratio,
    conditional_value_at_risk_95,
    confidence_return_correlation,
    cumulative_return,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    value_at_risk_95,
    win_rate,
)


def test_metrics_endpoint_shape():
    result = metrics()

    assert isinstance(result["ts"], int)


def test_max_drawdown_known_series():
    assert max_drawdown([100, 120, 90, 150]) == 0.25


def test_cumulative_return_known_series():
    assert cumulative_return([100, 125]) == 0.25


def test_sharpe_no_crash_on_flat_equity():
    assert sharpe_ratio([100, 100, 100]) == 0.0


def test_extended_risk_metrics_are_finite_for_known_series():
    equity = [100.0]
    for index in range(40):
        step_return = -0.004 if index % 6 == 0 else 0.006
        equity.append(equity[-1] * (1 + step_return))

    assert sortino_ratio(equity) > 0
    assert calmar_ratio(equity) > 0
    assert value_at_risk_95(equity) >= 0
    assert conditional_value_at_risk_95(equity) >= 0


def test_execution_and_llm_metric_helpers():
    assert average_latency([10, 20, 30]) == 20
    assert average_slippage([1.0, 2.0, 3.0]) == 2.0
    assert confidence_return_correlation([0.1, 0.5, 0.9], [-1, 0, 1]) > 0.99


def test_win_rate_known_pnl_list():
    assert win_rate([10, -5, 0, 4]) == 0.5


def test_profit_factor_known_pnl_list():
    assert profit_factor([10, -5, 0, 5]) == 3.0


def test_profit_factor_caps_no_loss_winners():
    assert profit_factor([10, 5]) == NO_LOSS_PROFIT_FACTOR


def test_risk_adjusted_metrics_require_minimum_sample_size():
    short_equity = [100, 101, 102, 103, 104, 105, 106, 107]

    assert sharpe_ratio(short_equity) == 0.0
    assert sortino_ratio(short_equity) == 0.0
    assert calmar_ratio(short_equity) == 0.0


def test_metrics_never_return_nan_for_sparse_inputs():
    values = [
        cumulative_return([]),
        cumulative_return([100]),
        max_drawdown([]),
        sharpe_ratio([100]),
        sortino_ratio([100]),
        calmar_ratio([100]),
        value_at_risk_95([]),
        conditional_value_at_risk_95([]),
        average_latency([]),
        average_slippage([]),
        confidence_return_correlation([], []),
        win_rate([]),
        profit_factor([10, 5]),
    ]

    assert all(math.isfinite(value) for value in values)
