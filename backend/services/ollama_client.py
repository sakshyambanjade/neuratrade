"""
Reusable Ollama client for strict JSON trading decisions.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from config import LLM_MODEL, LLM_TIMEOUT, OLLAMA_URL
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from services.llm_quality import extract_first_json_object

Action = Literal["BUY", "SELL", "HOLD"]


class OllamaDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Action
    confidence: float = Field(ge=0.0, le=1.0)
    position_size_pct: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1)
    stop_loss: float = Field(ge=0.0)
    take_profit: float = Field(ge=0.0)

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("action must be a string")
        action = value.upper()
        if action not in {"BUY", "SELL", "HOLD"}:
            raise ValueError("action must be BUY, SELL, or HOLD")
        return action


DECISION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "position_size_pct": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string", "minLength": 1},
        "stop_loss": {"type": "number", "minimum": 0},
        "take_profit": {"type": "number", "minimum": 0},
    },
    "required": [
        "action",
        "confidence",
        "position_size_pct",
        "reasoning",
        "stop_loss",
        "take_profit",
    ],
}


class OllamaDecisionError(RuntimeError):
    """Raised when Ollama does not return a valid decision."""


def fallback_decision(
    reasoning: str = "Ollama unavailable during paper-trading inference, so the system is holding safely.",
) -> OllamaDecision:
    return OllamaDecision(
        action="HOLD",
        confidence=0.0,
        position_size_pct=0.0,
        reasoning=reasoning,
        stop_loss=0.0,
        take_profit=0.0,
    )


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_URL,
        model: str = LLM_MODEL,
        timeout: float = float(LLM_TIMEOUT),
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.retries = max(1, retries)
        self.transport = transport

    def decide(self, prompt: str, *, fallback_on_error: bool = True) -> OllamaDecision:
        try:
            return self._decide_with_retries(prompt)
        except (httpx.TimeoutException, httpx.HTTPError, OllamaDecisionError):
            if fallback_on_error:
                return fallback_decision()
            raise

    def _decide_with_retries(self, prompt: str) -> OllamaDecision:
        last_error: Exception | None = None
        for _ in range(self.retries):
            try:
                return self._request_decision(prompt)
            except (httpx.TimeoutException, httpx.HTTPError, OllamaDecisionError) as exc:
                last_error = exc
        detail = f": {last_error}" if last_error else ""
        raise OllamaDecisionError(f"Ollama decision failed{detail}") from last_error

    def _request_decision(self, prompt: str) -> OllamaDecision:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": DECISION_JSON_SCHEMA,
            "options": {"temperature": 0},
        }
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            response = client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            body = response.json()
        return parse_ollama_decision(body)


def parse_ollama_decision(body: dict[str, Any]) -> OllamaDecision:
    raw_response = body.get("response")
    if isinstance(raw_response, dict):
        data = raw_response
    elif isinstance(raw_response, str):
        try:
            data = extract_first_json_object(raw_response)
        except json.JSONDecodeError as exc:
            raise OllamaDecisionError("Ollama response was not valid JSON") from exc
        except ValueError as exc:
            raise OllamaDecisionError("Ollama response was not valid JSON") from exc
    else:
        raise OllamaDecisionError("Ollama response field missing or invalid")

    try:
        return OllamaDecision.model_validate(data)
    except ValidationError as exc:
        raise OllamaDecisionError("Ollama decision did not match schema") from exc
