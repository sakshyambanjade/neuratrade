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
