import httpx
from config import BINANCE_BASE, BRAIN_URL, OLLAMA_URL
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    status = {"ok": True, "ollama": False, "brain": False, "binance": False}
    async with httpx.AsyncClient(timeout=2) as client:
        try:
            await client.get(f"{OLLAMA_URL}/api/tags")
            status["ollama"] = True
        except Exception:
            status["ok"] = False
        try:
            await client.get(f"{BRAIN_URL}/health")
            status["brain"] = True
        except Exception:
            status["ok"] = False
        try:
            await client.get(f"{BINANCE_BASE}/api/v3/ping")
            status["binance"] = True
        except Exception:
            status["ok"] = False
    return status
