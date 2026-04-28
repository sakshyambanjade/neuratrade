import csv
import json
import math

from experiments.ablation import AblationConfig, run_ablation


def _config(**overrides):
    data = {
        "prices": [100, 105, 95, 110],
        "decisions": [
            {"action": "BUY", "confidence": 0.9, "position_size_pct": 0.2, "stop_loss": 0.02},
            "HOLD",
            {"action": "SELL", "confidence": 0.9, "position_size_pct": 1.0, "stop_loss": 0.02},
            "HOLD",
        ],
        "fee_bps": 0,
        "spread_bps": 10,
        "volatility": 0.01,
        "latency_ms": 25,
    }
    data.update(overrides)
    return AblationConfig(**data)


def test_all_variants_run():
    result = run_ablation(_config())

    assert {row.variant for row in result.variants} == {
        "full_system",
        "no_risk_engine",
        "no_memory",
        "no_news",
        "no_slippage",
        "no_latency",
    }


def test_same_input_series_used_across_variants():
    prices = [100, 101, 102]
    result = run_ablation(_config(prices=prices, decisions=["HOLD", "HOLD", "HOLD"]))

    assert all(row.price_series == prices for row in result.variants)


def test_csv_and_json_outputs_created(tmp_path):
    result = run_ablation(_config(output_dir=str(tmp_path)))

    assert result.csv_path == str(tmp_path / "ablation_results.csv")
    assert result.summary_json_path == str(tmp_path / "ablation_summary.json")
    with open(result.csv_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with open(result.summary_json_path, encoding="utf-8") as handle:
        summary = json.load(handle)

    assert len(rows) == 6
    assert set(summary) == {"best_sharpe", "lowest_drawdown", "highest_return"}


def test_no_slippage_has_zero_slippage():
    result = run_ablation(_config())
    row = next(row for row in result.variants if row.variant == "no_slippage")

    assert row.avg_slippage_bps == 0.0


def test_no_latency_has_zero_latency():
    result = run_ablation(_config())
    row = next(row for row in result.variants if row.variant == "no_latency")

    assert row.avg_latency_ms == 0.0


def test_no_risk_engine_allows_trades_that_risk_engine_blocks():
    result = run_ablation(
        _config(
            decisions=[
                {"action": "BUY", "confidence": 0.1, "position_size_pct": 0.2, "stop_loss": 0.02},
                {"action": "SELL", "confidence": 0.9, "position_size_pct": 1.0, "stop_loss": 0.02},
            ],
            prices=[100, 110],
        )
    )

    full = next(row for row in result.variants if row.variant == "full_system")
    no_risk = next(row for row in result.variants if row.variant == "no_risk_engine")

    assert full.risk_blocked >= 1
    assert no_risk.risk_blocked == 0
    assert no_risk.trade_count > full.trade_count


def test_no_nan_or_inf_in_results():
    result = run_ablation(_config())

    for row in result.variants:
        values = [
            row.cumulative_return,
            row.sharpe,
            row.max_drawdown,
            row.win_rate,
            row.profit_factor,
            row.avg_slippage_bps,
            row.avg_latency_ms,
        ]
        assert all(math.isfinite(value) for value in values)
