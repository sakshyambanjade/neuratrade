import math

from api.routes.metrics import metrics
from services.metrics import (
    cumulative_return,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
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


def test_win_rate_known_pnl_list():
    assert win_rate([10, -5, 0, 4]) == 0.5


def test_profit_factor_known_pnl_list():
    assert profit_factor([10, -5, 0, 5]) == 3.0


def test_metrics_never_return_nan_for_sparse_inputs():
    values = [
        cumulative_return([]),
        cumulative_return([100]),
        max_drawdown([]),
        sharpe_ratio([100]),
        win_rate([]),
        profit_factor([10, 5]),
    ]

    assert all(math.isfinite(value) for value in values)
