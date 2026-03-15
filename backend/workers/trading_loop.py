"""
Skeleton 5-minute loop with clock alignment and placeholders.
Run with: python -m workers.trading_loop
"""
import asyncio
import time
import uuid
from db.database import SessionLocal, init_db
from db import models
from services import market_service, indicator_service, decision_service, risk_service
from api.websocket import manager
from config import SYMBOL, TICK_INTERVAL_SECONDS
from utils.logging import setup_logging

log = setup_logging()


async def tick_loop():
    init_db()
    while True:
        start = time.time()
        target = start - (start % TICK_INTERVAL_SECONDS) + TICK_INTERVAL_SECONDS
        sleep_for = max(0, target - time.time())
        await asyncio.sleep(sleep_for)
        ts = int(time.time())
        candles = market_service.get_candles(limit=200)
        indicators = indicator_service.latest_indicators(candles)

        # Broadcast tick
        await manager.broadcast({"type": "tick", "timestamp": ts, **indicators})

        # Risk & decision (simplified portfolio)
        equity = 10000.0
        ctx = risk_service.RiskContext(
            equity=equity,
            open_trades=0,
            daily_trade_count=0,
            drawdown_pct=0,
            confidence=0.5,
        )
        ok, reason = risk_service.validate(ctx)
        if not ok:
            log.info("Risk blocked: %s", reason)
            continue
        decision = decision_service.decide(indicators, {"total_value": equity, "cash": equity, "btc": 0}, memories=[])
        log.info("Decision: %s", decision)
        trade_id = f"tr_{uuid.uuid4().hex[:8]}"

        # Persist trade opening (idempotent placeholder)
        with SessionLocal() as db:
            trade = models.Trade(
                id=trade_id,
                opened_at=ts,
                action=decision.action,
                entry_price=indicators.get("price", 0),
                size_btc=0,
                size_usdt=0,
                stop_loss=0,
                take_profit=0,
                status="open" if decision.action != "HOLD" else "skipped",
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                indicator_snapshot="{}",
            )
            db.merge(trade)
            db.commit()

        await manager.broadcast(
            {"type": "decision", "timestamp": ts, "action": decision.action, "confidence": decision.confidence, "reasoning": decision.reasoning}
        )


def main():
    asyncio.run(tick_loop())


if __name__ == "__main__":
    main()
