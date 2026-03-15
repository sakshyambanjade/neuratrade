import time
from fastapi import APIRouter
from services.market_service import latest_price

router = APIRouter()


@router.get("/status")
def status():
    return {
        "price": latest_price(),
        "timestamp": int(time.time()),
        "bot_status": "idle",
    }
