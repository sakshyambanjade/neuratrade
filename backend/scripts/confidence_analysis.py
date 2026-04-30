"""
Analyze whether V1 model confidence predicts realized outcomes.

Run from backend/:
    python scripts/confidence_analysis.py --experiment-name v1-live
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


def load_decision_outcomes(
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
            i.id AS inference_id,
            i.timestamp,
            i.model_name,
            i.parsed_action,
            i.confidence,
            f.id AS fill_id,
            f.realized_pnl,
            f.slippage_bps,
            f.latency_ms AS fill_latency_ms,
            mt.last_price AS decision_price,
            next_mt.last_price AS next_price
        FROM inference_logs i
        JOIN model_runs mr ON mr.id = i.model_run_id
        JOIN experiments e ON e.id = mr.experiment_id
        LEFT JOIN market_ticks mt ON mt.id = i.market_tick_id
        LEFT JOIN market_ticks next_mt ON next_mt.id = (
            SELECT mt2.id
            FROM market_ticks mt2
            WHERE mt2.model_run_id = i.model_run_id
              AND mt2.cycle_index > mt.cycle_index
              AND mt2.last_price IS NOT NULL
            ORDER BY mt2.cycle_index ASC
            LIMIT 1
        )
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
        rows = [dict(row) for row in connection.execute(query, params).fetchall()]

    for row in rows:
        row["realized_return"] = signed_next_return(
            row.get("parsed_action"),
            row.get("decision_price"),
            row.get("next_price"),
        )
    return rows


def calibration_rows(rows: list[dict[str, Any]], *, buckets: int = 10) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        confidence = _finite(row.get("confidence"))
        bucket = min(buckets - 1, max(0, int(confidence * buckets)))
        grouped[(str(row.get("model_name", "")), bucket)].append(row)

    output = []
    for (model_name, bucket), bucket_rows in sorted(grouped.items()):
        pnls = [_finite(row.get("realized_pnl")) for row in bucket_rows if row.get("realized_pnl") is not None]
        returns = [_finite(row.get("realized_return")) for row in bucket_rows if row.get("realized_return") is not None]
        output.append(
            {
                "model": model_name,
                "confidence_bucket": f"{bucket / buckets:.1f}-{(bucket + 1) / buckets:.1f}",
                "count": len(bucket_rows),
                "fills": len(pnls),
                "mean_realized_pnl": _average(pnls),
                "std_realized_pnl": _std(pnls),
                "mean_realized_return": _average(returns),
            }
        )
    return output


def correlation_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"overall": _correlations(rows)}
    for model_name in sorted({str(row.get("model_name", "")) for row in rows}):
        model_rows = [row for row in rows if row.get("model_name") == model_name]
        summary[model_name] = _correlations(model_rows)
    return summary


def signed_next_return(action: object, decision_price: object, next_price: object) -> float | None:
    current = _optional_float(decision_price)
    future = _optional_float(next_price)
    if current is None or future is None or current <= 0:
        return None
    raw_return = future / current - 1
    normalized_action = str(action or "").upper()
    if normalized_action == "BUY":
        return _finite(raw_return)
    if normalized_action == "SELL":
        return _finite(-raw_return)
    return 0.0


def pearson(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys, strict=False) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 2:
        return 0.0
    clean_xs = [pair[0] for pair in pairs]
    clean_ys = [pair[1] for pair in pairs]
    x_mean = mean(clean_xs)
    y_mean = mean(clean_ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_var = sum((x - x_mean) ** 2 for x in clean_xs)
    y_var = sum((y - y_mean) ** 2 for y in clean_ys)
    denominator = math.sqrt(x_var * y_var)
    return _finite(numerator / denominator) if denominator > 0 else 0.0


def spearman(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys, strict=False) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 2:
        return 0.0
    return pearson(_ranks([pair[0] for pair in pairs]), _ranks([pair[1] for pair in pairs]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze confidence calibration from V1 live DB logs.")
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
    rows = load_decision_outcomes(
        args.db_path,
        experiment_name=args.experiment_name,
        model_name=args.model,
        max_fill_lag_seconds=args.max_fill_lag_seconds,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    calibration = calibration_rows(rows)
    summary = correlation_summary(rows)
    _write_csv(
        output_dir / "confidence_calibration.csv",
        calibration,
        fieldnames=[
            "model",
            "confidence_bucket",
            "count",
            "fills",
            "mean_realized_pnl",
            "std_realized_pnl",
            "mean_realized_return",
        ],
    )
    _write_csv(
        output_dir / "confidence_return.csv",
        [
            {
                "model": row.get("model_name", ""),
                "step": index,
                "action": row.get("parsed_action", ""),
                "confidence": row.get("confidence", 0.0),
                "realized_return": row.get("realized_return", 0.0),
            }
            for index, row in enumerate(rows)
            if row.get("realized_return") is not None
        ],
        fieldnames=["model", "step", "action", "confidence", "realized_return"],
    )
    (output_dir / "confidence_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print("=== Confidence Calibration ===")
    print(f"decisions={len(rows)} buckets={len(calibration)}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Artifacts written to: {output_dir.resolve()}")


def _correlations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    confidence_pnl_pairs = [
        (_finite(row.get("confidence")), _finite(row.get("realized_pnl")))
        for row in rows
        if row.get("realized_pnl") is not None
    ]
    confidence_return_pairs = [
        (_finite(row.get("confidence")), _finite(row.get("realized_return")))
        for row in rows
        if row.get("realized_return") is not None
    ]
    pnl_xs = [pair[0] for pair in confidence_pnl_pairs]
    pnl_ys = [pair[1] for pair in confidence_pnl_pairs]
    return_xs = [pair[0] for pair in confidence_return_pairs]
    return_ys = [pair[1] for pair in confidence_return_pairs]
    return {
        "decisions": len(rows),
        "fills": len(confidence_pnl_pairs),
        "next_return_samples": len(confidence_return_pairs),
        "pearson_confidence_realized_pnl": pearson(pnl_xs, pnl_ys),
        "spearman_confidence_realized_pnl": spearman(pnl_xs, pnl_ys),
        "pearson_confidence_next_return": pearson(return_xs, return_ys),
        "spearman_confidence_next_return": spearman(return_xs, return_ys),
    }


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index + 1
        while end < len(indexed) and indexed[end][1] == indexed[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for original_index, _ in indexed[index:end]:
            ranks[original_index] = average_rank
        index = end
    return ranks


def _write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str] | None = None) -> None:
    fieldnames = fieldnames or (list(rows[0].keys()) if rows else [])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _average(values: list[float]) -> float:
    return _finite(mean(values)) if values else 0.0


def _std(values: list[float]) -> float:
    return _finite(pstdev(values)) if len(values) > 1 else 0.0


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _finite(value: Any) -> float:
    number = _optional_float(value)
    return number if number is not None else 0.0


if __name__ == "__main__":
    main()
