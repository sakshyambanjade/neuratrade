# NeuraTradeBench Experiment 1

## Experiment Config
```json
{
  "ablation_csv": "../artifacts/demo/ablation_results.csv",
  "baselines": [
    "random",
    "buy_and_hold",
    "ema_crossover",
    "always_hold"
  ],
  "comparison_csv": "../artifacts/demo/model_comparison.csv",
  "experiment": "paper-demo",
  "models": [
    "qwen2.5:7b",
    "llama3.1:8b",
    "gemma2:2b"
  ],
  "periods_per_year": 1,
  "price_points": 1440,
  "price_source": "deterministic_synthetic_btc_1m_multi_regime",
  "price_window_minutes": 1440,
  "prompt_version": "ntb-v2",
  "risk_adjusted_metric_scale": "non_annualized_demo",
  "seed": 42,
  "statistics_resamples": 500
}
```

## Model Leaderboard
| rank | model | return | sharpe | sortino | calmar | max_drawdown | win_rate | profit_factor | avg_latency_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | baseline:ema_crossover | 0.0329 | 0.2071 | 0.0905 | 0.0074 | 0.0030 | 0.8333 | 59.9349 | 25.0000 |
| 2 | qwen2.5:7b | 0.0203 | 0.1534 | 0.0669 | 0.0037 | 0.0038 | 0.6667 | 13.8900 | 25.0000 |
| 3 | llama3.1:8b | 0.0099 | 0.0893 | 0.0449 | 0.0012 | 0.0055 | 0.5000 | 3.6378 | 25.0000 |
| 4 | baseline:random | 0.0026 | 0.0780 | 0.0357 | 0.0032 | 0.0006 | 0.9882 | 18.6096 | 25.0000 |
| 5 | baseline:buy_and_hold | 0.0137 | 0.0148 | 0.0149 | 0.0001 | 0.1058 | 0.0000 | 0.0000 | 25.0000 |
| 6 | gemma2:2b | 0.0010 | 0.0112 | 0.0059 | 0.0001 | 0.0058 | 0.5000 | 1.3791 | 25.0000 |
| 7 | baseline:always_hold | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## Ablation Table
| variant | cumulative_return | sharpe | sortino | calmar | max_drawdown | win_rate | profit_factor | avg_slippage_bps | avg_latency_ms | trade_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_system | 0.0042 | 0.0103 | 0.0108 | 0.0001 | 0.0435 | 0.7500 | 2.9156 | 12.5148 | 25.0000 | 24 |
| no_risk_engine | 0.0326 | 0.1823 | 0.1096 | 0.0052 | 0.0043 | 0.7500 | 20.8742 | 12.5247 | 25.0000 | 24 |
| no_memory | 0.0042 | 0.0103 | 0.0108 | 0.0001 | 0.0435 | 0.7500 | 2.9156 | 12.5148 | 25.0000 | 24 |
| no_news | 0.0042 | 0.0103 | 0.0108 | 0.0001 | 0.0435 | 0.7500 | 2.9156 | 12.5148 | 25.0000 | 24 |
| no_slippage | 0.0083 | 0.0203 | 0.0214 | 0.0001 | 0.0420 | 0.7500 | 3.7180 | 0.0000 | 25.0000 | 24 |
| no_latency | 0.0042 | 0.0103 | 0.0108 | 0.0001 | 0.0435 | 0.7500 | 2.9156 | 12.5148 | 0.0000 | 24 |

## Key Metrics
- `best_sharpe`: `no_risk_engine`
- `highest_return`: `no_risk_engine`
- `lowest_drawdown`: `no_risk_engine`

## Statistical Validation
Bootstrap 95% confidence intervals:

| Model | Return CI | Sharpe CI | Win Rate CI |
| --- | --- | --- | --- |
| baseline:always_hold | [0.0000, 0.0000] | [0.0000, 0.0000] | [0.0000, 0.0000] |
| baseline:buy_and_hold | [-0.0350, 0.0673] | [-0.0377, 0.0692] | [0.0000, 0.0000] |
| baseline:ema_crossover | [0.0245, 0.0410] | [0.1484, 0.2650] | [0.5000, 1.0000] |
| baseline:random | [0.0006, 0.0042] | [0.0139, 0.1456] | [0.9529, 1.0000] |
| gemma2:2b | [-0.0033, 0.0059] | [-0.0384, 0.0673] | [0.1667, 0.8333] |
| llama3.1:8b | [0.0045, 0.0158] | [0.0398, 0.1420] | [0.1667, 0.8333] |
| qwen2.5:7b | [0.0134, 0.0270] | [0.0965, 0.2105] | [0.3333, 1.0000] |

