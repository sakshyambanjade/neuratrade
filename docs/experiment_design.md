# Experiment Design

NeuraTradeBench experiments are designed to compare model behavior and isolate system components under controlled conditions.

## Model Comparison

Model comparison runs multiple local Ollama models over the same price series. Each model receives equivalent market context, produces trading decisions, and is scored with the same simulator and metrics. Results are ranked by Sharpe ratio, drawdown, and cumulative return.

Leaderboard runs include deterministic baselines by default: random actions, buy-and-hold, EMA crossover, and always-hold. Keep these rows in publication tables so readers can see whether an LLM adds value over trivial policies.

Use model comparison to answer questions such as:

- Which local model produces the most stable simulated equity curve?
- Which model trades too often or too aggressively?
- Which model has the best risk-adjusted return under identical inputs?

## Memory Vs No Memory

The memory ablation compares the full system with a variant that disables memory-dependent behavior. This helps estimate whether prior context improves decisions or simply increases variance and hallucination risk.

## Risk Vs No Risk

The risk ablation compares normal risk-gated execution with a variant that bypasses the risk engine. This measures how often risk rules prevent bad or oversized model actions and how much they affect return, drawdown, and trade count.

## Slippage Vs No Slippage

The slippage ablation compares simulated execution with and without spread and market-impact assumptions. This helps separate model decision quality from execution cost sensitivity.

## Latency Vs No Latency

The latency ablation compares normal simulated latency with zero-latency fills. This estimates how much inference and execution delay can affect outcomes, especially during fast market movement.

## Recommended Controls

Use the same price series, starting balances, fee assumptions, model versions, prompts, and random seeds for every variant in a comparison. Store the generated CSV, JSON, logs, and reports with the experiment configuration.

For benchmark claims, use at least 1,000 matched price points and report bootstrap confidence intervals plus pairwise tests on matched period returns. Smoke tests can use shorter windows, but risk-adjusted metrics intentionally return `0.0` until at least 30 period returns are available.
