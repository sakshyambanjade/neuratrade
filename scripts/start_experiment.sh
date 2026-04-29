#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL="${LLM_MODEL:-${1:-llama3.2:1b}}"
ARTIFACT_DIR="${ARTIFACT_DIR:-$ROOT_DIR/artifacts/live}"
MAX_CYCLES="${MAX_CYCLES:-10}"
CYCLE_INTERVAL_SECONDS="${CYCLE_INTERVAL_SECONDS:-60}"
DB_PATH="${DB_PATH:-$ROOT_DIR/backend/trading.db}"
if [[ -z "${PYTHON_BIN:-}" && -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

if [[ -f "$ROOT_DIR/backend/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/backend/.env"
  set +a
fi

if [[ "${DRY_RUN:-true}" != "true" ]]; then
  echo "Refusing to start: DRY_RUN must remain true for paper-trading research." >&2
  exit 1
fi

case "$ARTIFACT_DIR" in
  /*) ;;
  *) ARTIFACT_DIR="$ROOT_DIR/$ARTIFACT_DIR" ;;
esac

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed or not on PATH." >&2
  exit 1
fi

if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$MODEL"; then
  echo "Model $MODEL is not pulled. Run: ollama pull $MODEL" >&2
  exit 1
fi

if [[ "${SKIP_MARKET_PREFLIGHT:-false}" != "true" ]]; then
  if ! "$PYTHON_BIN" - <<'PY'
import socket

for host in ("stream.binance.com", "api.binance.com"):
    socket.getaddrinfo(host, 443)
PY
  then
    echo "Cannot resolve Binance market data hosts. Fix DNS/network/VPN, or set SKIP_MARKET_PREFLIGHT=true for a gap-only diagnostic run." >&2
    exit 1
  fi
fi

mkdir -p "$ARTIFACT_DIR"
export DB_PATH
export LLM_MODEL="$MODEL"
export DRY_RUN=true

cd "$ROOT_DIR/backend"
"$PYTHON_BIN" - <<PY
import asyncio
from experiments.metadata import write_experiment_start
from experiments.run_live import LiveExperimentRunner, LiveRunConfig

config = LiveRunConfig(
    model_name="${MODEL}",
    experiment_name="paper-trading-live",
    cycle_interval_seconds=float("${CYCLE_INTERVAL_SECONDS}"),
    max_cycles=int("${MAX_CYCLES}"),
    dry_run=True,
)
artifact_path = write_experiment_start(config.model_dump(), artifact_dir="${ARTIFACT_DIR}")
print(f"Wrote experiment metadata: {artifact_path}")
state = asyncio.run(LiveExperimentRunner(config).start())
print(state.model_dump_json(indent=2))
PY
