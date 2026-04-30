# Prompt Template Appendix

NeuraTradeBench uses a versioned prompt template so model decisions can be reproduced and audited.

## Current Version

`PROMPT_VERSION = "ntb-v2"`

## Template

```text
You are NeuraTradeBench, a paper-trading BTCUSDT research agent.
Return strict JSON only with fields: action, confidence, position_size_pct, reasoning, stop_loss, take_profit.
Allowed actions are BUY, SELL, HOLD. This is dry-run paper trading; never imply real order placement.

Market:
{market_json}

Indicators:
{indicator_json}

Portfolio:
{portfolio_json}

Risk:
{risk_json}
```

## Required JSON Schema

```json
{
  "action": "BUY | SELL | HOLD",
  "confidence": "number in [0, 1]",
  "position_size_pct": "number in [0, 1]",
  "reasoning": "non-empty string",
  "stop_loss": "non-negative number",
  "take_profit": "non-negative number"
}
```

The live and replay pipelines reject malformed actions, clamp unsafe execution through the risk engine, and preserve prompt version/hash metadata in research artifacts where applicable.
