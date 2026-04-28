import csv
import math

from experiments.compare_models import ModelComparisonConfig, compare_models


def test_multiple_mocked_models_run_successfully():
    result = compare_models(
        ModelComparisonConfig(
            models=["alpha", "beta"],
            prices=[100, 110, 120],
            mocked_decisions_by_model={
                "alpha": ["BUY", "HOLD", "SELL"],
                "beta": ["HOLD", "HOLD", "HOLD"],
            },
            fee_bps=0,
        )
    )

    assert {row.model for row in result.results} == {"alpha", "beta"}
    assert len(result.results) == 2


def test_same_price_series_is_used_for_every_model():
    prices = [100, 105, 103, 110]
    result = compare_models(
        ModelComparisonConfig(
            models=["alpha", "beta"],
            prices=prices,
            mocked_decisions_by_model={
                "alpha": ["BUY", "HOLD", "SELL", "HOLD"],
                "beta": ["HOLD", "BUY", "HOLD", "SELL"],
            },
            fee_bps=0,
        )
    )

    assert all(row.price_series == prices for row in result.results)


def test_csv_output_is_created(tmp_path):
    output = tmp_path / "comparison.csv"

    result = compare_models(
        ModelComparisonConfig(
            models=["alpha", "beta"],
            prices=[100, 110],
            mocked_decisions_by_model={
                "alpha": ["BUY", "SELL"],
                "beta": ["HOLD", "HOLD"],
            },
            output_csv_path=str(output),
            fee_bps=0,
        )
    )

    assert result.csv_path == str(output)
    assert output.exists()
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["model"] for row in rows] == result.ranked_models


def test_ranking_uses_sharpe_then_drawdown_then_return():
    result = compare_models(
        ModelComparisonConfig(
            models=["winner", "flat", "loser"],
            prices=[100, 130, 90, 120],
            mocked_decisions_by_model={
                "winner": ["BUY", "HOLD", "HOLD", "SELL"],
                "flat": ["HOLD", "HOLD", "HOLD", "HOLD"],
                "loser": ["HOLD", "BUY", "SELL", "HOLD"],
            },
            fee_bps=0,
        )
    )

    assert result.ranked_models[0] == "winner"
    assert result.results[0].rank == 1


def test_no_nan_or_inf_in_metrics():
    result = compare_models(
        ModelComparisonConfig(
            models=["alpha", "beta"],
            prices=[100, 100, 100],
            mocked_decisions_by_model={
                "alpha": ["BUY", "SELL", "HOLD"],
                "beta": ["HOLD", "HOLD", "HOLD"],
            },
            fee_bps=0,
        )
    )

    for row in result.results:
        values = [
            row.cumulative_return,
            row.sharpe,
            row.max_drawdown,
            row.win_rate,
            row.profit_factor,
            row.avg_latency_ms,
        ]
        assert all(math.isfinite(value) for value in values)
