import math

from experiments.runner import ExperimentConfig, run_mock_experiment


def test_experiment_runner_returns_metrics():
    result = run_mock_experiment(
        ExperimentConfig(
            name="unit",
            prices=[100, 110, 120],
            mocked_decisions=[
                {"action": "BUY", "confidence": 1.0, "position_size_pct": 0.5},
                "HOLD",
                {"action": "SELL", "confidence": 1.0, "position_size_pct": 1.0},
            ],
            initial_cash=1_000,
            fee_bps=0,
        )
    )

    assert result.name == "unit"
    assert result.ticks == 3
    assert result.fills == 2
    assert result.cumulative_return > 0
    assert result.win_rate == 1.0


def test_experiment_runner_outputs_no_nan_or_inf():
    result = run_mock_experiment(
        ExperimentConfig(
            prices=[100, 100, 100],
            mocked_decisions=["HOLD", "BUY", "SELL"],
            fee_bps=0,
        )
    )

    scalar_values = [
        result.cumulative_return,
        result.sharpe,
        result.max_drawdown,
        result.win_rate,
        result.profit_factor,
    ]

    assert all(math.isfinite(value) for value in scalar_values)
    assert all(math.isfinite(value) for value in result.equity_series)
    assert all(math.isfinite(value) for value in result.trade_pnls)
