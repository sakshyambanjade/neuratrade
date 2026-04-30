"""
LLM-backed decision service with validation + fallback to rules.
"""

from config import MIN_CONFIDENCE
from pydantic import BaseModel, Field, field_validator

from services.ollama_client import OllamaClient
from services.prompting import render_prompt


class Decision(BaseModel):
    action: str
    confidence: float
    reasoning: str
    position_size_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    stop_loss: float = Field(default=0.0, ge=0.0)
    take_profit: float = Field(default=0.0, ge=0.0)

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


def _fallback_rule(indicators: dict) -> Decision:
    # RSI 30/70 are conventional oversold/overbought guardrails used only when the LLM path fails.
    if indicators.get("rsi", 50) < 30 and indicators.get("macd", 0) > 0:
        return Decision(action="BUY", confidence=0.5, reasoning="Fallback oversold rule")
    if indicators.get("rsi", 50) > 70:
        return Decision(action="SELL", confidence=0.5, reasoning="Fallback overbought rule")
    return Decision(action="HOLD", confidence=0.4, reasoning="Fallback neutral rule")


def call_llm(indicators: dict, portfolio: dict, memories: list[str]) -> Decision:
    prompt = render_prompt(
        market={
            "symbol": "BTCUSDT",
            "last_price": indicators.get("price"),
            "source": "decision_service",
        },
        indicators=indicators,
        portfolio=portfolio,
        risk={
            "dry_run": True,
            "execution_mode": "paper_trading",
            "memories": memories,
        },
    )
    decision = OllamaClient().decide(prompt, fallback_on_error=False)
    return Decision(**decision.model_dump())


def decide(indicators: dict, portfolio: dict, memories: list[str]) -> Decision:
    try:
        decision = call_llm(indicators, portfolio, memories)
    except Exception:
        decision = _fallback_rule(indicators)
    # Enforce minimum confidence
    if decision.confidence < MIN_CONFIDENCE:
        decision = Decision(
            action="HOLD", confidence=decision.confidence, reasoning="Confidence below minimum; holding"
        )
    return decision
