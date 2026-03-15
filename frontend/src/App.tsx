import { useEffect, useMemo, useRef, useState } from "react";
import { format } from "date-fns";
import { AreaChart, Area, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { createChart, CandlestickSeries, createSeriesMarkers } from "lightweight-charts";
import type { IChartApi, ISeriesApi, ISeriesMarkersPluginApi, Time } from "lightweight-charts";
import {
  getHealth,
  getStatus,
  getCandles,
  getTrades,
  getIndicators,
  getPortfolio,
  getDecisions,
  getBrainStatus,
  getBrainMemories,
  getSnapshots,
} from "./services/api";
import { useWebSocket } from "./services/websocket";
import "./style.css";
import type { Candle, Trade, Decision, Indicators, Snapshot } from "./types/trading";

type TickEvent = {
  type: "tick";
  timestamp: number;
  price: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
};

export default function App() {
  const [health, setHealth] = useState<string>("checking...");
  const [status, setStatus] = useState<any>(null);
  const [lastTick, setLastTick] = useState<TickEvent | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [brain, setBrain] = useState<any>(null);
  const [memories, setMemories] = useState<any[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartObj = useRef<IChartApi | null>(null);
  const candleSeries = useRef<ISeriesApi<"Candlestick", Time> | null>(null);
  const seriesMarkers = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const markers = useRef<any[]>([]);
  const { status: wsStatus, lastMessage } = useWebSocket();
  const [noCandles, setNoCandles] = useState(false);

  useEffect(() => {
    getHealth().then(() => setHealth("ok")).catch(() => setHealth("unavailable"));
    getStatus().then(setStatus).catch(() => setStatus(null));
    getCandles().then((candles: Candle[]) => initChart(candles));
    getTrades().then((t) => { setTrades(t); refreshMarkers(t); }).catch(() => setTrades([]));
    getIndicators().then(setIndicators).catch(() => setIndicators(null));
    getPortfolio().then(setPortfolio).catch(() => setPortfolio(null));
    getDecisions().then(setDecisions).catch(() => setDecisions([]));
    getBrainStatus().then(setBrain).catch(() => setBrain(null));
    getBrainMemories("", 5).then((d) => setMemories(d.items || [])).catch(() => setMemories([]));
    getSnapshots().then(setSnapshots).catch(() => setSnapshots([]));
  }, []);

  useEffect(() => {
    if (lastMessage?.type === "tick") {
      setLastTick(lastMessage as TickEvent);
      setIndicators((prev) => ({ ...(prev || {}), ...lastMessage, ts: lastMessage.timestamp } as any));
      if (candleSeries.current && lastMessage.price) {
        candleSeries.current.update({
          time: lastMessage.timestamp,
          open: lastMessage.open ?? lastMessage.price,
          high: lastMessage.high ?? lastMessage.price,
          low: lastMessage.low ?? lastMessage.price,
          close: lastMessage.price,
        });
      }
    }
    if (lastMessage?.type === "trade_opened") {
      const t = lastMessage as any;
      setTrades((prev) => [t, ...prev].slice(0, 100));
      addMarker(t, "open");
    }
    if (lastMessage?.type === "trade_closed") {
      const t = lastMessage as any;
      setTrades((prev) => prev.map((x) => (x.id === t.id ? { ...x, ...t, status: "closed" } : x)));
      addMarker(t, "close");
    }
    if (lastMessage?.type === "decision") {
      const d = lastMessage as any;
      setDecisions((prev) => [{ ts: d.timestamp, action: d.action, confidence: d.confidence, reasoning: d.reasoning }, ...prev].slice(0, 30));
    }
  }, [lastMessage]);

  // Refresh data when WS connects (helps initial hydrate)
  useEffect(() => {
    if (wsStatus === "ok") {
      getStatus().then(setStatus).catch(() => {});
      getCandles().then((c: Candle[]) => {
        initChart(c);
        if (!c.length) setNoCandles(true);
      }).catch(() => {});
    }
  }, [wsStatus]);

  const price = useMemo(() => lastTick?.price ?? status?.price ?? 0, [lastTick, status]);
  const wsBadge = wsStatus === "ok" ? "badge success" : wsStatus === "connecting" ? "badge warn" : "badge danger";

  const initChart = (candles: Candle[]) => {
    if (!chartRef.current) return;
    if (!chartObj.current) {
      const width = chartRef.current.clientWidth || 920;
      const api = createChart(chartRef.current, {
        width,
        height: 340,
        layout: { background: { color: "#0e142b" }, textColor: "#d8e0ff" },
        grid: { vertLines: { color: "#1f2a4a" }, horzLines: { color: "#1f2a4a" } },
        timeScale: { timeVisible: true, secondsVisible: false },
      });
      chartObj.current = api;
      candleSeries.current = api.addSeries(CandlestickSeries, {
        upColor: "#16c784",
        downColor: "#ef4444",
        borderUpColor: "#16c784",
        borderDownColor: "#ef4444",
        wickUpColor: "#16c784",
        wickDownColor: "#ef4444",
      });
      seriesMarkers.current = createSeriesMarkers(candleSeries.current, []);
      const handleResize = () => {
        if (chartRef.current && chartObj.current) {
          chartObj.current.resize(chartRef.current.clientWidth || width, 340);
        }
      };
      window.addEventListener("resize", handleResize);
    }
    if (candles.length && candleSeries.current) {
      setNoCandles(false);
      candleSeries.current.setData(
        candles.map((c) => ({
          time: c.time as any,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        })),
      );
      refreshMarkers(trades);
    } else {
      setNoCandles(true);
    }
  };

  const refreshMarkers = (tradeList: Trade[]) => {
    markers.current = tradeList
      .filter((t) => t.opened_at)
      .map((t) => ({
        time: t.opened_at as any,
        position: t.action === "BUY" ? "belowBar" : "aboveBar",
        color: t.pnl_pct && t.pnl_pct < 0 ? "#ef4444" : "#16c784",
        shape: t.action === "BUY" ? "arrowUp" : "arrowDown",
        text: `${t.action} ${t.entry_price?.toFixed(0)}`,
      }));
    seriesMarkers.current?.setMarkers(markers.current);
  };

  const addMarker = (trade: any, kind: "open" | "close") => {
    markers.current = [
      {
        time: (trade.timestamp || trade.opened_at) as any,
        position: kind === "open" ? "belowBar" : "aboveBar",
        color: kind === "open" ? "#0ea5e9" : (trade.pnl_pct ?? 0) >= 0 ? "#16c784" : "#ef4444",
        shape: kind === "open" ? "arrowUp" : "arrowDown",
        text: kind === "open" ? `BUY ${trade.entry_price?.toFixed(0)}` : `EXIT ${trade.exit_price?.toFixed(0)}`,
      },
      ...markers.current,
    ].slice(0, 200);
    seriesMarkers.current?.setMarkers(markers.current);
  };

  useEffect(() => {
    if (trades.length && candleSeries.current) {
      refreshMarkers(trades);
    }
  }, [trades]);

  return (
    <div className="page">
      <header className="hero">
        <div>
          <div className="eyebrow">Backend</div>
          <span className={`badge ${health === "ok" ? "success" : "danger"}`}>{health}</span>
        </div>
        <div>
          <div className="eyebrow">WebSocket</div>
          <span className={wsBadge}>{wsStatus}</span>
        </div>
        <div>
          <div className="eyebrow">BTC Price</div>
          <div className="price">${price?.toFixed(2)}</div>
          {lastTick && <div className="muted">tick @ {format(lastTick.timestamp * 1000, "HH:mm:ss")}</div>}
        </div>
        <div>
          <div className="eyebrow">Open Trades</div>
          <div className="price">{status?.open_trades ?? 0}</div>
        </div>
      </header>

      <section className="grid two">
        <main className="panel">
          <div className="panel-head">
            <h1>Live BTC Candles</h1>
            <div className="muted">Markers show buys/exits</div>
          </div>
          <div className="chart-wrap">
            <div ref={chartRef} className="chart" />
            {noCandles && <div className="chart-placeholder">No candles yet</div>}
          </div>
        </main>

        <aside className="panel side">
          <div className="stat">
            <div className="label">Portfolio Value</div>
            <div className="value">${portfolio?.total_value?.toFixed(2) ?? "—"}</div>
            <div className="muted">
              Cash ${portfolio?.cash?.toFixed(2) ?? "—"} · BTC {portfolio?.btc_held?.toFixed?.(4) ?? "—"}
            </div>
            {portfolio?.open_trade && (
              <div className="muted">Open #{portfolio.open_trade.id} @ ${portfolio.open_trade.entry_price?.toFixed(0)}</div>
            )}
          </div>
          <div className="stat pills">
            <div className="label">Indicators</div>
            <div className="pill tight">RSI {indicators?.rsi?.toFixed(1) ?? "—"}</div>
            <div className="pill tight">MACD {indicators?.macd?.toFixed(4) ?? "—"}</div>
            <div className="pill tight">EMA9 {indicators?.ema9?.toFixed(2) ?? "—"}</div>
            <div className="pill tight">EMA21 {indicators?.ema21?.toFixed(2) ?? "—"}</div>
          </div>
          <div className="stat">
            <div className="label">Brain</div>
            <div className="muted">Status: {brain?.prajnyavan ? "online" : "offline"}</div>
            <div className="muted">Memories: {brain?.memories ?? "—"}</div>
          </div>
        </aside>
      </section>

      <section className="grid two">
        <div className="panel">
          <div className="panel-head">
            <h2>Recent Trades</h2>
            <div className="muted">{trades.length} rows</div>
          </div>
          {trades.length === 0 ? (
            <p className="muted">No trades yet.</p>
          ) : (
            <div className="table">
              <div className="row head">
                <span>Time</span>
                <span>Action</span>
                <span>Entry</span>
                <span>Status</span>
                <span>PnL %</span>
              </div>
              {trades.map((t) => (
                <div className="row" key={t.id}>
                  <span>{format((t.opened_at || 0) * 1000, "MM-dd HH:mm")}</span>
                  <span className={t.action === "BUY" ? "pos" : "neg"}>{t.action}</span>
                  <span>${t.entry_price?.toFixed(2)}</span>
                  <span>{t.status ?? "open"}</span>
                  <span className={(t.pnl_pct ?? 0) >= 0 ? "pos" : "neg"}>{t.pnl_pct !== undefined ? (t.pnl_pct * 100).toFixed(2) : "—"}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-head">
            <h2>Decisions</h2>
            <div className="muted">Last {decisions.length}</div>
          </div>
          {decisions.slice(0, 10).map((d, i) => (
            <div className="card-line" key={i}>
              <div>
                <div className="eyebrow">{format(d.ts * 1000, "MM-dd HH:mm:ss")}</div>
                <div className="label">{d.action}</div>
              </div>
              <div className="muted">conf {d.confidence.toFixed(2)}</div>
              <div className="reason">{d.reasoning}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid two">
        <div className="panel">
          <div className="panel-head">
            <h2>Equity Curve</h2>
            <div className="muted">Last {snapshots.length} points</div>
          </div>
          {snapshots.length === 0 ? (
            <p className="muted">No snapshots yet.</p>
          ) : (
            <div style={{ width: "100%", height: 240, minWidth: 320 }}>
              <ResponsiveContainer>
                <AreaChart data={snapshots}>
                  <XAxis dataKey="ts" tickFormatter={(t) => format(t * 1000, "MM-dd")} />
                  <YAxis tickFormatter={(v) => `$${Math.round(v)}`} />
                  <Tooltip
                    contentStyle={{ background: "#0f172e", border: "1px solid #1f2a4a" }}
                    labelFormatter={(t) => format((t as number) * 1000, "MM-dd HH:mm")}
                    formatter={(value: any) => [`$${Number(value).toFixed(2)}`, "Equity"]}
                  />
                  <Legend />
                  <Area type="monotone" dataKey="total_value" stroke="#16c784" fill="#0f3122" strokeWidth={2} name="Equity" />
                  <Area type="monotone" dataKey="cash" stroke="#38bdf8" fill="#0b1f33" strokeWidth={1} name="Cash" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-head">
            <h2>Memories</h2>
            <div className="muted">Top recalls</div>
          </div>
          {memories.length === 0 ? (
            <p className="muted">None loaded.</p>
          ) : (
            <div className="mem-grid">
              {memories.map((m, idx) => (
                <div className="mem-card" key={idx}>
                  <div className="eyebrow">{m.category ?? "memory"}</div>
                  <div className="reason">{m.content ?? ""}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
