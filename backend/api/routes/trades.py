from fastapi import APIRouter, HTTPException
from db.database import SessionLocal
from db import models

router = APIRouter()


@router.get("/trades")
def list_trades(limit: int = 100):
    with SessionLocal() as db:
        rows = (
            db.query(models.Trade)
            .order_by(models.Trade.opened_at.desc())
            .limit(limit)
            .all()
        )
    return [
        {
            "id": r.id,
            "opened_at": r.opened_at,
            "closed_at": r.closed_at,
            "action": r.action,
            "entry_price": r.entry_price,
            "exit_price": r.exit_price,
            "pnl_pct": r.pnl_pct,
            "reasoning": r.reasoning,
            "status": r.status,
        }
        for r in rows
    ]


@router.get("/trades/{trade_id}")
def get_trade(trade_id: str):
    with SessionLocal() as db:
        row = db.query(models.Trade).filter(models.Trade.id == trade_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Trade not found")
        return {
            "id": row.id,
            "opened_at": row.opened_at,
            "closed_at": row.closed_at,
            "action": row.action,
            "entry_price": row.entry_price,
            "exit_price": row.exit_price,
            "pnl_pct": row.pnl_pct,
            "reasoning": row.reasoning,
            "status": row.status,
            "indicator_snapshot": row.indicator_snapshot_dict(),
        }
