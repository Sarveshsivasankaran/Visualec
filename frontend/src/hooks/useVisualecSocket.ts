import { useEffect, useRef, useState } from "react";
import { emptyState, SystemState } from "../types";
import { request } from "../api";

const WS = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

export function useVisualecSocket() {
  const [state, setState] = useState<SystemState>(emptyState);
  const [connected, setConnected] = useState(false);
  const retries = useRef(0);
  useEffect(() => {
    let socket: WebSocket | undefined;
    let timer: number | undefined;
    let active = true;
    const connect = () => {
      socket = new WebSocket(WS);
      socket.onopen = () => { retries.current = 0; setConnected(true); };
      socket.onmessage = (event) => { try { setState(JSON.parse(event.data)); } catch { /* heartbeat */ } };
      socket.onclose = () => {
        setConnected(false);
        if (active) timer = window.setTimeout(connect, Math.min(10_000, 700 * 2 ** retries.current++));
      };
    };
    connect();
    request<SystemState>("/api/system/status").then(setState).catch(()=>undefined);
    return () => { active = false; if (timer) clearTimeout(timer); socket?.close(); };
  }, []);
  return {state, connected, setState};
}
