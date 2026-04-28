# Metrics

NeuraTradeBench reports metrics that describe return, risk, trade quality, and execution realism.

## Return

Return measures the percentage change in simulated equity over the experiment. It is the simplest profitability measure, but it does not account for volatility, drawdown, or execution risk.

## Sharpe Ratio

Sharpe ratio measures return relative to volatility. Higher Sharpe values indicate smoother returns per unit of variability, assuming the sampled return distribution is meaningful.

## Sortino Ratio

Sortino ratio measures return relative to downside volatility. It focuses on harmful volatility rather than all volatility, making it useful when upside jumps should not be penalized like losses.

## Calmar Ratio

Calmar ratio compares annualized return with max drawdown. It rewards return only when it is achieved without large peak-to-trough losses.

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

## Latency

Latency tracks simulated or observed delay around model inference and execution. It helps quantify whether slower models or execution assumptions degrade results.

## Slippage

Slippage measures the difference between decision price and simulated fill price, usually in basis points. It captures spread, market impact, and execution cost assumptions.

## LLM Confidence Correlation

Confidence-return correlation measures whether higher-confidence model decisions are associated with better realized returns. It helps identify models that are confidently wrong.
