import csv

import pytest

from reports.generate_report import generate_markdown_report
from reports.plots import (
    plot_ablation_results,
    plot_confidence_return_scatter,
    plot_drawdown_curve,
    plot_equity_curve,
    plot_equity_curves,
    plot_model_comparison,
    plot_parameter_vs_sharpe,
    plot_regime_breakdown,
)


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_report_file_is_created(tmp_path):
    _write_csv(
        tmp_path / "model_comparison.csv",
        ["rank", "model", "return", "sharpe", "max_drawdown", "win_rate", "profit_factor"],
        [
            {
                "rank": 1,
                "model": "alpha",
                "return": 0.123456,
                "sharpe": 1.234567,
                "max_drawdown": 0.056789,
                "win_rate": 0.654321,
                "profit_factor": 1.54321,
            }
        ],
    )
    _write_csv(
        tmp_path / "ablation_results.csv",
        [
            "variant",
            "cumulative_return",
            "sharpe",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "avg_slippage_bps",
            "avg_latency_ms",
            "trade_count",
        ],
        [
            {
                "variant": "full_system",
                "cumulative_return": 0.1,
                "sharpe": 1.2,
                "max_drawdown": 0.05,
                "win_rate": 0.6,
                "profit_factor": 1.5,
                "avg_slippage_bps": 3,
                "avg_latency_ms": 20,
                "trade_count": 4,
            }
        ],
    )
    (tmp_path / "ablation_summary.json").write_text('{"best_sharpe":"full_system"}', encoding="utf-8")
    (tmp_path / "model_comparison_statistics.json").write_text(
        """
{
  "bootstrap_intervals": {
    "alpha": {
      "return": [0.01, 0.2],
      "sharpe": [0.5, 1.9],
      "win_rate": [0.4, 0.8]
    }
  },
  "pairwise_tests": [
    {
      "left": "alpha",
      "right": "beta",
      "test_name": "wilcoxon_signed_rank",
      "p_value": 0.012345,
      "corrected_p_value": 0.024691,
      "effect_size": 0.333333,
      "n": 32
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "equity.png").write_bytes(b"png")

    output = tmp_path / "report.md"
    generate_markdown_report(42, output)

    text = output.read_text(encoding="utf-8")
    assert output.exists()
    assert "NeuraTradeBench Experiment 42" in text
    assert "Model Leaderboard" in text
    assert "0.1235" in text
    assert "Statistical Validation" in text
    assert "wilcoxon_signed_rank" in text
    assert "Limitations" in text
    assert "equity.png" in text


def test_png_files_are_created(tmp_path):
    equity_csv = tmp_path / "equity.csv"
    comparison_csv = tmp_path / "model_comparison.csv"
    ablation_csv = tmp_path / "ablation_results.csv"
    _write_csv(equity_csv, ["equity"], [{"equity": 100}, {"equity": 110}, {"equity": 90}])
    _write_csv(comparison_csv, ["model", "return", "sharpe"], [{"model": "alpha", "return": 0.1, "sharpe": 1.0}])
    _write_csv(
        ablation_csv,
        ["variant", "cumulative_return", "sharpe", "max_drawdown"],
        [{"variant": "full_system", "cumulative_return": 0.1, "sharpe": 1.0, "max_drawdown": 0.05}],
    )

    outputs = [
        tmp_path / "equity.png",
        tmp_path / "drawdown.png",
        tmp_path / "models.png",
        tmp_path / "ablation.png",
        tmp_path / "multi_equity.png",
        tmp_path / "confidence.png",
        tmp_path / "params.png",
        tmp_path / "regimes.png",
    ]
    plot_equity_curve(equity_csv, outputs[0])
    plot_drawdown_curve(equity_csv, outputs[1])
    plot_model_comparison(comparison_csv, outputs[2])
    plot_ablation_results(ablation_csv, outputs[3])
    multi_equity_csv = tmp_path / "multi_equity.csv"
    confidence_csv = tmp_path / "confidence.csv"
    regime_csv = tmp_path / "regime.csv"
    _write_csv(
        multi_equity_csv,
        ["model", "step", "equity"],
        [{"model": "alpha", "step": 0, "equity": 100}, {"model": "alpha", "step": 1, "equity": 101}],
    )
    _write_csv(
        confidence_csv,
        ["model", "confidence", "realized_return"],
        [{"model": "alpha", "confidence": 0.7, "realized_return": 0.01}],
    )
    _write_csv(regime_csv, ["regime", "model", "sharpe"], [{"regime": "bull", "model": "alpha", "sharpe": 1.1}])
    plot_equity_curves(multi_equity_csv, outputs[4])
    plot_confidence_return_scatter(confidence_csv, outputs[5])
    plot_parameter_vs_sharpe(comparison_csv, outputs[6], {"alpha": 1.0})
    plot_regime_breakdown(regime_csv, outputs[7])

    assert all(path.exists() and path.stat().st_size > 0 for path in outputs)


def test_empty_csv_handled_safely(tmp_path):
    empty = tmp_path / "empty.csv"
    _write_csv(empty, ["equity"], [])
    output = tmp_path / "empty.png"

    plot_equity_curve(empty, output)

    assert output.exists()
    assert output.stat().st_size > 0


def test_missing_columns_produce_clear_error(tmp_path):
    bad = tmp_path / "bad.csv"
    _write_csv(bad, ["model"], [{"model": "alpha"}])

    with pytest.raises(ValueError, match="Missing required column"):
        plot_model_comparison(bad, tmp_path / "bad.png")
