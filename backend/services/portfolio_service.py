import json
import time
import uuid
from typing import Optional

from sqlalchemy import func

from db import models
from config import MAX_POSITION_PCT

INITIAL_CASH = 10000.0


def _ensure_snapshot(db, price: float) -> models.PortfolioSnapshot:
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
    snap.total_value = snap.cash + snap.btc_held * price
    return snap


def current_drawdown(db, price: float) -> float:
    snaps = db.query(models.PortfolioSnapshot).order_by(models.PortfolioSnapshot.ts.asc()).all()
    peak = 0.0
    dd = 0.0
    for s in snaps:
        val = s.total_value if s.total_value is not None else (s.cash or 0) + (s.btc_held or 0) * price
        if val > peak:
            peak = val
        if peak:
            dd = min(dd, (val - peak) / peak)
    return dd  # negative when drawdown, 0 when flat


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
    fill_price = price * 1.001  # 0.1% adverse slippage/fee
    size_btc = size_usdt / fill_price
    trade_id = f"tr_{uuid.uuid4().hex[:10]}"
    trade = models.Trade(
        id=trade_id,
        opened_at=int(time.time()),
        action="BUY",
        entry_price=fill_price,
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
    fill_price = price * 0.999  # 0.1% adverse slippage/fee on exit
    pnl_usdt = (fill_price - trade.entry_price) * trade.size_btc
    pnl_pct = pnl_usdt / trade.size_usdt if trade.size_usdt else 0
    trade.closed_at = int(time.time())
    trade.exit_price = fill_price
    trade.pnl_usdt = pnl_usdt
    trade.pnl_pct = pnl_pct  # decimal; frontend renders percent
    trade.close_reason = reason
    trade.status = "closed"
    snap = current_portfolio(db, fill_price)
    snap.cash += trade.size_usdt + pnl_usdt
    snap.btc_held -= trade.size_btc
    snap.total_value = snap.cash + snap.btc_held * fill_price
    db.merge(trade)
    db.merge(snap)
    db.commit()
    return trade


def snapshot(db, price: float):
    snap = current_portfolio(db, price)
    now = int(time.time())
    day_start = now - (now % 86400)
    first_today = (
        db.query(models.PortfolioSnapshot)
        .filter(models.PortfolioSnapshot.ts >= day_start)
        .order_by(models.PortfolioSnapshot.ts.asc())
        .first()
    )
    daily_pnl = 0.0
    if first_today:
        daily_pnl = snap.total_value - first_today.total_value
    new_snap = models.PortfolioSnapshot(
        ts=now,
        cash=snap.cash,
        btc_held=snap.btc_held,
        total_value=snap.total_value,
        daily_pnl=daily_pnl,
    )
    db.add(new_snap)
    db.commit()
