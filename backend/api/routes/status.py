import time
from fastapi import APIRouter
from services.market_service import latest_price
from db.database import SessionLocal
from db import models

router = APIRouter()


@router.get("/status")
def status():
    with SessionLocal() as db:
        trades = db.query(models.Trade).count()
        open_trades = db.query(models.Trade).filter(models.Trade.status == "open").count()
        last_decision = db.query(models.DecisionRecord).order_by(models.DecisionRecord.ts.desc()).first()
    return {
        "price": latest_price(),
        "timestamp": int(time.time()),
        "bot_status": "ok",
        "trade_count": trades,
        "open_trades": open_trades,
        "last_decision": last_decision.action if last_decision else None,
    }
