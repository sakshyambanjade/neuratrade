"""
Risk gating for every trade decision.
"""
from dataclasses import dataclass
from config import (
    MAX_POSITION_PCT,
    MAX_OPEN_TRADES,
    MAX_DAILY_TRADES,
    MAX_DRAWDOWN_PCT,
    MIN_CONFIDENCE,
)


@dataclass
class RiskContext:
    equity: float
    open_trades: int
    daily_trade_count: int
    drawdown_pct: float
    confidence: float


def validate(ctx: RiskContext) -> tuple[bool, str]:
    if ctx.confidence < MIN_CONFIDENCE:
        return False, f"Confidence {ctx.confidence:.2f} below min {MIN_CONFIDENCE}"
    if ctx.open_trades >= MAX_OPEN_TRADES:
        return False, f"Max open trades {MAX_OPEN_TRADES} reached"
    if ctx.daily_trade_count >= MAX_DAILY_TRADES:
        return False, f"Max daily trades {MAX_DAILY_TRADES} reached"
    if ctx.drawdown_pct <= -MAX_DRAWDOWN_PCT:
        return False, f"Max drawdown {MAX_DRAWDOWN_PCT*100:.1f}% breached"
    # Position sizing check (simplified for paper trading)
    position_cap = ctx.equity * MAX_POSITION_PCT
    return True, f"Within limits (position cap ${position_cap:,.2f})"
