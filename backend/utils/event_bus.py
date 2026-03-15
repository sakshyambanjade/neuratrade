"""
Lightweight event bus.
- If REDIS_URL is set, publishes to Redis channel "events" for multi-process.
- Otherwise falls back to in-process broadcast.
"""
import asyncio
import json
import os
import threading
from typing import Callable, Optional

import redis

REDIS_URL = os.getenv("REDIS_URL", "")
CHANNEL = "events"

_redis_client: Optional[redis.Redis] = None
_sub_thread: Optional[threading.Thread] = None
_listeners: list[Callable[[dict], None]] = []


def _ensure_client():
    global _redis_client
    if REDIS_URL and not _redis_client:
        _redis_client = redis.Redis.from_url(REDIS_URL)
    return _redis_client


def publish(event: dict):
    client = _ensure_client()
    if client:
        client.publish(CHANNEL, json.dumps(event))
    else:
        # fallback: call listeners directly
        for fn in _listeners:
            try:
                fn(event)
            except Exception:
                pass


def subscribe(callback: Callable[[dict], None]):
    _listeners.append(callback)
    client = _ensure_client()
    if not client:
        return

    def _worker():
        pubsub = client.pubsub()
        pubsub.subscribe(CHANNEL)
        for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                callback(data)
            except Exception:
                continue

    global _sub_thread
    if _sub_thread and _sub_thread.is_alive():
        return
    _sub_thread = threading.Thread(target=_worker, daemon=True)
    _sub_thread.start()
