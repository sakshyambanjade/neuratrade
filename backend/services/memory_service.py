"""
Thin wrapper for Prajnyavan with retry and fail-open behavior.
"""
from typing import List
import httpx
from tenacity import retry, stop_after_attempt, wait_fixed
from config import BRAIN_URL, BRAIN_SECRET, USER_ID

HEADERS = {"Authorization": f"Bearer {BRAIN_SECRET}"}


@retry(wait=wait_fixed(1), stop=stop_after_attempt(3))
def store_decision(content: str, importance: float, tags: list[str]) -> str:
    payload = {
        "user_id": USER_ID,
        "content": content,
        "importance": importance,
        "tags": tags,
    }
    with httpx.Client(timeout=10) as client:
        resp = client.post(f"{BRAIN_URL}/mas/store", json=payload, headers=HEADERS)
        resp.raise_for_status()
        return resp.json().get("id", "")


@retry(wait=wait_fixed(1), stop=stop_after_attempt(3))
def update_outcome(memory_id: str, importance: float, suffix: str):
    payload = {"importance": importance, "content_append": suffix}
    with httpx.Client(timeout=10) as client:
        resp = client.post(f"{BRAIN_URL}/mas/update/{memory_id}", json=payload, headers=HEADERS)
        resp.raise_for_status()


def recall_similar(query: str, k: int = 8) -> List[dict]:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{BRAIN_URL}/mas/search", params={"user_id": USER_ID, "q": query, "k": k}, headers=HEADERS)
            resp.raise_for_status()
            return resp.json().get("items", [])
    except Exception:
        return []
