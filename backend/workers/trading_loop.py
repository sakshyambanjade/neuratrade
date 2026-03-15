"""
5-minute aligned trading loop with risk gating and persistence.
Run with: python -m workers.trading_loop
"""
import asyncio
import time
from db.database import SessionLocal, init_db
from db import models
from services import market_service, indicator_service, decision_service, risk_service, portfolio_service, memory_service
from utils import event_bus
from config import TICK_INTERVAL_SECONDS
from utils.logging import setup_logging

log = setup_logging()


def record_decision(db, decision):
    ts = int(time.time())
    db.add(
        models.DecisionRecord(
            ts=ts,
            action=decision.action,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
        )
    )
    db.commit()
    return ts


async def tick_loop():
    init_db()
    while True:
        start = time.time()
        target = start - (start % TICK_INTERVAL_SECONDS) + TICK_INTERVAL_SECONDS
        sleep_for = max(0, target - time.time())
        await asyncio.sleep(sleep_for)
        ts = int(time.time())
        with SessionLocal() as db:
            candles = market_service.get_candles(limit=200)
            market_service.persist_candles(db, candles[-1:])
            indicators = indicator_service.latest_indicators(candles)
            price = indicators.get("price", 0)
            snap = portfolio_service.current_portfolio(db, price)
            open_trades = portfolio_service.open_trades_count(db)
            daily_trades = portfolio_service.daily_trade_count(db)
            dd = portfolio_service.current_drawdown(db, price)
            ctx = risk_service.RiskContext(
                equity=snap.total_value,
                open_trades=open_trades,
                daily_trade_count=daily_trades,
                drawdown_pct=dd,
                confidence=1,
            )
            ok, reason = risk_service.validate(ctx)
            if not ok:
                log.info("Risk blocked: %s", reason)
                event_bus.publish({"type": "tick", "timestamp": ts, **indicators, "risk": reason})
                continue
            decision = decision_service.decide(
                indicators,
                {"total_value": snap.total_value, "cash": snap.cash, "btc": snap.btc_held},
                memories=[],
            )
            memory_id = ""
            try:
                memory_id = memory_service.store_decision(
                    content=f"Decision {decision.action} @ {price} | rsi {indicators.get('rsi'):.1f}",
                    importance=0.5,
                    tags=[f"action:{decision.action}", f"phase:{indicators.get('phase','live')}"],
                )
            except Exception as e:
                log.warning("Brain store failed: %s", e)
            record_decision(db, decision)
            # brain write (best effort)

            trade_event = None
            if decision.action == "BUY" and open_trades == 0:
                trade = portfolio_service.open_position(db, price, decision, indicators, brain_id=memory_id)
                if trade:
                    trade_event = {
                        "type": "trade_opened",
                        "timestamp": ts,
                        "id": trade.id,
                        "action": trade.action,
                        "entry_price": trade.entry_price,
                        "size_btc": trade.size_btc,
                    }
            elif decision.action == "SELL" and open_trades > 0:
                closed = portfolio_service.close_position(db, price, "decision_sell")
                if closed:
                    trade_event = {
                        "type": "trade_closed",
                        "timestamp": ts,
                        "id": closed.id,
                        "exit_price": closed.exit_price,
                        "pnl_usdt": closed.pnl_usdt,
                        "pnl_pct": closed.pnl_pct,
                    }
                    try:
                        memory_service.update_outcome(
                            memory_id=closed.brain_memory_id or "",
                            importance=min(0.95, abs(closed.pnl_pct or 0) / 400 + 0.5),
                            suffix=f" | OUTCOME {closed.pnl_pct:+.2f}%",
                        )
                    except Exception:
                        pass

            portfolio_service.snapshot(db, price)

        # Broadcast after DB commit
        event_bus.publish({"type": "tick", "timestamp": ts, **indicators})
        event_bus.publish(
            {"type": "decision", "timestamp": ts, "action": decision.action, "confidence": decision.confidence, "reasoning": decision.reasoning}
        )
        if trade_event:
            event_bus.publish(trade_event)


def main():
    asyncio.run(tick_loop())


if __name__ == "__main__":
    main()
