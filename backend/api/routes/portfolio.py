from fastapi import APIRouter
from db.database import SessionLocal
from db import models

router = APIRouter()


@router.get("/portfolio")
def get_portfolio():
    with SessionLocal() as db:
        latest = (
            db.query(models.PortfolioSnapshot)
            .order_by(models.PortfolioSnapshot.ts.desc())
            .first()
        )
    if not latest:
        return {"cash": 10000, "btc": 0, "total_value": 10000, "daily_pnl": 0}
    return {
        "cash": latest.cash,
        "btc": latest.btc_held,
        "total_value": latest.total_value,
        "daily_pnl": latest.daily_pnl,
    }
