# Metrics

NeuraTradeBench reports metrics that describe return, risk, trade quality, and execution realism.

## Return

Return measures the percentage change in simulated equity over the experiment. It is the simplest profitability measure, but it does not account for volatility, drawdown, or execution risk.

## Sharpe Ratio

Sharpe ratio measures return relative to volatility. Higher Sharpe values indicate smoother returns per unit of variability, assuming the sampled return distribution is meaningful.

NeuraTradeBench only reports annualized Sharpe when at least 30 period returns are available. Shorter windows return `0.0` so tiny smoke tests cannot produce inflated annualized values.

Experiment runners accept `periods_per_year` so reports can deliberately use non-annualized Sharpe for synthetic or short-window demos. Long 1-minute historical runs should use `525600`; short reproducibility demos should use `1` and label the metric scale.

## Sortino Ratio

Sortino ratio measures return relative to downside volatility. It focuses on harmful volatility rather than all volatility, making it useful when upside jumps should not be penalized like losses.

Like Sharpe, Sortino is guarded behind a 30-return minimum sample size.

## Calmar Ratio

Calmar ratio compares annualized return with max drawdown. It rewards return only when it is achieved without large peak-to-trough losses.

Calmar is also disabled for windows with fewer than 30 period returns.

## Value At Risk 95%

Value at Risk 95% estimates the one-period loss threshold at the 5th percentile of observed returns. It is reported as a positive loss magnitude.

## Conditional Value At Risk 95%

Conditional Value at Risk 95% averages the worst 5% tail returns. It is useful for measuring tail severity beyond the VaR cutoff.

## Max Drawdown

Max drawdown measures the largest peak-to-trough equity decline during the run. It is a core risk metric because strategies with similar returns can have very different loss profiles.

## Win Rate

Win rate is the share of closed simulated trades with positive realized PnL. It should be interpreted alongside average win/loss size because a high win rate can still lose money.

## Profit Factor

Profit factor is gross simulated profit divided by gross simulated loss. Values above 1 indicate that winning trades outweighed losing trades in aggregate.

If a run has winning closed trades and no losing closed trades, the true ratio is unbounded. Reports use a finite cap of `999.0` to avoid JSON/CSV infinities while still distinguishing no-loss winners from no-trade or no-win runs.

## Latency

Latency tracks simulated or observed delay around model inference and execution. It helps quantify whether slower models or execution assumptions degrade results.

## Slippage

Slippage measures the difference between decision price and simulated fill price, usually in basis points. It captures spread, market impact, and execution cost assumptions.

## LLM Confidence Correlation

Confidence-return correlation measures whether higher-confidence model decisions are associated with better realized returns. It helps identify models that are confidently wrong.

## Statistical Validation

Model comparison reports include bootstrap 95% confidence intervals for return, Sharpe, and win rate, plus pairwise Wilcoxon signed-rank tests on matched period returns. Corrected p-values use a Bonferroni adjustment across the pairwise leaderboard comparisons.
