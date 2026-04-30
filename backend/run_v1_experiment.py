"""
Run NeuraTradeBench V1 live paper-trading experiments.

Run from backend/:
    python run_v1_experiment.py --model qwen2.5:7b

By default this runs one model for 10,080 one-minute cycles. Use --all-models
or --models to run the V1 matrix sequentially.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import SYMBOL  # noqa: E402

from experiments.run_live import LiveExperimentRunner, LiveRunConfig  # noqa: E402

V1_MODELS = [
    "qwen2.5:7b",
    "llama3.1:8b",
    "gemma2:2b",
    "mistral:7b",
    "phi3:mini",
]
DEFAULT_MAX_CYCLES = 10_080


async def run_model(model_name: str, args: argparse.Namespace) -> None:
    experiment_name = f"{args.experiment_prefix}-{_slug(model_name)}"
    config = LiveRunConfig(
        model_name=model_name,
        symbol=args.symbol,
        experiment_name=experiment_name,
        description=args.description or f"V1 live paper-trading run: {model_name}",
        cycle_interval_seconds=args.cycle_interval_seconds,
        max_cycles=args.max_cycles,
        dry_run=True,
        starting_balance=args.starting_balance,
        starting_btc=args.starting_btc,
        fee_bps=args.fee_bps,
        temperature=args.temperature,
        hardware_tag=args.hardware_tag,
        market_warmup_seconds=args.market_warmup_seconds,
    )
    print(f"Starting {model_name} as {experiment_name}...")
    state = await LiveExperimentRunner(config).start()
    print(
        "Done: "
        f"{model_name} | cycles={state.cycles_completed} "
        f"| experiment_id={state.experiment_id} | model_run_id={state.model_run_id}"
    )


async def run_selected_models(models: list[str], args: argparse.Namespace) -> None:
    for model_name in models:
        await run_model(model_name, args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run V1 live paper-trading experiments against Binance BTCUSDT.")
    model_group = parser.add_mutually_exclusive_group()
    model_group.add_argument("--model", default=None, help="Single Ollama model to run.")
    model_group.add_argument("--models", nargs="+", help="One or more Ollama models to run sequentially.")
    model_group.add_argument("--all-models", action="store_true", help="Run the default V1 model matrix sequentially.")
    parser.add_argument("--symbol", default=SYMBOL, help="Trading symbol; defaults to SYMBOL env or BTCUSDT.")
    parser.add_argument(
        "--experiment-prefix",
        default="v1-live",
        help="Prefix used for experiment names. Model slugs are appended automatically.",
    )
    parser.add_argument("--description", default="", help="Optional experiment description override.")
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=int(os.getenv("V1_MAX_CYCLES", DEFAULT_MAX_CYCLES)),
        help="Number of cycles per model. Default is 10,080, or V1_MAX_CYCLES.",
    )
    parser.add_argument(
        "--cycle-interval-seconds",
        type=float,
        default=float(os.getenv("V1_CYCLE_INTERVAL_SECONDS", "60")),
        help="Seconds between live decision cycles.",
    )
    parser.add_argument("--starting-balance", type=float, default=10_000.0, help="Starting paper USDT balance.")
    parser.add_argument("--starting-btc", type=float, default=0.0, help="Starting paper BTC balance.")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Simulated fee in basis points.")
    parser.add_argument("--temperature", type=float, default=0.0, help="Ollama sampling temperature.")
    parser.add_argument(
        "--hardware-tag",
        default=os.getenv("HARDWARE_TAG", platform.node() or "local"),
        help="Hardware label stored with the model run.",
    )
    parser.add_argument(
        "--market-warmup-seconds",
        type=float,
        default=15.0,
        help="Seconds to wait for the Binance WebSocket snapshot before cycle 1.",
    )
    return parser


def selected_models(args: argparse.Namespace) -> list[str]:
    if args.all_models:
        return list(V1_MODELS)
    if args.models:
        return args.models
    return [args.model or os.getenv("LLM_MODEL") or V1_MODELS[0]]


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-").lower()


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run_selected_models(selected_models(args), args))


if __name__ == "__main__":
    main()
