# Prajnyavan BTC Trading – Scaffold

This repo now has:
- **backend/** FastAPI server + websocket hub + PM2-friendly trading loop skeleton with SQLite WAL, API key auth, risk gates, LLM fallback.
- **frontend/** React + Vite TypeScript shell that hydrates from REST and listens to live ticks over WebSocket.
- **RISK_REGISTER.md** Risks/mitigations from the build plan.

## Quick start (backend)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # edit keys before prod
uvicorn main:app --host 0.0.0.0 --port 8000
```
Trading loop (stub, 5‑min aligned): `python -m workers.trading_loop`

## Quick start (frontend)
```powershell
cd frontend
npm install
npm run dev  # http://localhost:5173
```
Configure `.env` (or Vite vars) with:
```
VITE_API_BASE=http://localhost:8000
VITE_API_KEY=dev-key
VITE_WS_URL=ws://localhost:8000/ws
```

## Notes
- SQLite runs in WAL mode with busy timeout; single DB file at `DB_PATH`.
- REST/WS require `x-api-key` (or `?key=` for WS).
- LLM JSON is validated with pydantic; falls back to rule-based HOLD/BUY/SELL if parse fails.
- Risk gates enforced before any trade: max open trades, max daily trades, drawdown, min confidence.
