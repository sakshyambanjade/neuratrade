import { useEffect, useState } from "react";

const WS_URL = (import.meta.env.VITE_WS_URL as string) ?? "ws://localhost:8000/ws";
const API_KEY = import.meta.env.VITE_API_KEY ?? "dev-key";

type WsStatus = "connecting" | "ok" | "closed";

let sharedWs: WebSocket | null = null;
let sharedBackoff = 800;
const listeners = new Set<(data: any) => void>();
let statusState: WsStatus = "connecting";
const statusListeners = new Set<(s: WsStatus) => void>();
let retryTimer: ReturnType<typeof setTimeout> | null = null;

const notifyStatus = (s: WsStatus) => {
  statusState = s;
  statusListeners.forEach((fn) => fn(s));
};

const ensureSocket = () => {
  if (sharedWs && (sharedWs.readyState === WebSocket.OPEN || sharedWs.readyState === WebSocket.CONNECTING)) return;
  try {
    sharedWs = new WebSocket(`${WS_URL}?key=${API_KEY}`);
  } catch {
    scheduleReconnect();
    return;
  }
  notifyStatus("connecting");
  sharedWs.onopen = () => {
    sharedBackoff = 800;
    notifyStatus("ok");
  };
  sharedWs.onclose = () => {
    notifyStatus("closed");
    scheduleReconnect();
  };
  sharedWs.onerror = () => {
    notifyStatus("closed");
    scheduleReconnect();
  };
  sharedWs.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      listeners.forEach((fn) => fn(data));
    } catch {
      /* ignore */
    }
  };
};

const scheduleReconnect = () => {
  if (retryTimer) return;
  retryTimer = setTimeout(() => {
    retryTimer = null;
    sharedBackoff = Math.min(sharedBackoff * 1.7, 6000);
    ensureSocket();
  }, sharedBackoff);
};

export function useWebSocket() {
  const [status, setStatus] = useState<WsStatus>(statusState);
  const [lastMessage, setLastMessage] = useState<any>(null);

  useEffect(() => {
    const msgHandler = (data: any) => setLastMessage(data);
    const statusHandler = (s: WsStatus) => setStatus(s);
    listeners.add(msgHandler);
    statusListeners.add(statusHandler);
    ensureSocket();
    return () => {
      listeners.delete(msgHandler);
      statusListeners.delete(statusHandler);
    };
  }, []);

  return { status, lastMessage };
}
