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
import json
import os
import platform
import socket
import sqlite3
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import urlopen

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import DB_PATH, OLLAMA_URL, SYMBOL  # noqa: E402

from experiments.run_live import LiveExperimentRunner, LiveRunConfig  # noqa: E402

V1_MODELS = [
    "qwen2.5:7b",
    "llama3.1:8b",
    "gemma2:2b",
    "mistral:7b",
    "phi3:mini",
]
DEFAULT_MAX_CYCLES = 10_080
DEFAULT_MIN_PREFILL_CANDLES = 129_600
BINANCE_PREFLIGHT_HOSTS = ("stream.binance.com", "api.binance.com")


class PreflightError(RuntimeError):
    pass


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


def run_preflight(models: list[str], args: argparse.Namespace) -> None:
    print("Preflight: V1 paper-trading safety checks")

    if args.skip_prefill_check:
        print("Preflight: candle prefill check skipped")
    else:
        candles = candle_count(args.db_path)
        if candles < args.min_prefill_candles:
            raise PreflightError(
                f"Only {candles} candle(s) found in {args.db_path}; need at least {args.min_prefill_candles}. "
                "Run `make prefill` before collecting V1 research data."
            )
        print(f"Preflight: candle history OK ({candles} candles)")

    if args.skip_ollama_preflight:
        print("Preflight: Ollama check skipped")
    else:
        available_models = fetch_ollama_models(args.ollama_url, timeout=args.ollama_timeout)
        missing = missing_ollama_models(available_models, models)
        if missing:
            commands = " && ".join(f"ollama pull {model}" for model in missing)
            raise PreflightError(f"Missing Ollama model(s): {', '.join(missing)}. Run: {commands}")
        print(f"Preflight: Ollama OK ({', '.join(models)})")

    if args.skip_market_preflight:
        print("Preflight: Binance DNS check skipped")
    else:
        check_binance_dns()
        print("Preflight: Binance DNS OK")

    print("Preflight: complete; starting live runner")


def candle_count(db_path: str | Path) -> int:
    path = Path(db_path)
    if not path.exists():
        return 0
    try:
        with sqlite3.connect(path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM candles WHERE close IS NOT NULL AND close > 0").fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0]) if row else 0


def fetch_ollama_models(ollama_url: str, *, timeout: float) -> set[str]:
    tags_url = urljoin(ollama_url.rstrip("/") + "/", "api/tags")
    try:
        with urlopen(tags_url, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise PreflightError(
            f"Cannot reach Ollama at {ollama_url}. Start it with `ollama serve`. Error: {exc}"
        ) from exc
    return {str(row.get("name", "")) for row in payload.get("models", []) if isinstance(row, dict)}


def missing_ollama_models(available_models: set[str], requested_models: list[str]) -> list[str]:
    return [model for model in requested_models if model not in available_models]


def check_binance_dns(hosts: tuple[str, ...] = BINANCE_PREFLIGHT_HOSTS) -> None:
    for host in hosts:
        try:
            socket.getaddrinfo(host, 443)
        except OSError as exc:
            raise PreflightError(
                f"Cannot resolve {host}. Check DNS/network/VPN before starting the live feed."
            ) from exc


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
    parser.add_argument("--db-path", default=DB_PATH, help="SQLite DB path used for the candle prefill check.")
    parser.add_argument("--ollama-url", default=OLLAMA_URL, help="Ollama base URL used for model preflight.")
    parser.add_argument("--ollama-timeout", type=float, default=5.0, help="Seconds to wait for Ollama preflight.")
    parser.add_argument(
        "--min-prefill-candles",
        type=int,
        default=int(os.getenv("V1_MIN_PREFILL_CANDLES", DEFAULT_MIN_PREFILL_CANDLES)),
        help="Minimum warm candle count required before a V1 run starts.",
    )
    parser.add_argument("--skip-prefill-check", action="store_true", help="Bypass the candle-history preflight.")
    parser.add_argument("--skip-ollama-preflight", action="store_true", help="Bypass the Ollama server/model check.")
    parser.add_argument("--skip-market-preflight", action="store_true", help="Bypass the Binance DNS check.")
    parser.add_argument("--preflight-only", action="store_true", help="Run checks and exit without starting cycles.")
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
    models = selected_models(args)
    try:
        run_preflight(models, args)
    except PreflightError as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if args.preflight_only:
        return
    asyncio.run(run_selected_models(models, args))


if __name__ == "__main__":
    main()
