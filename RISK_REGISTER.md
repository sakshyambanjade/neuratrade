# Prajnyavan BTC Trading System — Risk Register

Date: 2026-03-15  
Scope: Paper-trading stack (FastAPI backend, PM2 workers, Prajnyavan/Ollama brain, React/Vite dashboard).

## Risks
| ID | Sev | Area | Impact | Evidence (plan) | Mitigation / Next Action |
|----|-----|------|--------|-----------------|--------------------------|
| R1 | P1 | Data & Market Feed | 5‑min loop can drift; stale candles skew indicators. | Phase 1 cadence; no clock sync noted. | Enforce NTP; align ticks to wall clock; record fetch_ts vs candle_ts; drop/flag late data. |
| R2 | P1 | Trading Loop | Hardcoded RSI/MACD strategy lacks sizing/drawdown limits → runaway risk. | Phase 2 rule; no risk_service yet. | Add risk_service gates: max position %, daily trade cap, max open trades, max drawdown; block trade if violated. |
| R3 | P1 | Persistence | SQLite used by bot + API + PM2 without WAL/locking plan → “database is locked”, event loss. | Schema + PM2 multi-process use. | Enable WAL + busy_timeout; prefer single-writer queue; wrap writes in API process or message bus. |
| R4 | P1 | APIs/WebSocket | No auth on REST/WS; FastAPI is single door exposed via Nginx. | “Single rule: FastAPI is the ONLY door”; port map. | Add JWT/API key; restrict CORS; IP-allowlist /ws early; bind services to localhost. |
| R5 | P1 | LLM/Brain Integration | JSON from Ollama/tinyllama not validated; bad parse stalls loop. | Phase 4 decision_service. | Pydantic schema; retry with constrained sampling; fallback to deterministic rule; log/store raw prompt+response. |
| R6 | P1 | Security & Ops | Secrets (brain, feeds) in config.py; no vault/env guidance. | config.py mention only. | Load from env/.env.sample; keep secrets out of VCS; secure PM2 env; rotate keys. |
| R7 | P2 | Data Quality | Binance→CoinGecko fallback may mix volumes; indicators inconsistent. | Phase 1 fallback. | Tag source in candles; avoid mixing within window; overlap check; reject inconsistent volumes. |
| R8 | P2 | Trading Loop | Restart recovery unclear; open trades may be lost between open and DB write. | No reopen logic noted. | Treat trade “opening” until DB ack; on boot reconcile open trades; idempotent writes with status field. |
| R9 | P2 | Persistence | Single trades table may not cover open positions/partial fills or multi-asset. | Trades schema only. | Add open_positions or enforce single-open invariant; add indices on ts/status. |
| R10 | P2 | APIs/WebSocket | No backpressure/replay; WS clients may leak; late joiners miss events. | websocket.py description. | Heartbeat + cleanup; buffer last N events for resync; seq numbers or socket.io ack. |
| R11 | P2 | Frontend | Timestamp/unit mismatch (sec vs ms) can misplace markers; hydration path unspecified. | CandleChart example uses raw timestamp. | Standardize epoch seconds; convert before chart; hydrate with REST then live WS; add unit tests. |
| R12 | P2 | LLM/Brain | Brain writes lack retry/backoff; outage drops learning. | memory_service pattern. | Queue + retry DLQ; surface failures in /health; idempotent updates. |
| R13 | P2 | Testing & Rollout | 24–48h soak mentioned but no automated alerts or thresholds. | Phase tests. | Cron health pings; alerts if tick >7m, WS clients zero, DB lock error; soak script. |
| R14 | P3 | Security & Ops | Prajnyavan/Ollama ports exposed; firewall not mentioned. | Port map. | UFW/iptables restrict to localhost/Nginx; auth or bind to 127.0.0.1. |
| R15 | P3 | Persistence | No DB backup/rotation; corruption risk over time. | Schema section. | Nightly sqlite3 .backup with 7-day retention; WAL checkpoint. |
| R16 | P3 | Frontend | No offline/WS-fail UX; mobile layout unverified. | Frontend phases. | WS status banner; cached last candles; manual refresh; mobile smoke test. |
| R17 | P3 | Data Feed | No handling of Binance maintenance/delist; bot may stall. | Feed section. | Secondary provider list; exponential backoff; pause trading when feed unhealthy; alert. |

## Quick Wins (do these first)
1. Turn on SQLite WAL + busy_timeout; centralize writes behind a queue/single writer.  
2. Add auth + CORS restrictions to FastAPI/WS; bind Prajnyavan/Ollama to localhost.  
3. Implement risk_service gates (position cap, daily trade cap, max drawdown, max open trades).  
4. Validate LLM JSON with pydantic; retry then fallback to deterministic rules on parse failure.  
5. Add heartbeats/alerts: tick >7 min, DB lock errors, WS clients zero, brain write failures.

## Phase-Aligned Follow-ups
- **Before Phase 2 end:** NTP sync; tag candle source; enable WAL; boot reconciliation of open trades.  
- **Before Phase 3 end:** Auth/CORS; WS heartbeat + cleanup; response schema versioning; idempotent DB writes.  
- **Before Phase 4 end:** Pydantic validation + retry/backoff for LLM/brain; fallback path; log raw prompt/response.  
- **Before Phase 5 end:** Enforce risk limits in loop; crash/restart replay; 48h soak with alerts.  
- **Frontend phases:** Standardize timestamps; REST hydration then WS; WS status UI; marker unit tests; mobile check.
