"""
LLM output parsing and semantic quality checks for paper-trading decisions.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HallucinationEvent:
    hallucination_type: str
    field_name: str = ""
    field_value: str = ""
    corrective_action: str = "fallback_hold"


def extract_first_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        loaded = json.loads(stripped)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("no JSON object found")
    loaded = json.loads(match.group(0))
    if not isinstance(loaded, dict):
        raise ValueError("JSON payload is not an object")
    return loaded


def validate_decision_payload(data: dict[str, Any], *, current_price: float) -> list[HallucinationEvent]:
    events: list[HallucinationEvent] = []
    action = str(data.get("action", "")).strip().upper()
    if action not in {"BUY", "SELL", "HOLD"}:
        events.append(HallucinationEvent("invalid_action", "action", str(data.get("action", ""))))

    for field_name in ("confidence", "position_size_pct", "stop_loss", "take_profit"):
        value = data.get(field_name)
        if value is None:
            events.append(HallucinationEvent("non_numeric_field", field_name, ""))
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            events.append(HallucinationEvent("non_numeric_field", field_name, str(value)))
            continue
        if not math.isfinite(number):
            events.append(HallucinationEvent("non_finite_field", field_name, str(value)))
            continue
        if field_name == "confidence" and not 0.0 <= number <= 1.0:
            events.append(HallucinationEvent("confidence_out_of_range", field_name, str(value)))
        if field_name == "position_size_pct" and action != "HOLD" and not 0.0 < number <= 1.0:
            events.append(HallucinationEvent("position_size_out_of_range", field_name, str(value)))

    reasoning = str(data.get("reasoning", "")).strip()
    if len(reasoning.split()) < 10:
        events.append(HallucinationEvent("reasoning_too_short", "reasoning", reasoning))

    stop_loss = _float_or_none(data.get("stop_loss"))
    take_profit = _float_or_none(data.get("take_profit"))
    if action == "BUY" and stop_loss is not None and take_profit is not None:
        if not stop_loss < current_price < take_profit:
            events.append(
                HallucinationEvent("invalid_buy_brackets", "stop_loss_take_profit", f"{stop_loss},{take_profit}")
            )
    if action == "SELL" and stop_loss is not None and take_profit is not None:
        if not take_profit < current_price < stop_loss:
            events.append(
                HallucinationEvent("invalid_sell_brackets", "stop_loss_take_profit", f"{stop_loss},{take_profit}")
            )

    return events


def has_repetition_loop(text: str, *, max_repeats: int = 3) -> bool:
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < 6:
        return False
    phrases = [" ".join(words[index : index + 3]) for index in range(len(words) - 2)]
    return any(count > max_repeats for count in Counter(phrases).values())


class ActionDistributionMonitor:
    def __init__(self, *, window: int = 20, max_share: float = 0.95) -> None:
        self.window = window
        self.max_share = max_share
        self.actions: deque[str] = deque(maxlen=window)

    def observe(self, action: str) -> bool:
        self.actions.append(action.upper())
        if len(self.actions) < self.window:
            return False
        most_common = Counter(self.actions).most_common(1)[0][1]
        return most_common / len(self.actions) >= self.max_share


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
