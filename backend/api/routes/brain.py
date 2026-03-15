from fastapi import APIRouter

router = APIRouter()


@router.get("/brain/status")
def brain_status():
    return {"prajnyavan": True, "memories": 0}
