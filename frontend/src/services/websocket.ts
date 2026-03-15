import { useEffect, useRef, useState } from "react";

const WS_URL = (import.meta.env.VITE_WS_URL as string) ?? "ws://localhost:8000/ws";
const API_KEY = import.meta.env.VITE_API_KEY ?? "dev-key";

type WsStatus = "connecting" | "ok" | "closed";

export function useWebSocket() {
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [lastMessage, setLastMessage] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let alive = true;

    const connect = () => {
      try {
        setStatus("connecting");
        const ws = new WebSocket(`${WS_URL}?key=${API_KEY}`);
        wsRef.current = ws;
        ws.onopen = () => alive && setStatus("ok");
        ws.onclose = () => {
          alive && setStatus("closed");
          retryRef.current = setTimeout(connect, 1500);
        };
        ws.onerror = () => {
          alive && setStatus("closed");
          retryRef.current = setTimeout(connect, 1500);
        };
        ws.onmessage = (evt) => {
          try {
            setLastMessage(JSON.parse(evt.data));
          } catch {
            /* ignore parse errors */
          }
        };
      } catch {
        retryRef.current = setTimeout(connect, 1500);
      }
    };

    connect();
    return () => {
      alive = false;
      wsRef.current?.close();
      if (retryRef.current) clearTimeout(retryRef.current);
    };
  }, []);

  return { status, lastMessage };
}
