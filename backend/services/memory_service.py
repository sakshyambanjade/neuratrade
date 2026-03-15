"""
Thin wrapper for Prajnyavan SDK (prajnyavan==0.1.1) with fail-open behavior.
"""
import json
from functools import lru_cache
from typing import List

from tenacity import retry, stop_after_attempt, wait_fixed

from config import (
    PRAJ_BASE_URL,
    PRAJ_TOKEN,
    PRAJ_EMBED_PROVIDER,
    PRAJ_EMBED_MODEL,
    OPENAI_API_KEY,
    USER_ID,
)


def _client():
    try:
        from prajnyavan import MemoryClient, auto_client, get_token
    except Exception:
        return None

    try:
        return auto_client(user_id=USER_ID)
    except Exception:
        pass

    # Fallback: explicit client (works when auto discovery fails)
    provider = PRAJ_EMBED_PROVIDER or "local"
    if provider == "openai" and not OPENAI_API_KEY:
        provider = "local"
    token = PRAJ_TOKEN or ""
    if not token and PRAJ_BASE_URL:
        try:
            token = get_token(PRAJ_BASE_URL, user_id="backend")
        except Exception:
            token = ""
    try:
        return MemoryClient(
            base_url=PRAJ_BASE_URL or "http://127.0.0.1:9999",
            token=token or "dev-token",
            openai_api_key=OPENAI_API_KEY or None,
            embedding_provider=provider,
            embedding_model=PRAJ_EMBED_MODEL or None,
        )
    except Exception:
        return None


@retry(wait=wait_fixed(1), stop=stop_after_attempt(3))
def store_decision(content: str, importance: float, tags: list[str]) -> str:
    client = _client()
    if not client:
        return ""
    try:
        return client.store(USER_ID, content, importance=importance, tags=tags)
    except Exception:
        return ""


@retry(wait=wait_fixed(1), stop=stop_after_attempt(3))
def update_outcome(memory_id: str, importance: float, suffix: str):
    client = _client()
    if not client or not memory_id:
        return
    try:
        payload = {"importance": importance, "content_append": suffix}
        resp = client.session.post(
            f"{client.base_url}/memory/update/{memory_id}",
            data=json.dumps(payload),
            timeout=10,
        )
        resp.raise_for_status()
    except Exception:
        return


def recall_similar(query: str, k: int = 8) -> List[dict]:
    client = _client()
    if not client:
        return []
    try:
        return client.search(USER_ID, query, k=k)
    except Exception:
        return []
