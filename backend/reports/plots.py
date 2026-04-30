"""
Matplotlib-only plotting helpers for research artifacts.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_equity_curve(results_csv: str | Path, output_png: str | Path) -> None:
    rows = _read_csv(results_csv, required=["equity"])
    equity = _numbers(rows, "equity")
    _line_plot(
        output_png,
        title="Equity Curve",
        ylabel="Equity",
        series=equity,
        empty_label="No equity data",
    )


def plot_drawdown_curve(results_csv: str | Path, output_png: str | Path) -> None:
    rows = _read_csv(results_csv, required=["equity"])
    equity = _numbers(rows, "equity")
    drawdowns = _drawdowns(equity)
    _line_plot(
        output_png,
        title="Drawdown Curve",
        ylabel="Drawdown",
        series=drawdowns,
        empty_label="No drawdown data",
    )


def plot_model_comparison(results_csv: str | Path, output_png: str | Path) -> None:
    rows = _read_csv(results_csv, required=["model", "sharpe", "return"])
    labels = [row["model"] for row in rows]
    values = _numbers(rows, "sharpe")
    _bar_plot(
        output_png,
        title="Model Comparison by Sharpe",
        ylabel="Sharpe",
        labels=labels,
        values=values,
        empty_label="No model data",
    )


def plot_ablation_results(ablation_csv: str | Path, output_png: str | Path) -> None:
    rows = _read_csv(ablation_csv, required=["variant", "sharpe", "max_drawdown", "cumulative_return"])
    labels = [row["variant"] for row in rows]
    values = _numbers(rows, "sharpe")
    _bar_plot(
        output_png,
        title="Ablation Results by Sharpe",
        ylabel="Sharpe",
        labels=labels,
        values=values,
        empty_label="No ablation data",
    )


def plot_equity_curves(equity_csv: str | Path, output_png: str | Path) -> None:
    rows = _read_csv(equity_csv, required=["model", "step", "equity"])
    series: dict[str, list[tuple[int, float]]] = {}
    for row in rows:
        try:
            step = int(float(row["step"]))
            equity = float(row["equity"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(equity):
            series.setdefault(row["model"], []).append((step, equity))

    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    if series:
        for label, values in sorted(series.items()):
            values = sorted(values)
            ax.plot([step for step, _ in values], [equity for _, equity in values], linewidth=1.8, label=label)
        ax.legend(fontsize=8)
    else:
        ax.text(0.5, 0.5, "No equity data", ha="center", va="center", transform=ax.transAxes)
    ax.set_title("Equity Curves")
    ax.set_xlabel("Decision Step")
    ax.set_ylabel("Simulated Equity")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_png, dpi=300)
    plt.close(fig)


def plot_confidence_return_scatter(confidence_csv: str | Path, output_png: str | Path) -> None:
    rows = _read_csv(confidence_csv, required=["model", "confidence", "realized_return"])
    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.5, 5))
    plotted = False
    for model in sorted({row["model"] for row in rows}):
        model_rows = [row for row in rows if row["model"] == model]
        confidences = _numbers(model_rows, "confidence")
        returns = _numbers(model_rows, "realized_return")
        if confidences and returns:
            ax.scatter(confidences, returns, s=10, alpha=0.45, label=model)
            plotted = True
    if plotted:
        ax.legend(fontsize=8)
    else:
        ax.text(0.5, 0.5, "No confidence data", ha="center", va="center", transform=ax.transAxes)
    ax.axhline(0, color="#555555", linewidth=0.8)
    ax.set_title("Confidence vs. Realized Return")
    ax.set_xlabel("Model Confidence")
    ax.set_ylabel("Next-period Signed Return")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_png, dpi=300)
    plt.close(fig)


def plot_parameter_vs_sharpe(
    results_csv: str | Path,
    output_png: str | Path,
    model_parameters_b: dict[str, float],
) -> None:
    rows = _read_csv(results_csv, required=["model", "sharpe"])
    points = [
        (model_parameters_b[row["model"]], _numbers([row], "sharpe")[0], row["model"])
        for row in rows
        if row["model"] in model_parameters_b
    ]
    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.5, 5))
    if points:
        ax.scatter([point[0] for point in points], [point[1] for point in points], s=50)
        for params, sharpe, label in points:
            ax.annotate(label, (params, sharpe), fontsize=8, xytext=(4, 4), textcoords="offset points")
    else:
        ax.text(0.5, 0.5, "No parameter metadata", ha="center", va="center", transform=ax.transAxes)
    ax.set_title("Parameter Count vs. Sharpe")
    ax.set_xlabel("Parameters (B)")
    ax.set_ylabel("Sharpe")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_png, dpi=300)
    plt.close(fig)


def plot_regime_breakdown(regime_csv: str | Path, output_png: str | Path) -> None:
    rows = _read_csv(regime_csv, required=["regime", "model", "sharpe"])
    labels = [f"{row['regime']}:{row['model']}" for row in rows]
    values = _numbers(rows, "sharpe")
    _bar_plot(
        output_png,
        title="Sharpe by Market Regime",
        ylabel="Sharpe",
        labels=labels,
        values=values,
        empty_label="No regime data",
    )


def _read_csv(path: str | Path, *, required: list[str]) -> list[dict[str, str]]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [column for column in required if column not in fieldnames]
        if missing:
            raise ValueError(f"Missing required column(s): {', '.join(missing)}")
        return list(reader)


def _numbers(rows: Iterable[dict[str, str]], column: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        try:
            value = float(row.get(column, 0.0))
        except (TypeError, ValueError):
            value = 0.0
        values.append(value if math.isfinite(value) else 0.0)
    return values


def _drawdowns(equity: list[float]) -> list[float]:
    peak = equity[0] if equity else 0.0
    values: list[float] = []
    for value in equity:
        peak = max(peak, value)
        values.append((peak - value) / peak if peak > 0 else 0.0)
    return values


def _line_plot(
    output_png: str | Path,
    *,
    title: str,
    ylabel: str,
    series: list[float],
    empty_label: str,
) -> None:
    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if series:
        ax.plot(range(len(series)), series, linewidth=2)
    else:
        ax.text(0.5, 0.5, empty_label, ha="center", va="center", transform=ax.transAxes)
    ax.set_title(title)
    ax.set_xlabel("Step")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_png, dpi=150)
    plt.close(fig)


def _bar_plot(
    output_png: str | Path,
    *,
    title: str,
    ylabel: str,
    labels: list[str],
    values: list[float],
    empty_label: str,
) -> None:
    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if labels and values:
        ax.bar(labels, values, color="#3366aa")
        ax.tick_params(axis="x", labelrotation=25)
    else:
        ax.text(0.5, 0.5, empty_label, ha="center", va="center", transform=ax.transAxes)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_png, dpi=150)
    plt.close(fig)
