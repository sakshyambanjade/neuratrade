"""
Production-grade risk engine for LLM trading decisions.
"""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Action = Literal["BUY", "SELL", "HOLD"]


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_confidence: float = Field(default=0.60, ge=0, le=1)
    max_position_pct: float = Field(default=0.25, ge=0, le=1)
    max_risk_per_trade_pct: float = Field(default=0.01, ge=0, le=1)
    max_daily_drawdown_pct: float = Field(default=0.03, ge=0)
    max_total_drawdown_pct: float = Field(default=0.10, ge=0)
    max_spread_bps: float = Field(default=25.0, ge=0)
    high_volatility_threshold: float = Field(default=0.05, ge=0)
    consecutive_loss_cooldown: int = Field(default=3, ge=0)
    kill_switch_active: bool = False


class RiskInput(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    action: str
    confidence: float = 0.0
    position_size_pct: float = 0.0
    equity: float
    entry_price: float | None = None
    stop_loss: float | None = None
    daily_drawdown_pct: float = 0.0
    total_drawdown_pct: float = 0.0
    spread_bps: float = 0.0
    volatility: float = 0.0
    consecutive_losses: int = 0

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value: object) -> str:
        return str(value).upper()


class RiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    final_action: Action
    final_size_pct: float
    reason: str
    triggered_rules: list[str]


class RiskEngine:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def validate(self, risk_input: RiskInput) -> RiskDecision:
        triggered: list[str] = []
        action = risk_input.action.upper()
        final_action: Action = action if action in {"BUY", "SELL", "HOLD"} else "HOLD"
        final_size_pct = _finite_or_zero(risk_input.position_size_pct)

        if self.config.kill_switch_active:
            triggered.append("kill_switch")
            return self._blocked(final_action="HOLD", triggered=triggered, reason="Kill switch active")

        finite_error = self._finite_error(risk_input)
        if finite_error:
            triggered.append("invalid_numeric_input")
            return self._blocked(final_action="HOLD", triggered=triggered, reason=finite_error)

        if action not in {"BUY", "SELL", "HOLD"}:
            triggered.append("invalid_action")
            return self._blocked(final_action="HOLD", triggered=triggered, reason=f"Invalid action {risk_input.action}")

        if action == "HOLD":
            return RiskDecision(
                allowed=True,
                final_action="HOLD",
                final_size_pct=0.0,
                reason="Hold allowed",
                triggered_rules=[],
            )

        if risk_input.confidence < self.config.min_confidence:
            triggered.append("min_confidence")
            return self._blocked(
                final_action=final_action,
                triggered=triggered,
                reason=f"Confidence {risk_input.confidence:.2f} below {self.config.min_confidence:.2f}",
            )

        if risk_input.stop_loss is None or risk_input.stop_loss <= 0:
            triggered.append("missing_stop_loss")
            return self._blocked(final_action=final_action, triggered=triggered, reason="Missing stop_loss")

        if risk_input.daily_drawdown_pct >= self.config.max_daily_drawdown_pct:
            triggered.append("daily_drawdown")
            return self._blocked(final_action=final_action, triggered=triggered, reason="Daily drawdown limit breached")

        if risk_input.total_drawdown_pct >= self.config.max_total_drawdown_pct:
            triggered.append("total_drawdown")
            return self._blocked(final_action=final_action, triggered=triggered, reason="Total drawdown limit breached")

        if risk_input.spread_bps > self.config.max_spread_bps:
            triggered.append("max_spread")
            return self._blocked(final_action=final_action, triggered=triggered, reason="Spread too wide")

        if risk_input.consecutive_losses >= self.config.consecutive_loss_cooldown:
            triggered.append("loss_cooldown")
            return self._blocked(final_action=final_action, triggered=triggered, reason="Loss cooldown active")

        if final_size_pct > self.config.max_position_pct:
            final_size_pct = self.config.max_position_pct
            triggered.append("max_position_pct")

        risk_cap_pct = self._risk_cap_pct(risk_input)
        if risk_cap_pct is not None and final_size_pct > risk_cap_pct:
            final_size_pct = risk_cap_pct
            triggered.append("max_risk_per_trade")

        if risk_input.volatility >= self.config.high_volatility_threshold:
            final_size_pct *= 0.5
            triggered.append("high_volatility")

        final_size_pct = min(max(final_size_pct, 0.0), self.config.max_position_pct)
        reason = "Allowed" if not triggered else f"Allowed with adjustments: {', '.join(triggered)}"
        return RiskDecision(
            allowed=True,
            final_action=final_action,
            final_size_pct=final_size_pct,
            reason=reason,
            triggered_rules=triggered,
        )

    def _risk_cap_pct(self, risk_input: RiskInput) -> float | None:
        if risk_input.entry_price is None or risk_input.entry_price <= 0:
            return None
        if risk_input.stop_loss is None or risk_input.stop_loss <= 0:
            return None
        price_risk_pct = abs(risk_input.entry_price - risk_input.stop_loss) / risk_input.entry_price
        if price_risk_pct <= 0:
            return None
        return self.config.max_risk_per_trade_pct / price_risk_pct

    @staticmethod
    def _finite_error(risk_input: RiskInput) -> str | None:
        numeric_values = {
            "confidence": risk_input.confidence,
            "position_size_pct": risk_input.position_size_pct,
            "equity": risk_input.equity,
            "daily_drawdown_pct": risk_input.daily_drawdown_pct,
            "total_drawdown_pct": risk_input.total_drawdown_pct,
            "spread_bps": risk_input.spread_bps,
            "volatility": risk_input.volatility,
            "consecutive_losses": float(risk_input.consecutive_losses),
        }
        if risk_input.entry_price is not None:
            numeric_values["entry_price"] = risk_input.entry_price
        if risk_input.stop_loss is not None:
            numeric_values["stop_loss"] = risk_input.stop_loss

        for name, value in numeric_values.items():
            if not math.isfinite(float(value)):
                return f"{name} must be finite"
        if risk_input.equity <= 0:
            return "equity must be positive"
        return None

    @staticmethod
    def _blocked(*, final_action: Action, triggered: list[str], reason: str) -> RiskDecision:
        return RiskDecision(
            allowed=False,
            final_action=final_action,
            final_size_pct=0.0,
            reason=reason,
            triggered_rules=triggered,
        )


def _finite_or_zero(value: float) -> float:
    return float(value) if math.isfinite(float(value)) else 0.0
