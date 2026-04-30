"""
Summarize V1 decision outcomes by logged market regime.

Run from backend/:
    python scripts/regime_analysis.py --experiment-name v1-live
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import DB_PATH  # noqa: E402

DEFAULT_OUTPUT_DIR = Path("../artifacts/v1")


def load_regime_outcomes(
    db_path: str | Path,
    *,
    experiment_name: str | None = None,
    model_name: str | None = None,
    max_fill_lag_seconds: int = 5,
) -> list[dict[str, Any]]:
    filters = ["i.parsed_action IN ('BUY', 'SELL')"]
    params: list[Any] = [max_fill_lag_seconds]
    if experiment_name:
        filters.append("e.name LIKE ?")
        params.append(f"%{experiment_name}%")
    if model_name:
        filters.append("i.model_name = ?")
        params.append(model_name)

    query = f"""
        SELECT
            e.name AS experiment_name,
            i.model_run_id,
            i.model_name,
            i.id AS inference_id,
            i.timestamp,
            i.parsed_action,
            i.confidence,
            c.regime,
            f.id AS fill_id,
            f.realized_pnl,
            f.slippage_bps,
            f.latency_ms
        FROM inference_logs i
        JOIN model_runs mr ON mr.id = i.model_run_id
        JOIN experiments e ON e.id = mr.experiment_id
        LEFT JOIN cycle_indicators c ON c.id = i.cycle_indicator_id
        LEFT JOIN execution_fills f ON f.id = (
            SELECT f2.id
            FROM execution_fills f2
            WHERE f2.model_run_id = i.model_run_id
              AND f2.side = i.parsed_action
              AND f2.timestamp >= i.timestamp
              AND f2.timestamp <= i.timestamp + ?
            ORDER BY f2.timestamp ASC, f2.id ASC
            LIMIT 1
        )
        WHERE {" AND ".join(filters)}
        ORDER BY i.model_run_id, i.id
    """
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def summarize_by_regime(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("regime") or "unknown"), str(row.get("model_name") or ""))].append(row)

    output = []
    for (regime, model_name), group in sorted(grouped.items()):
        pnls = [_finite(row.get("realized_pnl")) for row in group if row.get("realized_pnl") is not None]
        confidences = [_finite(row.get("confidence")) for row in group]
        output.append(
            {
                "regime": regime,
                "model": model_name,
                "n": len(group),
                "fills": len(pnls),
                "return": sum(pnls),
                "sharpe": _trade_sharpe(pnls),
                "max_drawdown": _pnl_drawdown(pnls),
                "win_rate": _win_rate(pnls),
                "mean_realized_pnl": _average(pnls),
                "mean_confidence": _average(confidences),
            }
        )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze V1 live performance by logged market regime.")
    parser.add_argument("--db-path", default=DB_PATH, help="SQLite DB path. Defaults to config.DB_PATH.")
    parser.add_argument("--experiment-name", default=None, help="Substring filter for experiment names.")
    parser.add_argument("--model", default=None, help="Exact model_name filter.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for CSV/JSON artifacts.")
    parser.add_argument(
        "--max-fill-lag-seconds",
        type=int,
        default=5,
        help="Pair an inference to a fill only if the fill appears within this many seconds.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = load_regime_outcomes(
        args.db_path,
        experiment_name=args.experiment_name,
        model_name=args.model,
        max_fill_lag_seconds=args.max_fill_lag_seconds,
    )
    summary = summarize_by_regime(rows)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "regime_breakdown.csv",
        summary,
        fieldnames=[
            "regime",
            "model",
            "n",
            "fills",
            "return",
            "sharpe",
            "max_drawdown",
            "win_rate",
            "mean_realized_pnl",
            "mean_confidence",
        ],
    )
    (output_dir / "regime_summary.json").write_text(
        json.dumps({"rows": summary}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("=== Regime Analysis ===")
    for row in summary:
        print(
            f"Regime: {row['regime']:16s} | model={row['model']:16s} "
            f"| n={row['n']:4d} | fills={row['fills']:4d} | Sharpe={row['sharpe']:.3f}"
        )
    print(f"Artifacts written to: {output_dir.resolve()}")


def _write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str] | None = None) -> None:
    fieldnames = fieldnames or (list(rows[0].keys()) if rows else [])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _trade_sharpe(pnls: list[float]) -> float:
    if len(pnls) < 2:
        return 0.0
    volatility = pstdev(pnls)
    return _finite(mean(pnls) / volatility) if volatility > 0 else 0.0


def _pnl_drawdown(pnls: list[float]) -> float:
    if not pnls:
        return 0.0
    equity = [0.0]
    for pnl in pnls:
        equity.append(equity[-1] + pnl)
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        worst = max(worst, peak - value)
    return _finite(worst)


def _win_rate(pnls: list[float]) -> float:
    return sum(1 for pnl in pnls if pnl > 0) / len(pnls) if pnls else 0.0


def _average(values: list[float]) -> float:
    return _finite(mean(values)) if values else 0.0


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


if __name__ == "__main__":
    main()
