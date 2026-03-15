import time
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from db.database import init_db
from api.websocket import router as ws_router, manager
from api.routes import health, status, candles, trades, portfolio, brain, decisions
from config import ALLOWED_ORIGINS, API_KEY
from utils.logging import setup_logging

log = setup_logging()

app = FastAPI(title="Prajnyavan BTC Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def api_key_auth(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.on_event("startup")
def on_startup():
    init_db()
    log.info("DB initialized (SQLite WAL enabled)")


app.include_router(health.router, tags=["health"])
app.include_router(
    ws_router,
    tags=["ws"],
)
app.include_router(status.router, dependencies=[Depends(api_key_auth)], tags=["status"])
app.include_router(candles.router, dependencies=[Depends(api_key_auth)], tags=["candles"])
app.include_router(trades.router, dependencies=[Depends(api_key_auth)], tags=["trades"])
app.include_router(portfolio.router, dependencies=[Depends(api_key_auth)], tags=["portfolio"])
app.include_router(brain.router, dependencies=[Depends(api_key_auth)], tags=["brain"])
app.include_router(decisions.router, dependencies=[Depends(api_key_auth)], tags=["decisions"])


@app.get("/")
def root():
    return {"ok": True, "ts": int(time.time())}
