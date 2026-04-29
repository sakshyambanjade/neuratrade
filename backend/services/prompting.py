"""
Versioned paper-trading prompt templates.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

PROMPT_VERSION = "ntb-v2"

PROMPT_TEMPLATE = """You are NeuraTradeBench, a paper-trading BTCUSDT research agent.
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
"""


def template_hash(template_text: str = PROMPT_TEMPLATE) -> str:
    return hashlib.sha256(template_text.encode("utf-8")).hexdigest()


def render_prompt(
    *,
    market: dict[str, Any],
    indicators: dict[str, Any],
    portfolio: dict[str, Any],
    risk: dict[str, Any],
    template_text: str = PROMPT_TEMPLATE,
) -> str:
    return template_text.format(
        market_json=_stable_json(market),
        indicator_json=_stable_json(indicators),
        portfolio_json=_stable_json(portfolio),
        risk_json=_stable_json(risk),
    )


def _stable_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
