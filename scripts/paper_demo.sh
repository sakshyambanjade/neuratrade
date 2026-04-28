#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/demo"

mkdir -p "$ARTIFACT_DIR"
export MPLCONFIGDIR="$ARTIFACT_DIR/.matplotlib"
mkdir -p "$MPLCONFIGDIR"

cd "$ROOT_DIR/backend"

python - <<'PY'
import json
from pathlib import Path

from experiments.ablation import AblationConfig, run_ablation
from experiments.compare_models import ModelComparisonConfig, compare_models
from reports.generate_report import generate_markdown_report
from reports.plots import plot_ablation_results, plot_model_comparison

artifact_dir = Path("../artifacts/demo")
artifact_dir.mkdir(parents=True, exist_ok=True)

prices = [65000, 65120, 64980, 65340, 65210, 65550, 65480, 65720]
mocked_decisions = {
    "qwen2.5:7b": [
        {"action": "BUY", "confidence": 0.82, "position_size_pct": 0.2},
        "HOLD",
        "HOLD",
        {"action": "SELL", "confidence": 0.76, "position_size_pct": 0.5},
        "HOLD",
        {"action": "BUY", "confidence": 0.81, "position_size_pct": 0.2},
        "HOLD",
        {"action": "SELL", "confidence": 0.78, "position_size_pct": 1.0},
    ],
    "llama3.1:8b": [
        "HOLD",
        {"action": "BUY", "confidence": 0.70, "position_size_pct": 0.2},
        {"action": "SELL", "confidence": 0.64, "position_size_pct": 0.5},
        "HOLD",
        {"action": "BUY", "confidence": 0.68, "position_size_pct": 0.2},
        "HOLD",
        {"action": "SELL", "confidence": 0.66, "position_size_pct": 1.0},
        "HOLD",
    ],
    "gemma2:2b": [
        "HOLD",
        "HOLD",
        "HOLD",
        "HOLD",
        {"action": "BUY", "confidence": 0.61, "position_size_pct": 0.15},
        {"action": "SELL", "confidence": 0.60, "position_size_pct": 1.0},
        "HOLD",
        "HOLD",
    ],
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
    )
)

decisions = [
    {"action": "BUY", "confidence": 0.82, "position_size_pct": 0.2, "stop_loss": 0.02},
    {"action": "HOLD", "confidence": 0.62, "position_size_pct": 0.0, "stop_loss": 0.02},
    {"action": "HOLD", "confidence": 0.58, "position_size_pct": 0.0, "stop_loss": 0.02},
    {"action": "SELL", "confidence": 0.76, "position_size_pct": 0.5, "stop_loss": 0.02},
    {"action": "HOLD", "confidence": 0.55, "position_size_pct": 0.0, "stop_loss": 0.02},
    {"action": "BUY", "confidence": 0.81, "position_size_pct": 0.2, "stop_loss": 0.02},
    {"action": "HOLD", "confidence": 0.63, "position_size_pct": 0.0, "stop_loss": 0.02},
    {"action": "SELL", "confidence": 0.78, "position_size_pct": 1.0, "stop_loss": 0.02},
]
ablation = run_ablation(
    AblationConfig(
        prices=prices,
        decisions=decisions,
        output_dir=str(artifact_dir),
        fee_bps=10.0,
        spread_bps=5.0,
        volatility=0.01,
        latency_ms=25,
    )
)

(artifact_dir / "experiment_config.json").write_text(
    json.dumps(
        {
            "experiment": "paper-demo",
            "seed": 42,
            "prompt_version": "ntb-v1",
            "models": list(mocked_decisions),
            "price_points": len(prices),
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
