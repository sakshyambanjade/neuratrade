"""
Run NeuraTradeBench V1 live paper-trading experiments.

Run from backend/:
    python run_v1_experiment.py --model qwen2.5:7b

By default this runs one model for 10,080 one-minute cycles. Use --all-models
--auto-resume for the V1 autopilot: resume unfinished runs, skip completed
models, and switch through the model matrix sequentially.
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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class AutoResumeRun:
    model_name: str
    resume_model_run_id: int | None
    cycles_completed: int
    status: str
    skip: bool = False


async def run_model(model_name: str, args: argparse.Namespace, *, resume_model_run_id: int | None = None) -> None:
    experiment_name = f"{args.experiment_prefix}-{_slug(model_name)}"
    selected_resume_id = (
        resume_model_run_id if resume_model_run_id is not None else getattr(args, "resume_model_run_id", None)
    )
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
        resume_model_run_id=selected_resume_id,
    )
    verb = "Resuming" if selected_resume_id is not None else "Starting"
    suffix = f" from model_run_id={selected_resume_id}" if selected_resume_id is not None else ""
    print(f"{verb} {model_name} as {experiment_name}{suffix}...")
    state = await LiveExperimentRunner(config).start()
    print(
        "Done: "
        f"{model_name} | cycles={state.cycles_completed} "
        f"| experiment_id={state.experiment_id} | model_run_id={state.model_run_id}"
    )


async def run_selected_models(models: list[str], args: argparse.Namespace) -> None:
    if getattr(args, "auto_resume", False):
        for planned in build_auto_resume_plan(models, args):
            if planned.skip:
                print(
                    f"Skipping {planned.model_name}: latest model_run_id={planned.resume_model_run_id} "
                    f"already has {planned.cycles_completed}/{args.max_cycles} cycles."
                )
                continue
            if planned.resume_model_run_id is None:
                print(f"Autopilot: no prior {planned.model_name} run found; starting fresh.")
            else:
                print(
                    f"Autopilot: {planned.model_name} has {planned.cycles_completed}/{args.max_cycles} cycles "
                    f"({planned.status}); resuming model_run_id={planned.resume_model_run_id}."
                )
            await run_model(planned.model_name, args, resume_model_run_id=planned.resume_model_run_id)
        return

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
    resume_group = parser.add_mutually_exclusive_group()
    resume_group.add_argument("--resume-model-run-id", type=int, default=None, help="Resume an existing model_runs.id.")
    resume_group.add_argument(
        "--resume-latest",
        action="store_true",
        help="Resume the latest model run matching --model and --experiment-prefix.",
    )
    parser.add_argument(
        "--auto-resume",
        action="store_true",
        help=(
            "For --all-models/--models, automatically resume each unfinished model, "
            "skip completed models, and continue through the list."
        ),
    )
    return parser


def selected_models(args: argparse.Namespace) -> list[str]:
    if args.all_models:
        return list(V1_MODELS)
    if args.models:
        return args.models
    return [args.model or os.getenv("LLM_MODEL") or V1_MODELS[0]]


def resolve_resume_args(args: argparse.Namespace, models: list[str]) -> list[str]:
    if getattr(args, "auto_resume", False):
        if args.resume_model_run_id is not None or args.resume_latest:
            raise PreflightError("--auto-resume cannot be combined with --resume-model-run-id or --resume-latest.")
        return models
    if args.resume_model_run_id is None and not args.resume_latest:
        return models
    if args.all_models or args.models or len(models) != 1:
        raise PreflightError(
            "Resume mode supports exactly one model. Use --model with --resume-latest or --resume-model-run-id."
        )
    if args.resume_latest:
        args.resume_model_run_id = latest_model_run_id(
            args.db_path,
            model_name=models[0],
            experiment_prefix=args.experiment_prefix,
        )
    resume_model = model_name_for_model_run(args.db_path, args.resume_model_run_id)
    if resume_model != models[0]:
        if args.model is not None:
            raise PreflightError(
                f"Cannot resume model_run_id={args.resume_model_run_id}: DB model is {resume_model!r}, "
                f"but --model is {models[0]!r}."
            )
        return [resume_model]
    return models


def model_name_for_model_run(db_path: str | Path, model_run_id: int | None) -> str:
    if model_run_id is None:
        raise PreflightError("No model run id was provided for resume.")
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute("SELECT model_name FROM model_runs WHERE id = ?", (model_run_id,)).fetchone()
    except sqlite3.Error as exc:
        raise PreflightError(f"Cannot inspect model run {model_run_id} in {db_path}: {exc}") from exc
    if row is None:
        raise PreflightError(f"model_run_id={model_run_id} was not found in {db_path}.")
    return str(row[0])


def latest_model_run_id(db_path: str | Path, *, model_name: str, experiment_prefix: str) -> int:
    summary = latest_model_run_summary(db_path, model_name=model_name, experiment_prefix=experiment_prefix)
    if summary is None:
        raise PreflightError(f"No prior model run found for model={model_name!r} and prefix={experiment_prefix!r}.")
    return int(summary["id"])


def latest_model_run_summary(
    db_path: str | Path,
    *,
    model_name: str,
    experiment_prefix: str,
) -> dict[str, int | str] | None:
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                """
                SELECT mr.id, mr.status
                FROM model_runs mr
                JOIN experiments e ON e.id = mr.experiment_id
                WHERE mr.model_name = ? AND e.name LIKE ?
                ORDER BY mr.id DESC
                LIMIT 1
                """,
                (model_name, f"{experiment_prefix}-%"),
            ).fetchone()
            if row is None:
                return None
            cycles_row = connection.execute(
                "SELECT COALESCE(MAX(cycle_index) + 1, 0) FROM market_ticks WHERE model_run_id = ?",
                (int(row[0]),),
            ).fetchone()
    except sqlite3.Error as exc:
        raise PreflightError(f"Cannot inspect latest model run in {db_path}: {exc}") from exc
    return {
        "id": int(row[0]),
        "status": str(row[1]),
        "cycles_completed": int(cycles_row[0]) if cycles_row else 0,
    }


def build_auto_resume_plan(models: list[str], args: argparse.Namespace) -> list[AutoResumeRun]:
    plan: list[AutoResumeRun] = []
    for model_name in models:
        summary = latest_model_run_summary(
            args.db_path,
            model_name=model_name,
            experiment_prefix=args.experiment_prefix,
        )
        if summary is None:
            plan.append(
                AutoResumeRun(
                    model_name=model_name,
                    resume_model_run_id=None,
                    cycles_completed=0,
                    status="new",
                )
            )
            continue
        cycles_completed = int(summary["cycles_completed"])
        skip = args.max_cycles is not None and cycles_completed >= args.max_cycles
        plan.append(
            AutoResumeRun(
                model_name=model_name,
                resume_model_run_id=int(summary["id"]),
                cycles_completed=cycles_completed,
                status=str(summary["status"]),
                skip=skip,
            )
        )
    return plan


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-").lower()


def main() -> None:
    args = build_parser().parse_args()
    models = selected_models(args)
    try:
        models = resolve_resume_args(args, models)
        run_preflight(models, args)
    except PreflightError as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if args.preflight_only:
        return
    asyncio.run(run_selected_models(models, args))


if __name__ == "__main__":
    main()
