from fastapi import APIRouter
from services import memory_service

router = APIRouter()


@router.get("/brain/status")
def brain_status():
    return {"prajnyavan": True, "memories": 0}


@router.get("/brain/memories")
def brain_memories(query: str = "", k: int = 5):
    items = memory_service.recall_similar(query or "btc trade", k)
    return {"items": items, "query": query, "k": k}
