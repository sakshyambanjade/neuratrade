# Methodology

NeuraTradeBench evaluates local LLM trading behavior through live BTC paper-trading experiments. The benchmark observes a live BTC market feed, prompts a local Ollama model, validates the model decision through risk controls, and records only simulated executions.

## Live BTC Evaluation

The live runner uses `BTCUSDT` market snapshots as the primary evaluation stream. Each cycle captures current market context, account state, and risk context, then asks the selected model for a trading decision.

The live setup is useful for studying decision behavior under real-time market movement, but it is not a complete market replay or exchange-grade simulator.

## Local Ollama Models

Models run locally through Ollama. This keeps inference private, repeatable within a controlled machine setup, and inexpensive for repeated experiments. Each model must return strict JSON with a `BUY`, `SELL`, or `HOLD` action plus confidence, size, reasoning, stop loss, and take profit.

If Ollama fails, times out, or returns invalid JSON, NeuraTradeBench records the failure and uses a `HOLD` fallback.

## Dry-Run Simulator

Every live experiment is dry-run only. Approved decisions are sent to the execution simulator, which updates paper balances and logs simulated fills, fees, slippage, latency, and realized PnL.

## No Real Orders

NeuraTradeBench does not place live orders in the live experiment path. There are no real exchange-side order submissions, no custody actions, and no production trading guarantees. Results are research artifacts, not trading instructions.
