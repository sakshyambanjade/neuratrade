"""
Run the full 90-day research pipeline from pre-filled Binance candles.

The expensive LLM replay is checkpointed per model. If a run stops after 200
decisions, the next run resumes at decision 201 and continues to the target.

Run from backend/:
    python scripts/run_90d_experiment.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db import models  # noqa: E402
from db.database import SessionLocal, init_db  # noqa: E402
from experiments.ablation import AblationConfig, run_ablation  # noqa: E402
from experiments.baselines import BaselineConfig, run_baselines  # noqa: E402
from experiments.compare_models import ModelComparisonConfig, compare_models  # noqa: E402
from reports.generate_report import generate_markdown_report  # noqa: E402
from reports.plots import plot_ablation_results, plot_model_comparison  # noqa: E402
from services.ollama_client import OllamaClient  # noqa: E402

OUTPUT_DIR = Path("../artifacts/90d_real")
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"
MODELS = ["qwen2.5:7b", "llama3.1:8b", "gemma2:2b"]
SEED = 42
TARGET_POINTS = 129_600
ABLATION_POINTS = 10_080
PERIODS_PER_YEAR = 525_600


def load_price_series(*, target_points: int = TARGET_POINTS) -> list[float]:
    with SessionLocal() as db:
        candles = db.query(models.Candle).order_by(models.Candle.ts.desc()).limit(target_points).all()
    candles = list(reversed(candles))
    prices = [float(candle.close) for candle in candles if candle.close is not None and candle.close > 0]
    if len(prices) < target_points:
        raise RuntimeError(
            f"Only {len(prices)} usable candles in DB; need {target_points}. "
            "Run `make prefill` first and rerun until the target is complete."
        )
    gaps = _count_minute_gaps([int(candle.ts) for candle in candles])
    if gaps:
        print(f"WARNING: found {gaps} one-minute timestamp gap(s) in the selected DB window.")
    print(f"Loaded {len(prices)} price points from database.")
    return prices


def run_model_comparison(prices: list[float], *, model_names: list[str]) -> None:
    print("\n--- Running checkpointed model comparison ---")
    mocked_decisions = {model: collect_model_decisions(model=model, prices=prices) for model in model_names}
    result = compare_models(
        ModelComparisonConfig(
            models=model_names,
            prices=prices,
            mocked_decisions_by_model=mocked_decisions,
            output_csv_path=str(OUTPUT_DIR / "model_comparison.csv"),
            seed=SEED,
            periods_per_year=PERIODS_PER_YEAR,
        )
    )
    best = result.ranked_models[0] if result.ranked_models else "N/A"
    print(f"Best model by Sharpe: {best}")
    (OUTPUT_DIR / "model_comparison.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")


def collect_model_decisions(*, model: str, prices: list[float]) -> list[dict[str, Any]]:
    checkpoint_path = decision_checkpoint_path(model)
    decisions = load_checkpointed_decisions(checkpoint_path, expected_prices=prices)
    start_index = len(decisions)
    if start_index >= len(prices):
        print(f"{model}: checkpoint complete ({len(prices)} decisions).")
        return decisions

    print(f"{model}: resuming at decision {start_index + 1}/{len(prices)}.")
    client = OllamaClient(model=model)
    for index in range(start_index, len(prices)):
        decision = client.decide(_decision_prompt(index=index, price=prices[index]), fallback_on_error=True)
        decision_data = decision.model_dump()
        append_checkpoint_decision(
            checkpoint_path,
            index=index,
            price=prices[index],
            decision=decision_data,
        )
        decisions.append(decision_data)
        if (index + 1) % 100 == 0 or index + 1 == len(prices):
            print(f"{model}: {index + 1}/{len(prices)} decisions", end="\r")
    print()
    return decisions


def run_ablation_study(prices: list[float], *, model_names: list[str]) -> None:
    print("\n--- Running ablation study ---")
    ablation_prices = prices[: min(ABLATION_POINTS, len(prices))]
    primary_model = model_names[0]
    decisions = load_checkpointed_decisions(
        decision_checkpoint_path(primary_model),
        expected_prices=prices,
    )[: len(ablation_prices)]
    if len(decisions) < len(ablation_prices):
        raise RuntimeError(f"{primary_model} checkpoint is incomplete; run model comparison first.")

    result = run_ablation(
        AblationConfig(
            prices=ablation_prices,
            decisions=decisions,
            output_dir=str(OUTPUT_DIR),
            periods_per_year=PERIODS_PER_YEAR,
        )
    )
    print(f"Ablation variants completed: {len(result.variants)}")


def run_baseline_comparison(prices: list[float]) -> None:
    print("\n--- Running baseline comparison ---")
    results = run_baselines(
        BaselineConfig(
            prices=prices,
            seed=SEED,
            periods_per_year=PERIODS_PER_YEAR,
        )
    )
    summary = {
        row.name: {
            "return": row.result.cumulative_return,
            "sharpe": row.result.sharpe,
            "max_drawdown": row.result.max_drawdown,
            "ticks": row.result.ticks,
        }
        for row in results
    }
    (OUTPUT_DIR / "baselines.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Baselines: {', '.join(summary)}")


def generate_report() -> None:
    print("\n--- Generating research report ---")
    output_path = OUTPUT_DIR / "report.md"
    generate_markdown_report(1, output_path)
    print(f"Report written to {output_path}")


def generate_charts() -> None:
    model_csv = OUTPUT_DIR / "model_comparison.csv"
    ablation_csv = OUTPUT_DIR / "ablation_results.csv"
    if model_csv.exists():
        plot_model_comparison(model_csv, OUTPUT_DIR / "model_sharpe.png")
    if ablation_csv.exists():
        plot_ablation_results(ablation_csv, OUTPUT_DIR / "ablation_sharpe.png")


def load_checkpointed_decisions(path: Path, *, expected_prices: list[float]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows_by_index: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            index = int(row["index"])
            if 0 <= index < len(expected_prices) and _same_price(float(row["price"]), expected_prices[index]):
                rows_by_index[index] = row["decision"]

    decisions = []
    for index in range(len(expected_prices)):
        decision = rows_by_index.get(index)
        if decision is None:
            break
        decisions.append(decision)
    return decisions


def append_checkpoint_decision(path: Path, *, index: int, price: float, decision: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "index": index,
                    "price": price,
                    "decision": decision,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )


def decision_checkpoint_path(model: str) -> Path:
    return CHECKPOINT_DIR / f"{_slug(model)}_decisions.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the 90-day NeuraTradeBench research pipeline.")
    parser.add_argument("--max-points", type=int, default=TARGET_POINTS, help="Number of DB price points to replay.")
    parser.add_argument("--models", nargs="+", default=MODELS, help="Ollama model names to compare.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

    prices = load_price_series(target_points=args.max_points)
    run_model_comparison(prices, model_names=args.models)
    run_ablation_study(prices, model_names=args.models)
    run_baseline_comparison(prices)
    generate_charts()
    generate_report()

    print("\n=== DONE ===")
    print(f"All artifacts in: {OUTPUT_DIR.resolve()}")
    print("Run: cat ../artifacts/90d_real/report.md")


def _decision_prompt(*, index: int, price: float) -> str:
    return (
        "Return strict JSON only for a BTCUSDT paper-trading decision. "
        f"tick={index} price={price:.2f}. "
        "Fields: action, confidence, position_size_pct, reasoning, stop_loss, take_profit."
    )


def _count_minute_gaps(timestamps: list[int]) -> int:
    return sum(1 for left, right in zip(timestamps, timestamps[1:], strict=False) if right - left != 60)


def _same_price(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-8)


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_").lower()


if __name__ == "__main__":
    main()
