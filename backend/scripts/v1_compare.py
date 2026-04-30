"""
Run a V1 same-price-sequence comparison with baselines.

This script loads real BTC prices from SQLite candles, obtains/checkpoints one
decision per model per price, and feeds those decisions into compare_models.

Run from backend/:
    python scripts/v1_compare.py --max-points 1440
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import DB_PATH  # noqa: E402

from experiments.compare_models import ModelComparisonConfig, compare_models  # noqa: E402
from services.ollama_client import OllamaClient  # noqa: E402

V1_MODELS = [
    "qwen2.5:7b",
    "llama3.1:8b",
    "gemma2:2b",
    "mistral:7b",
    "phi3:mini",
]
DEFAULT_OUTPUT_DIR = Path("../artifacts/v1")
DEFAULT_MAX_POINTS = 10_080
PERIODS_PER_YEAR = 525_600


def load_price_series(db_path: str | Path, *, max_points: int) -> list[float]:
    query = """
        SELECT close
        FROM candles
        WHERE close IS NOT NULL AND close > 0
        ORDER BY ts DESC
        LIMIT ?
    """
    with sqlite3.connect(db_path) as connection:
        prices = [float(row[0]) for row in connection.execute(query, (max_points,)).fetchall()]
    prices.reverse()
    if len(prices) < max_points:
        raise RuntimeError(
            f"Only {len(prices)} usable candle closes found; need {max_points}. "
            "Run `make prefill` or lower --max-points."
        )
    return prices


def collect_model_decisions(
    *,
    model: str,
    prices: list[float],
    checkpoint_dir: Path,
    fallback_on_error: bool,
) -> list[dict[str, Any]]:
    checkpoint_path = checkpoint_dir / f"{_slug(model)}_decisions.jsonl"
    decisions = load_checkpointed_decisions(checkpoint_path, expected_prices=prices)
    if len(decisions) >= len(prices):
        print(f"{model}: checkpoint complete ({len(prices)} decisions).")
        return decisions

    print(f"{model}: resuming at decision {len(decisions) + 1}/{len(prices)}.")
    client = OllamaClient(model=model)
    for index in range(len(decisions), len(prices)):
        decision = client.decide(
            _decision_prompt(index=index, price=prices[index]), fallback_on_error=fallback_on_error
        )
        decision_data = decision.model_dump()
        append_checkpoint_decision(checkpoint_path, index=index, price=prices[index], decision=decision_data)
        decisions.append(decision_data)
        if (index + 1) % 100 == 0 or index + 1 == len(prices):
            print(f"{model}: {index + 1}/{len(prices)} decisions", end="\r")
    print()
    return decisions


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
                rows_by_index[index] = dict(row["decision"])

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare V1 Ollama models on the same DB price sequence.")
    parser.add_argument("--db-path", default=DB_PATH, help="SQLite DB path. Defaults to config.DB_PATH.")
    parser.add_argument("--models", nargs="+", default=V1_MODELS, help="Ollama models to compare.")
    parser.add_argument("--max-points", type=int, default=DEFAULT_MAX_POINTS, help="Number of candle closes to replay.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for artifacts.")
    parser.add_argument("--seed", type=int, default=42, help="Seed used by baselines/statistics.")
    parser.add_argument("--statistics-resamples", type=int, default=1000, help="Bootstrap resamples.")
    parser.add_argument(
        "--fallback-on-error",
        action="store_true",
        help="Use Ollama fallback HOLD decisions when a model call fails.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prices = load_price_series(args.db_path, max_points=args.max_points)
    checkpoint_dir = output_dir / "checkpoints"
    mocked_decisions = {
        model: collect_model_decisions(
            model=model,
            prices=prices,
            checkpoint_dir=checkpoint_dir,
            fallback_on_error=args.fallback_on_error,
        )
        for model in args.models
    }
    result = compare_models(
        ModelComparisonConfig(
            models=args.models,
            prices=prices,
            mocked_decisions_by_model=mocked_decisions,
            output_csv_path=str(output_dir / "model_comparison.csv"),
            include_baselines=True,
            seed=args.seed,
            statistics_resamples=args.statistics_resamples,
            periods_per_year=PERIODS_PER_YEAR,
        )
    )
    (output_dir / "model_comparison.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(result.model_dump_json(indent=2))
    print(f"Artifacts written to: {output_dir.resolve()}")


def _decision_prompt(*, index: int, price: float) -> str:
    return (
        "Return strict JSON only for a BTCUSDT paper-trading decision. "
        f"tick={index} price={price:.2f}. "
        "Fields: action, confidence, position_size_pct, reasoning, stop_loss, take_profit."
    )


def _same_price(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-8)


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_").lower()


if __name__ == "__main__":
    main()
