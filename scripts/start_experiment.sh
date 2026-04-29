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

export DB_PATH
export LLM_MODEL="$MODEL"
export LLM_TIMEOUT="${LLM_TIMEOUT:-120}"
export DRY_RUN=true
export PYTHONPATH="$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed or not on PATH." >&2
  exit 1
fi

if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$MODEL"; then
  echo "Model $MODEL is not pulled. Run: ollama pull $MODEL" >&2
  exit 1
fi

echo "Preflight: checking Ollama API and model $MODEL..."
"$PYTHON_BIN" - <<PY
from services.ollama_client import OllamaClient

decision = OllamaClient(model="${MODEL}", timeout=float("${LLM_TIMEOUT:-120}"), retries=1).decide(
    "Return strict JSON only: "
    '{"action":"HOLD","confidence":0.5,"position_size_pct":0,'
    '"reasoning":"Testing structured JSON output for paper trading readiness only",'
    '"stop_loss":0,"take_profit":0}',
    fallback_on_error=False,
)
print(f"Preflight: Ollama structured decision OK ({decision.action}, confidence={decision.confidence})")
PY

if [[ "${SKIP_MARKET_PREFLIGHT:-false}" != "true" ]]; then
  echo "Preflight: checking Binance DNS..."
  if ! "$PYTHON_BIN" - <<'PY'
import socket

for host in ("stream.binance.com", "api.binance.com"):
    socket.getaddrinfo(host, 443)
PY
  then
    echo "Cannot resolve Binance market data hosts. Fix DNS/network/VPN, or set SKIP_MARKET_PREFLIGHT=true for a gap-only diagnostic run." >&2
    exit 1
  fi
  echo "Preflight: Binance DNS OK"
fi

mkdir -p "$ARTIFACT_DIR"

cd "$ROOT_DIR/backend"
"$PYTHON_BIN" - <<PY
import asyncio
from db.database import init_db
from experiments.metadata import write_experiment_start
from experiments.run_live import LiveExperimentRunner, LiveRunConfig
from sqlalchemy import text
from db.database import SessionLocal

print("Preflight: initializing database...")
init_db()
print("Preflight: project runtime OK")

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

print("\\nCycle summary:")
with SessionLocal() as db:
    rows = db.execute(
        text(
            """
            SELECT
                mt.cycle_index,
                mt.validation_status,
                mt.data_gap,
                COALESCE(il.parsed_action, '-') AS action,
                COALESCE(il.success, 0) AS success,
                COALESCE(il.latency_ms, 0) AS latency_ms,
                COALESCE(NULLIF(il.error, ''), '-') AS error,
                COUNT(DISTINCT lh.id) AS hallucinations,
                COUNT(DISTINCT ef.id) AS fills
            FROM market_ticks mt
            LEFT JOIN inference_logs il ON il.market_tick_id = mt.id
            LEFT JOIN llm_hallucinations lh ON lh.inference_log_id = il.id
            LEFT JOIN execution_fills ef ON ef.model_run_id = mt.model_run_id AND ef.timestamp >= il.timestamp
            WHERE mt.model_run_id = :model_run_id
            GROUP BY mt.id, il.id
            ORDER BY mt.cycle_index
            """
        ),
        {"model_run_id": state.model_run_id},
    ).fetchall()

for row in rows:
    print(
        f"cycle={row.cycle_index} validation={row.validation_status} data_gap={row.data_gap} "
        f"action={row.action} success={row.success} latency_ms={row.latency_ms} "
        f"hallucinations={row.hallucinations} fills={row.fills} error={row.error}"
    )
PY
