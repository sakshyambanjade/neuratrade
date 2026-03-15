"""
LLM-backed decision service with validation + fallback to rules.
"""
import json
import httpx
from pydantic import BaseModel, ValidationError, field_validator
from tenacity import retry, wait_fixed, stop_after_attempt

from config import OLLAMA_URL, LLM_MODEL, LLM_TIMEOUT, MIN_CONFIDENCE


class Decision(BaseModel):
    action: str
    confidence: float
    reasoning: str

    @field_validator("action")
    @classmethod
    def normalize_action(cls, v):
        v = v.upper()
        if v not in {"BUY", "SELL", "HOLD"}:
            raise ValueError("invalid action")
        return v

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v):
        if v < 0 or v > 1:
            raise ValueError("confidence out of range")
        return v


PROMPT_TEMPLATE = """You are a disciplined BTC/USDT trader.
Return a compact JSON with fields: action (BUY/SELL/HOLD), confidence (0-1), reasoning.
Use indicators: RSI={rsi:.1f}, MACD={macd:.5f}, BB_upper={bb_upper:.2f}, BB_lower={bb_lower:.2f}, EMA9={ema9:.2f}, EMA21={ema21:.2f}.
Portfolio total={total_value:.2f}, cash={cash:.2f}, btc={btc:.6f}.
Recent memories: {memories}
Respond with JSON only."""


def _fallback_rule(indicators: dict) -> Decision:
    if indicators.get("rsi", 50) < 30 and indicators.get("macd", 0) > 0:
        return Decision(action="BUY", confidence=0.5, reasoning="Fallback oversold rule")
    if indicators.get("rsi", 50) > 70:
        return Decision(action="SELL", confidence=0.5, reasoning="Fallback overbought rule")
    return Decision(action="HOLD", confidence=0.4, reasoning="Fallback neutral rule")


@retry(wait=wait_fixed(1), stop=stop_after_attempt(2))
def call_llm(indicators: dict, portfolio: dict, memories: list[str]) -> Decision:
    payload = {
        "model": LLM_MODEL,
        "prompt": PROMPT_TEMPLATE.format(memories=memories, **indicators, **portfolio),
        "stream": False,
    }
    with httpx.Client(timeout=LLM_TIMEOUT) as client:
        resp = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
        text = resp.json().get("response", "{}")
    try:
        data = json.loads(text)
        decision = Decision(**data)
        return decision
    except (json.JSONDecodeError, ValidationError, TypeError):
        raise


def decide(indicators: dict, portfolio: dict, memories: list[str]) -> Decision:
    try:
        decision = call_llm(indicators, portfolio, memories)
    except Exception:
        decision = _fallback_rule(indicators)
    # Enforce minimum confidence
    if decision.confidence < MIN_CONFIDENCE:
        decision = Decision(action="HOLD", confidence=decision.confidence, reasoning="Confidence below minimum; holding")
    return decision
