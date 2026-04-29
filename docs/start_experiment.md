# Start A Paper-Trading Research Experiment

This runbook starts a NeuraTradeBench paper-trading experiment for BTCUSDT. It never places real exchange orders. All fills are simulated, and every artifact should be treated as research data only after the checks below pass.

## 1. Environment Checklist

Use Python 3.12. The pinned backend dependencies are not compatible with Python 3.14.

```bash
cd /Users/skb/Documents/NeuraPlay/neuratrade
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
```

Confirm Ollama is running and a model is pulled:

```bash
ollama serve
ollama pull qwen2.5:7b
ollama list
```

If `qwen2.5:7b` is too slow on local hardware, use a smaller pulled model for the first smoke run, then switch back to the paper model lineup before collecting research data.

Confirm the codebase is green before starting:

```bash
scripts/lint.sh
scripts/test.sh
```

## 2. Configure The Run

Create or update `.env` in the repo root or `backend/.env`:

```env
DRY_RUN=true
OLLAMA_URL=http://127.0.0.1:11434
LLM_MODEL=qwen2.5:7b
DB_PATH=/Users/skb/Documents/NeuraPlay/neuratrade/backend/research_production.db
SYMBOL=BTCUSDT
CYCLE_INTERVAL_SECONDS=60
MAX_CYCLES=10
ARTIFACT_DIR=/Users/skb/Documents/NeuraPlay/neuratrade/artifacts/live
```

Important guardrails:

- Keep `DRY_RUN=true`.
- Do not add exchange API keys.
- Do not use `scripts/paper_demo.sh` as research evidence; it is synthetic demo output only.
- Use `MAX_CYCLES=10` for the first smoke test. For collection, remove `MAX_CYCLES` or set a large supervised value.

## 3. Start The Experiment

From the repo root:

```bash
source backend/.venv/bin/activate
make run
```

Or explicitly:

```bash
source backend/.venv/bin/activate
LLM_MODEL=qwen2.5:7b \
MAX_CYCLES=10 \
CYCLE_INTERVAL_SECONDS=60 \
ARTIFACT_DIR=/Users/skb/Documents/NeuraPlay/neuratrade/artifacts/live \
scripts/start_experiment.sh
```

The script checks:

- `DRY_RUN=true`
- Ollama is installed
- The selected model is pulled
- The run can write `experiment_start.json`

## 4. Expected Outputs

After startup, check:

```bash
ls -la artifacts/live
cat artifacts/live/experiment_start.json
```

The SQLite DB should contain research tables such as:

- `experiments`
- `model_runs`
- `market_ticks`
- `cycle_indicators`
- `prompt_templates`
- `inference_logs`
- `llm_hallucinations`
- `execution_fills`
- `metric_snapshots`

Quick DB sanity check:

```bash
sqlite3 backend/research_production.db "
SELECT COUNT(*) AS ticks FROM market_ticks;
SELECT COUNT(*) AS inferences FROM inference_logs;
SELECT COUNT(*) AS gaps FROM market_ticks WHERE data_gap = 1;
SELECT COUNT(*) AS hallucinations FROM llm_hallucinations;
"
```

## 5. Data Integrity Manifest

If you download historical OHLCV, tick, funding, or order-book files into `data/`, generate the manifest:

```bash
scripts/validate_data_integrity.sh data data/manifest.sha256
cat data/manifest.sha256
```

Commit the manifest with the exact dataset used for research so reviewers can verify file identity.

## 6. Research Collection Gate

Only begin a long run after all of these are true:

- `scripts/lint.sh` passes.
- `scripts/test.sh` passes.
- The smoke run writes valid `experiment_start.json`.
- Binance market data is reachable from the machine.
- Ollama inference latency fits inside the configured cycle interval.
- Data-gap percentage is acceptable for the run window.
- `market_ticks.validation_status` is mostly `valid`.
- `DRY_RUN=true` is confirmed in both config and artifacts.

Minimum research target from the gap analysis:

- 7 continuous days per model minimum.
- 30 continuous days recommended.
- 500+ completed simulated trades per model where feasible.
- Baselines must use the identical time window and fee/slippage assumptions.

## 7. Stop And Resume

Stop a supervised run with `Ctrl-C`. The runner finalizes the model run status in the DB.

Before resuming, archive or rename the previous artifact directory if you want a clean run:

```bash
mv artifacts/live artifacts/live_$(date +%Y%m%d_%H%M%S)
mkdir -p artifacts/live
```

Then restart with `make run`.

## 8. What Not To Cite

Do not cite:

- `artifacts/demo/*`
- outputs from `scripts/paper_demo.sh`
- runs with mocked prices or mocked decisions
- runs where `data_gap` is high or unreported
- runs where metrics cannot be traced back to DB rows

Only cite results generated from validated live Binance data or hash-verified historical data, with matching baselines and full metadata.
