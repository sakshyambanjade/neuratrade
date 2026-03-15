"""
Thin wrapper for Prajnyavan with retry and fail-open behavior.
"""
from functools import lru_cache
from typing import List
import httpx
from tenacity import retry, stop_after_attempt, wait_fixed
from config import BRAIN_URL, BRAIN_SECRET, USER_ID


@lru_cache(maxsize=1)
def _token() -> str:
    try:
        with httpx.Client(timeout=8) as client:
            resp = client.post(f"{BRAIN_URL}/auth/token", json={"user_id": USER_ID, "secret": BRAIN_SECRET})
            resp.raise_for_status()
            return resp.json().get("token", "")
    except Exception:
        return ""


def _headers():
    tok = _token()
    auth = f"Bearer {tok}" if tok else f"Bearer {BRAIN_SECRET}"
    return {"Authorization": auth}


@retry(wait=wait_fixed(1), stop=stop_after_attempt(3))
def store_decision(content: str, importance: float, tags: list[str]) -> str:
    payload = {
        "user_id": USER_ID,
        "content": content,
        "importance": importance,
        "tags": tags,
    }
    with httpx.Client(timeout=10) as client:
        resp = client.post(f"{BRAIN_URL}/memory/store", json=payload, headers=_headers())
        resp.raise_for_status()
        return resp.json().get("id", "")


@retry(wait=wait_fixed(1), stop=stop_after_attempt(3))
def update_outcome(memory_id: str, importance: float, suffix: str):
    payload = {"importance": importance, "content_append": suffix}
    with httpx.Client(timeout=10) as client:
        resp = client.post(f"{BRAIN_URL}/memory/update/{memory_id}", json=payload, headers=_headers())
        resp.raise_for_status()


def recall_similar(query: str, k: int = 8) -> List[dict]:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{BRAIN_URL}/memory/search", json={"user_id": USER_ID, "query": query, "k": k}, headers=_headers())
            resp.raise_for_status()
            return resp.json().get("items", [])
    except Exception:
        return []