Pairwise tests on matched period returns:

| Left | Right | Test | p | p corrected | Effect | n |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| baseline:ema_crossover | qwen2.5:7b | wilcoxon_signed_rank | 0.0000 | 0.0000 | 0.1015 | 1439 |
| baseline:ema_crossover | llama3.1:8b | wilcoxon_signed_rank | 0.0000 | 0.0000 | 0.1730 | 1439 |
| baseline:ema_crossover | baseline:random | wilcoxon_signed_rank | 0.0000 | 0.0000 | 0.1984 | 1439 |
| baseline:ema_crossover | baseline:buy_and_hold | wilcoxon_signed_rank | 0.8384 | 1.0000 | 0.0209 | 1439 |
| baseline:ema_crossover | gemma2:2b | wilcoxon_signed_rank | 0.0000 | 0.0000 | 0.2237 | 1439 |
| baseline:ema_crossover | baseline:always_hold | wilcoxon_signed_rank | 0.0000 | 0.0000 | 0.2071 | 1439 |
| qwen2.5:7b | llama3.1:8b | wilcoxon_signed_rank | 0.0000 | 0.0000 | 0.0928 | 1439 |
| qwen2.5:7b | baseline:random | wilcoxon_signed_rank | 0.0000 | 0.0000 | 0.1300 | 1439 |
| qwen2.5:7b | baseline:buy_and_hold | wilcoxon_signed_rank | 0.8526 | 1.0000 | 0.0069 | 1439 |
| qwen2.5:7b | gemma2:2b | wilcoxon_signed_rank | 0.0000 | 0.0000 | 0.1604 | 1439 |
| qwen2.5:7b | baseline:always_hold | wilcoxon_signed_rank | 0.0000 | 0.0000 | 0.1534 | 1439 |
| llama3.1:8b | baseline:random | wilcoxon_signed_rank | 0.0469 | 0.9851 | 0.0630 | 1439 |
| llama3.1:8b | baseline:buy_and_hold | wilcoxon_signed_rank | 0.6299 | 1.0000 | -0.0045 | 1439 |
| llama3.1:8b | gemma2:2b | wilcoxon_signed_rank | 0.0000 | 0.0003 | 0.0912 | 1439 |
| llama3.1:8b | baseline:always_hold | wilcoxon_signed_rank | 0.0023 | 0.0487 | 0.0893 | 1439 |
| baseline:random | baseline:buy_and_hold | wilcoxon_signed_rank | 0.6144 | 1.0000 | -0.0121 | 1439 |
| baseline:random | gemma2:2b | wilcoxon_signed_rank | 0.2613 | 1.0000 | 0.0170 | 1439 |
| baseline:random | baseline:always_hold | wilcoxon_signed_rank | 0.1244 | 1.0000 | 0.0780 | 1439 |
| baseline:buy_and_hold | gemma2:2b | wilcoxon_signed_rank | 0.5245 | 1.0000 | 0.0143 | 1439 |
| baseline:buy_and_hold | baseline:always_hold | wilcoxon_signed_rank | 0.5761 | 1.0000 | 0.0148 | 1439 |

## Charts
- [ablation_sharpe.png](ablation_sharpe.png)
- [model_sharpe.png](model_sharpe.png)

## Limitations
- Results are paper-trading simulations and do not include real exchange order placement.
- Synthetic or short live windows may not capture regime changes, liquidity shocks, or exchange outages.
- Local LLM outputs can vary across model versions, prompts, sampling settings, and hardware latency.

## Reproducibility
- Preserve CSV artifacts, generated charts, model names, prompts, and random seeds for each run.
- Re-run tests with `pytest -q` before publishing tables.
- Use the same price series across compared models and ablation variants.
