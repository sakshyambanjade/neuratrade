import httpx
from fastapi import APIRouter
from config import OLLAMA_URL, BRAIN_URL, BINANCE_BASE

router = APIRouter()


@router.get("/health")
def health():
    status = {"ok": True, "ollama": False, "brain": False, "binance": False}
    try:
        httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).raise_for_status()
        status["ollama"] = True
    except Exception:
        status["ok"] = False
    try:
        httpx.get(f"{BRAIN_URL}/health", timeout=2).raise_for_status()
        status["brain"] = True
    except Exception:
        status["ok"] = False
    try:
        httpx.get(f"{BINANCE_BASE}/api/v3/ping", timeout=2).raise_for_status()
        status["binance"] = True
    except Exception:
        status["ok"] = False
    return status
