#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/demo"
if [[ -z "${PYTHON_BIN:-}" && -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

mkdir -p "$ARTIFACT_DIR"
export MPLCONFIGDIR="$ARTIFACT_DIR/.matplotlib"
mkdir -p "$MPLCONFIGDIR"

cd "$ROOT_DIR/backend"

"$PYTHON_BIN" - <<'PY'
import json
import math
import random
from pathlib import Path

from experiments.ablation import AblationConfig, run_ablation
from experiments.compare_models import ModelComparisonConfig, compare_models
from reports.generate_report import generate_markdown_report
from reports.plots import plot_ablation_results, plot_model_comparison
from services.prompting import PROMPT_VERSION

artifact_dir = Path("../artifacts/demo")
artifact_dir.mkdir(parents=True, exist_ok=True)

SEED = 42
PRICE_POINTS = 1_440
STATISTICS_RESAMPLES = 500
PERIODS_PER_YEAR = 1


def synthetic_btc_prices(points: int = PRICE_POINTS, start: float = 65_000.0) -> list[float]:
    rng = random.Random(SEED)
    price = start
    prices = []
    for index in range(points):
        regime = index / points
        if regime < 0.34:
            drift = 0.00011
        elif regime < 0.67:
            drift = -0.00009
        else:
            drift = 0.00001
        cycle = 0.00065 * math.sin(index / 18) + 0.00035 * math.sin(index / 57)
        noise = rng.gauss(0.0, 0.00045)
        price = max(1.0, price * (1 + drift + cycle + noise))
        prices.append(round(price, 2))
    return prices


def moving_average(values: list[float], end: int, window: int) -> float:
    start = max(0, end + 1 - window)
    segment = values[start : end + 1]
    return sum(segment) / len(segment)


def model_decisions(
    prices: list[float],
    *,
    fast: int,
    slow: int,
    buy_threshold: float,
    sell_threshold: float,
    size: float,
    confidence: float,
) -> list[dict[str, float | str]]:
    decisions = []
    in_position = False
    for index, _price in enumerate(prices):
        if index < slow:
            decisions.append(_decision("HOLD", 0.0, confidence - 0.12))
            continue
        fast_ma = moving_average(prices, index, fast)
        slow_ma = moving_average(prices, index, slow)
        momentum = fast_ma / slow_ma - 1
        if momentum > buy_threshold and not in_position:
            in_position = True
            decisions.append(_decision("BUY", size, confidence))
        elif momentum < -sell_threshold and in_position:
            in_position = False
            decisions.append(_decision("SELL", 1.0, confidence - 0.04))
        else:
            decisions.append(_decision("HOLD", 0.0, confidence - 0.16))
    if in_position:
        decisions[-1] = _decision("SELL", 1.0, confidence - 0.02)
    return decisions


def _decision(action: str, size: float, confidence: float) -> dict[str, float | str]:
    return {
        "action": action,
        "confidence": max(0.0, min(1.0, confidence)),
        "position_size_pct": size,
        "reasoning": f"Deterministic {action} signal for the reproducible paper demo.",
        "stop_loss": 0.02,
        "take_profit": 0.04,
    }


prices = synthetic_btc_prices()
mocked_decisions = {
    "qwen2.5:7b": model_decisions(
        prices,
        fast=9,
        slow=34,
        buy_threshold=0.0016,
        sell_threshold=0.0011,
        size=0.22,
        confidence=0.82,
    ),
    "llama3.1:8b": model_decisions(
        prices,
        fast=12,
        slow=48,
        buy_threshold=0.0022,
        sell_threshold=0.0014,
        size=0.18,
        confidence=0.74,
    ),
    "gemma2:2b": model_decisions(
        prices,
        fast=18,
        slow=72,
        buy_threshold=0.0028,
        sell_threshold=0.0017,
        size=0.14,
        confidence=0.66,
    ),
}

comparison = compare_models(
    ModelComparisonConfig(
        models=list(mocked_decisions),
        prices=prices,
        mocked_decisions_by_model=mocked_decisions,
        output_csv_path=str(artifact_dir / "model_comparison.csv"),
        fee_bps=10.0,
        spread_bps=5.0,
        volatility=0.01,
        latency_ms=25,
        periods_per_year=PERIODS_PER_YEAR,
        statistics_resamples=STATISTICS_RESAMPLES,
    )
)

decisions = mocked_decisions["qwen2.5:7b"]
ablation = run_ablation(
    AblationConfig(
        prices=prices,
        decisions=decisions,
        output_dir=str(artifact_dir),
        fee_bps=10.0,
        spread_bps=5.0,
        volatility=0.01,
        latency_ms=25,
        periods_per_year=PERIODS_PER_YEAR,
    )
)

(artifact_dir / "experiment_config.json").write_text(
    json.dumps(
        {
            "experiment": "paper-demo",
            "seed": 42,
            "prompt_version": PROMPT_VERSION,
            "models": list(mocked_decisions),
            "baselines": ["random", "buy_and_hold", "ema_crossover", "always_hold"],
            "price_source": "deterministic_synthetic_btc_1m_multi_regime",
            "price_points": len(prices),
            "price_window_minutes": len(prices),
            "periods_per_year": PERIODS_PER_YEAR,
            "risk_adjusted_metric_scale": "non_annualized_demo",
            "statistics_resamples": STATISTICS_RESAMPLES,
            "comparison_csv": comparison.csv_path,
            "ablation_csv": ablation.csv_path,
        },
        indent=2,
        sort_keys=True,
    ),
    encoding="utf-8",
)

plot_model_comparison(artifact_dir / "model_comparison.csv", artifact_dir / "model_sharpe.png")
plot_ablation_results(artifact_dir / "ablation_results.csv", artifact_dir / "ablation_sharpe.png")
generate_markdown_report(experiment_id=1, output_md=artifact_dir / "report.md")

print(f"Wrote demo artifacts to {artifact_dir}")
PY
