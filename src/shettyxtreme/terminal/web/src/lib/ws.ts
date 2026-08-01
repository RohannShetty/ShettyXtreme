/** WebSocket client with auto-reconnect and a topic-based handler registry.
 *
 * Server broadcasts JSON frames shaped `{ "topic": string, "data": object }`
 * (see ws_manager.broadcast). Pings keep the connection warm; pong frames are
 * consumed here and never forwarded.
 */

export type WsMessageHandler = (data: unknown) => void;

const RECONNECT_MS = 2000;
const PING_MS = 30000;

const handlers = new Map<string, Set<WsMessageHandler>>();
let socket: WebSocket | null = null;
let keepAlive: number | undefined;
let retryTimer: number | undefined;
let stopped = true;

function wsUrl(): string {
  if (import.meta.env.DEV) {
    return "ws://127.0.0.1:8000/ws";
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws`;
}

function scheduleReconnect(): void {
  if (stopped || retryTimer !== undefined) return;
  retryTimer = window.setTimeout(() => {
    retryTimer = undefined;
    connect();
  }, RECONNECT_MS);
}

function clearTimers(): void {
  if (keepAlive !== undefined) {
    window.clearInterval(keepAlive);
    keepAlive = undefined;
  }
  if (retryTimer !== undefined) {
    window.clearTimeout(retryTimer);
    retryTimer = undefined;
  }
}

function dispatch(topic: string, data: unknown): void {
  const set = handlers.get(topic);
  if (!set) return;
  for (const handler of set) {
    try {
      handler(data);
    } catch {
      /* a handler must never break the socket */
    }
  }
}

export function connect(): void {
  if (!stopped) return;
  stopped = false;
  let ws: WebSocket;
  try {
    ws = new WebSocket(wsUrl());
  } catch {
    scheduleReconnect();
    return;
  }
  socket = ws;

  ws.onopen = () => {
    keepAlive = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, PING_MS);
  };

  ws.onmessage = (ev: MessageEvent) => {
    let frame: { topic?: unknown; data?: unknown } | null = null;
    try {
      frame = JSON.parse(String(ev.data)) as { topic?: unknown; data?: unknown };
    } catch {
      return;
    }
    if (!frame || typeof frame.topic !== "string") return;
    if (frame.topic === "pong") return;
    dispatch(frame.topic, frame.data);
  };

  ws.onerror = () => {
    try {
      ws.close();
    } catch {
      /* already closed */
    }
  };

  ws.onclose = () => {
    if (socket === ws) socket = null;
    clearTimers();
    scheduleReconnect();
  };
}

export function stop(): void {
  stopped = true;
  clearTimers();
  if (socket) {
    const ws = socket;
    socket = null;
    ws.onclose = null;
    ws.onerror = null;
    ws.onmessage = null;
    ws.onopen = null;
    try {
      ws.close();
    } catch {
      /* already closed */
    }
  }
}

export function onMessage(topic: string, handler: WsMessageHandler): () => void {
  let set = handlers.get(topic);
  if (!set) {
    set = new Set<WsMessageHandler>();
    handlers.set(topic, set);
  }
  set.add(handler);
  return () => {
    const current = handlers.get(topic);
    if (current) {
      current.delete(handler);
      if (current.size === 0) handlers.delete(topic);
    }
  };
}
