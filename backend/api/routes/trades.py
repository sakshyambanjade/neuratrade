from fastapi import APIRouter
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
