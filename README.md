# Prajnyavan BTC Trading – Scaffold

This repo now has:
- **backend/** FastAPI server + WebSocket hub + PM2-friendly trading loop with SQLite WAL, API key auth, risk gates, LLM fallback, optional Redis fanout.
- **frontend/** React + Vite TypeScript dashboard (candles with markers, trades, decisions, brain snippets) via REST + live WebSocket ticks.
- **RISK_REGISTER.md** Risks/mitigations from the build plan.

## Quick start (backend)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # edit keys before prod
uvicorn main:app --host 0.0.0.0 --port 8000
python -m workers.trading_loop   # 5-minute aligned loop, publishes WS events
```
Optional multi-process WS fanout: set `REDIS_URL=redis://localhost:6379` in `.env`.

## Quick start (frontend)
```powershell
cd frontend
npm install
npm run dev  # http://localhost:5173
```
Configure `.env` (or Vite vars):
```
VITE_API_BASE=http://localhost:8000
VITE_API_KEY=dev-key
VITE_WS_URL=ws://localhost:8000/ws
```

## Notes
- SQLite runs in WAL mode with busy timeout; single DB file at `DB_PATH`.
- REST/WS require `x-api-key` (or `?key=` for WS).
- LLM JSON validated with pydantic; fallback rules if parse fails.
- Risk gates: max open trades, max daily trades, drawdown, min confidence.
- Frontend shows live candles + markers, trades table, decisions list, portfolio stats, brain memory snippets.
