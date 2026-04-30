# Reproducibility

NeuraTradeBench aims to make each experiment traceable from configuration to report.

## Fixed Seeds

Use fixed seeds for any stochastic model sampling, synthetic price generation, randomized decisions, or chart generation. Ollama requests should use deterministic options where possible, such as temperature `0`.

## Config Files

Store the complete experiment configuration with each run. Include model names and versions, prompt settings, price source, symbol, starting balances, fee assumptions, risk settings, slippage settings, latency settings, and output paths.

Use exact model tags where possible, such as `qwen2.5:7b-instruct-q4_K_M`, and record the Ollama version in the experiment metadata. The bundled metadata writer captures local hardware and `ollama --version` output when available.

## Price Windows

Risk-adjusted metrics need enough observations to be meaningful. Use at least 1,000 matched price points for benchmark claims, and prefer 30 or more days of historical BTC data when preparing publication tables. The network-free `make reproduce` demo uses a deterministic 1,440-point synthetic BTC minute window with non-annualized demo risk metrics so reviewers can validate the artifact pipeline without external services.

## CSV Outputs

Model comparisons and ablations should write CSV artifacts such as `model_comparison.csv` and `ablation_results.csv`. CSV files are the primary tabular record used for ranking, analysis, and report generation.

## Logs

Preserve inference logs, risk events, simulated fills, metric snapshots, and any model errors. Logs make it possible to inspect why a run produced a particular equity curve or trade sequence.

## CI Tests

Run the local test suite before publishing results:

```bash
scripts/lint.sh
scripts/test.sh
```

The GitHub Actions CI workflow runs linting, type checks, tests, and coverage so documentation and reports can reference a known validation baseline.

## Report Generation

Generate Markdown reports from the artifact directory:

```bash
cd backend
python - <<'PY'
from reports.generate_report import generate_markdown_report

generate_markdown_report(1, "../artifacts/report.md")
PY
```

Keep the report beside its source CSV, JSON, chart, and config artifacts so the result can be regenerated and audited.
