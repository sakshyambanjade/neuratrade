# Demo Artifacts

Run `scripts/paper_demo.sh` from the repository root to generate the paper-demo bundle in this directory.

Expected generated files:

- `experiment_config.json`
- `model_comparison.csv`
- `model_comparison_statistics.json`
- `ablation_results.csv`
- `ablation_summary.json`
- `model_sharpe.png`
- `ablation_sharpe.png`
- `report.md`

The demo is intentionally mocked and network-free so reviewers can validate the artifact pipeline without Ollama, Binance, wallets, or exchange credentials. It uses a deterministic 1,440-point synthetic BTC minute window, baseline strategies, non-annualized demo risk metrics, bootstrap confidence intervals, and pairwise return tests.
