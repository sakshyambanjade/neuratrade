from fastapi import APIRouter
from db.database import SessionLocal
from db import models

router = APIRouter()


@router.get("/portfolio/snapshots")
def portfolio_snapshots(limit: int = 200):
    with SessionLocal() as db:
        rows = (
            db.query(models.PortfolioSnapshot)
            .order_by(models.PortfolioSnapshot.ts.desc())
            .limit(limit)
            .all()
        )
    return [
        {"ts": r.ts, "cash": r.cash, "btc": r.btc_held, "total_value": r.total_value, "daily_pnl": r.daily_pnl}
        for r in reversed(rows)
    ]
