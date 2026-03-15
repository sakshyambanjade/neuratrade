from fastapi import APIRouter
import time

router = APIRouter()


@router.get("/metrics")
def metrics():
    return {"ts": int(time.time())}
