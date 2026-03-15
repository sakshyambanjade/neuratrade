from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Header
from config import API_KEY, WS_PATH

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active.discard(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket(WS_PATH)
async def websocket_endpoint(websocket: WebSocket, x_api_key: str = Header(default="")):
    # Allow header or query param (?key=)
    key = x_api_key or websocket.query_params.get("key", "")
    if key != API_KEY:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive / ignore client messages
    except WebSocketDisconnect:
        manager.disconnect(websocket)
