import json
import time
import uuid
from typing import Optional

from sqlalchemy import func

from db.database import SessionLocal
from db import models
from config import SYMBOL, MAX_POSITION_PCT

INITIAL_CASH = 10000.0


def _ensure_snapshot(db, price: float):
    latest = db.query(models.PortfolioSnapshot).order_by(models.PortfolioSnapshot.ts.desc()).first()
    if latest:
        return latest
    snap = models.PortfolioSnapshot(
        ts=int(time.time()),
        cash=INITIAL_CASH,
        btc_held=0.0,
        total_value=INITIAL_CASH,
        daily_pnl=0.0,
    )
    db.add(snap)
    db.commit()
    return snap


def current_portfolio(db, price: float) -> models.PortfolioSnapshot:
    snap = _ensure_snapshot(db, price)
    value = snap.cash + snap.btc_held * price
    snap.total_value = value
    return snap


def current_drawdown(db, price: float) -> float:
    snaps = (
        db.query(models.PortfolioSnapshot)
        .order_by(models.PortfolioSnapshot.ts.asc())
        .all()
    )
    peak = 0
    dd = 0
    for s in snaps:
        val = s.total_value if s.total_value else s.cash + s.btc_held * price
        if val > peak:
            peak = val
        if peak:
            dd = min(dd, (val - peak) / peak)
    return abs(dd)


def open_trades_count(db) -> int:
    return db.query(models.Trade).filter(models.Trade.status == "open").count()


def daily_trade_count(db) -> int:
    today_start = int(time.time()) - 86400
    return (
        db.query(func.count(models.Trade.id))
        .filter(models.Trade.opened_at >= today_start)
        .scalar()
        or 0
    )


def open_trade(db) -> Optional[models.Trade]:
    return (
        db.query(models.Trade)
        .filter(models.Trade.status == "open")
        .order_by(models.Trade.opened_at.desc())
        .first()
    )


def open_position(db, price: float, decision, indicators: dict, brain_id: str = "") -> Optional[models.Trade]:
    snap = current_portfolio(db, price)
    size_usdt = min(snap.total_value * MAX_POSITION_PCT, snap.cash)
    if size_usdt <= 0:
        return None
    size_btc = size_usdt / price
    trade_id = f"tr_{uuid.uuid4().hex[:10]}"
    trade = models.Trade(
        id=trade_id,
        opened_at=int(time.time()),
        action="BUY",
        entry_price=price,
        size_btc=size_btc,
        size_usdt=size_usdt,
        stop_loss=price * 0.97,
        take_profit=price * 1.03,
        status="open",
        confidence=decision.confidence,
        reasoning=decision.reasoning,
        indicator_snapshot=json.dumps(indicators),
        memories_used=json.dumps([]),
        brain_memory_id=brain_id,
    )
    snap.cash -= size_usdt
    snap.btc_held += size_btc
    snap.total_value = snap.cash + snap.btc_held * price
    db.add(trade)
    db.merge(snap)
    db.commit()
    return trade


def close_position(db, price: float, reason: str):
    trade = open_trade(db)
    if not trade:
        return None
    pnl_usdt = (price - trade.entry_price) * trade.size_btc
    pnl_pct = pnl_usdt / trade.size_usdt if trade.size_usdt else 0
    trade.closed_at = int(time.time())
    trade.exit_price = price
    trade.pnl_usdt = pnl_usdt
    trade.pnl_pct = pnl_pct * 100
    trade.close_reason = reason
    trade.status = "closed"
    snap = current_portfolio(db, price)
    snap.cash += trade.size_usdt + pnl_usdt
    snap.btc_held -= trade.size_btc
    snap.total_value = snap.cash + snap.btc_held * price
    db.merge(trade)
    db.merge(snap)
    db.commit()
    return trade


def snapshot(db, price: float):
    snap = current_portfolio(db, price)
    snap.ts = int(time.time())
    db.merge(snap)
    db.commit()
