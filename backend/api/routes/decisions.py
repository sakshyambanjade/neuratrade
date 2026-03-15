from fastapi import APIRouter
from db.database import SessionLocal
from db import models

router = APIRouter()


@router.get("/decisions")
def decisions(limit: int = 20):
    with SessionLocal() as db:
        rows = (
            db.query(models.DecisionRecord)
            .order_by(models.DecisionRecord.ts.desc())
            .limit(limit)
            .all()
        )
    return [
        {
            "ts": r.ts,
            "action": r.action,
            "confidence": r.confidence,
            "reasoning": r.reasoning,
        }
        for r in rows
    ]
