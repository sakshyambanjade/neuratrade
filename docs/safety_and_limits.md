# Safety And Limits

NeuraTradeBench is a simulator and paper-trading benchmark. It is intended for research, evaluation, and reporting, not real-money trading.

## No Real Trading

The live experiment path does not submit exchange orders. Model decisions are converted into simulated fills only. Results are paper-trading artifacts and should not be interpreted as deployable trading signals.

## Risk Blocks

The risk engine can block or modify model decisions based on confidence, position size, drawdown, spread, volatility, stop-loss data, and recent losses. Risk blocks are logged so experiments can measure how often the model attempts unsafe actions.

## Kill Switch

Live dry-run experiments can be stopped with process signals such as `Ctrl-C`. A supervised run should also use conservative `max_cycles`, isolated credentials, and external process monitoring when appropriate.

## Simulator Assumptions

The simulator approximates fills, fees, slippage, latency, and portfolio balances. It does not fully model exchange queues, outages, partial liquidity across venues, liquidation mechanics, funding, taxes, or regulatory constraints.

## Model Hallucination Risks

LLMs can hallucinate, ignore instructions, produce malformed JSON, overreact to noisy context, or express false confidence. NeuraTradeBench mitigates this with strict schemas, fallback `HOLD` decisions, and risk gates, but these controls do not make model output inherently reliable.

## Research Boundary

Benchmark results are useful for comparing models and system variants under shared assumptions. They are not financial advice, not a performance guarantee, and not evidence that a model will work in real markets.
