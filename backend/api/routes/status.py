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
    return {
        "price": latest_price(),
        "timestamp": int(time.time()),
        "bot_status": "ok",
        "trade_count": trades,
    }
