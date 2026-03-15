from fastapi import APIRouter

router = APIRouter()


@router.get("/decisions")
def decisions():
    return []
