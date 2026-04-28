# Reproducibility

NeuraTradeBench aims to make each experiment traceable from configuration to report.

## Fixed Seeds

Use fixed seeds for any stochastic model sampling, synthetic price generation, randomized decisions, or chart generation. Ollama requests should use deterministic options where possible, such as temperature `0`.

## Config Files

Store the complete experiment configuration with each run. Include model names and versions, prompt settings, price source, symbol, starting balances, fee assumptions, risk settings, slippage settings, latency settings, and output paths.

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
