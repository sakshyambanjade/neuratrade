# NeuraTradeBench Experiment 1

## Experiment Config
```json
{
  "ablation_csv": "../artifacts/demo/ablation_results.csv",
  "comparison_csv": "../artifacts/demo/model_comparison.csv",
  "experiment": "paper-demo",
  "models": [
    "qwen2.5:7b",
    "llama3.1:8b",
    "gemma2:2b"
  ],
  "price_points": 8,
  "prompt_version": "ntb-v1",
  "seed": 42
}
```

## Model Leaderboard
| rank | model | return | sharpe | sortino | calmar | max_drawdown | win_rate | profit_factor | avg_latency_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | qwen2.5:7b | 0.001177650401392949 | 288.99073585826756 | 433.8214424474513 | 205260.07059177203 | 0.00043080433323662153 | 1.0 | 0.0 | 25.0 |
| 2 | gemma2:2b | 0.00010481100832704371 | 51.75664054376273 | 32.166832838308885 | 23320.39920060945 | 0.0003379465381076443 | 1.0 | 0.0 | 25.0 |
| 3 | llama3.1:8b | -0.0005636135259905473 | -134.44067838903916 | -131.79630131586504 | -38255.85416230833 | 0.0011051929344601376 | 0.5 | 0.3565656880116404 | 25.0 |

## Ablation Table
| variant | cumulative_return | sharpe | sortino | calmar | max_drawdown | win_rate | profit_factor | avg_slippage_bps | avg_latency_ms | trade_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_system | 0.001687481982338257 | 307.31241070431423 | 482.83135646317777 | 294099.20893235505 | 0.00043080433323662153 | 1.0 | 0.0 | 12.514369483274383 | 25.0 | 4 |
| no_risk_engine | 0.0008321648753504274 | 200.08463321150035 | 265.90492715400626 | 145101.1704228556 | 0.00043080433323662153 | 1.0 | 0.0 | 12.521834184625208 | 25.0 | 4 |
| no_memory | 0.001687481982338257 | 307.31241070431423 | 482.83135646317777 | 294099.20893235505 | 0.00043080433323662153 | 1.0 | 0.0 | 12.514369483274383 | 25.0 | 4 |
| no_news | 0.001687481982338257 | 307.31241070431423 | 482.83135646317777 | 294099.20893235505 | 0.00043080433323662153 | 1.0 | 0.0 | 12.514369483274383 | 25.0 | 4 |
| no_slippage | 0.0020635903461234673 | 349.5154652910136 | 590.4993612951058 | 359667.5059061219 | 0.00043069634369578017 | 1.0 | 0.0 | 0.0 | 25.0 | 4 |
| no_latency | 0.001687481982338257 | 307.31241070431423 | 482.83135646317777 | 294099.20893235505 | 0.00043080433323662153 | 1.0 | 0.0 | 12.514369483274383 | 0.0 | 4 |

## Key Metrics
- `best_sharpe`: `no_slippage`
- `highest_return`: `no_slippage`
- `lowest_drawdown`: `no_slippage`

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
