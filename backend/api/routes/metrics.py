import time

from fastapi import APIRouter

router = APIRouter()


@router.get("/metrics")
def metrics():
    return {"ts": int(time.time())}
