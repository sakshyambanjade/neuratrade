import { useEffect, useMemo, useState } from "react";
import { format } from "date-fns";
import { getHealth, getStatus } from "./services/api";
import { useWebSocket } from "./services/websocket";
import "./style.css";

type TickEvent = {
  type: "tick";
  timestamp: number;
  price: number;
};

export default function App() {
  const [health, setHealth] = useState<string>("checking...");
  const [status, setStatus] = useState<any>(null);
  const [lastTick, setLastTick] = useState<TickEvent | null>(null);
  const { status: wsStatus, lastMessage } = useWebSocket();

  useEffect(() => {
    getHealth()
      .then(() => setHealth("ok"))
      .catch(() => setHealth("unavailable"));
    getStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (lastMessage?.type === "tick") {
      setLastTick(lastMessage as TickEvent);
    }
  }, [lastMessage]);

  const price = useMemo(() => lastTick?.price ?? status?.price ?? 0, [lastTick, status]);

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <div className="eyebrow">Backend</div>
          <div className="pill">{health}</div>
        </div>
        <div>
          <div className="eyebrow">WebSocket</div>
          <div className={`pill ${wsStatus}`}>{wsStatus}</div>
        </div>
        <div>
          <div className="eyebrow">BTC Price</div>
          <div className="price">${price?.toFixed(2)}</div>
          {lastTick && <div className="muted">tick @ {format(lastTick.timestamp * 1000, "HH:mm:ss")}</div>}
        </div>
      </header>
      <main className="panel">
        <h1>Trading Dashboard (stub)</h1>
        <p>This shell hydrates via REST then live WebSocket ticks.</p>
        <ul className="list">
          <li>REST /health → {health}</li>
          <li>REST /status → {status ? "ok" : "pending"}</li>
          <li>WS last event → {lastTick ? JSON.stringify(lastTick) : "none yet"}</li>
        </ul>
      </main>
    </div>
  );
}
