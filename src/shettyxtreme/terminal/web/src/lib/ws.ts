/** WebSocket client with auto-reconnect and a topic-based handler registry.
 *
 * Server broadcasts JSON frames shaped `{ "topic": string, "data": object }`
 * (see ws_manager.broadcast). On connect (and whenever the handler registry
 * changes) this client sends a subscribe frame declaring its topics:
 * `{ "type": "subscribe", "topics": [...] }`. Pings keep the connection
 * warm; pong frames are consumed here and never forwarded.
 *
 * Live topics (subscribe via onMessage(topic, handler)):
 *   tick              — watchlist LTP updates (WatchlistProjection)
 *   position          — position updates + live P&L (PositionProjection)
 *   risk              — risk summary changes (RiskProjection)
 *   alert             — risk/system alerts (RiskProjection/AlertProjection)
 *   regime, signal    — intelligence updates (IntelligenceProjection)
 *   connection        — data-socket connection state (HealthProjection)
 *   scanner_finding   — opportunity findings (ScannerProjection)
 *   proposal          — proposal lifecycle: {action, proposal} (P4)
 *   order             — order lifecycle: {action, order} (P4)
 *   research, knowledge, theme, color-convention, scanner-thresholds
 */

export type WsMessageHandler = (data: unknown) => void;

/** P1-2.4: browser-WS connection state (local to this tab). */
export type ConnectionState = "open" | "closed" | "reconnecting";

/** Callbacks for browser-WS open/close/error events. */
type ConnectionChangeHandler = (state: ConnectionState) => void;
const connectionHandlers = new Set<ConnectionChangeHandler>();

/** Live market-data tick broadcast by the backend (WatchlistProjection).
 *
 * Chain fields (oi/strike/option_type) ride the wire so ChainGrid can update
 * live without REST polling; they are null for non-option symbols (indexes,
 * equities). iv is intentionally absent — the HSM symbol-update feed has no
 * IV field, so IV stays REST-polled. */
export type TickPayload = {
  symbol: string;
  ltp: number;
  change_pct: number;
  volume: number;
  oi: number | null;
  strike: number | null;
  option_type: string | null;
};

/** P4: proposal lifecycle frame on the `proposal` topic (ProposalProjection).
 *
 * `action` is one of "created" | "approved" | "rejected" | "expired";
 * `proposal` mirrors the REST /api/execution/proposals shape. */
export type ProposalPayload = {
  action: "created" | "approved" | "rejected" | "expired" | string;
  proposal: {
    id: string;
    symbol: string;
    exchange: string;
    side: string;
    quantity: number;
    status: string; // PENDING / APPROVED / REJECTED / EXPIRED
    reason: string;
    timestamp: string | null;
    confidence?: number | null;
    entry_premium?: number | null;
    stop_loss?: number | null;
    target?: number | null;
    rationale?: string | null;
    [key: string]: unknown;
  };
};

/** P4: order lifecycle frame on the `order` topic (OrderWSProjection).
 *
 * `action` is one of "placed" | "filled" | "rejected" | "cancelled";
 * `order` mirrors the REST /api/execution/orders shape. */
export type OrderPayload = {
  action: "placed" | "filled" | "rejected" | "cancelled" | string;
  order: {
    order_id: string;
    symbol: string;
    exchange: string;
    side: string;
    order_type: string;
    quantity: number;
    price: number;
    status: string;
    filled_quantity?: number;
    average_price?: number;
    created_at?: string | null;
    [key: string]: unknown;
  };
};

/** Reconnect policy: exponential backoff (2s → 4s → 8s → 16s → 30s cap)
 *  with ±20% random jitter so a fleet of clients never thundering-herds the
 *  server after an outage. The attempt counter resets on a successful open. */
const RECONNECT_BASE_MS = 2000;
const RECONNECT_MAX_MS = 30000;
const PING_MS = 30000;

const handlers = new Map<string, Set<WsMessageHandler>>();
const subscribedTopics = new Set<string>();
let socket: WebSocket | null = null;
let keepAlive: number | undefined;
let retryTimer: number | undefined;
let stopped = true;
let reconnectAttempt = 0;

function wsUrl(): string {
  if (import.meta.env.DEV) {
    return "ws://127.0.0.1:8000/ws";
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws`;
}

function reconnectDelay(): number {
  const exp = Math.min(RECONNECT_BASE_MS * 2 ** reconnectAttempt, RECONNECT_MAX_MS);
  const jitter = 0.8 + Math.random() * 0.4; // ±20%
  return Math.round(exp * jitter);
}

function scheduleReconnect(): void {
  if (stopped || retryTimer !== undefined) return;
  const delay = reconnectDelay();
  reconnectAttempt += 1;
  retryTimer = window.setTimeout(() => {
    retryTimer = undefined;
    connect();
  }, delay);
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

function sendSubscribe(): void {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "subscribe", topics: [...subscribedTopics] }));
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
    reconnectAttempt = 0;
    keepAlive = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, PING_MS);
    sendSubscribe();
    // P1-2.4: notify connection listeners.
    for (const cb of connectionHandlers) {
      try { cb("open"); } catch { /* never break the socket */ }
    }
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
    // P1-2.4: notify connection listeners before closing.
    for (const cb of connectionHandlers) {
      try { cb("closed"); } catch { /* never break the socket */ }
    }
    try {
      ws.close();
    } catch {
      /* already closed */
    }
  };

  ws.onclose = () => {
    if (socket === ws) socket = null;
    clearTimers();
    // P1-2.4: notify connection listeners.
    for (const cb of connectionHandlers) {
      try { cb("reconnecting"); } catch { /* never break the socket */ }
    }
    scheduleReconnect();
  };
}

export function stop(): void {
  stopped = true;
  reconnectAttempt = 0;
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

/** P1-2.4: register a callback for browser-WS open/close events. */
export function onConnectionChange(handler: ConnectionChangeHandler): () => void {
  connectionHandlers.add(handler);
  return () => { connectionHandlers.delete(handler); };
}

/** P1-2.4: true when the browser WS socket is open. */
export function isWsConnected(): boolean {
  return socket !== null && socket.readyState === WebSocket.OPEN;
}

export function onMessage(topic: string, handler: WsMessageHandler): () => void {
  let set = handlers.get(topic);
  if (!set) {
    set = new Set<WsMessageHandler>();
    handlers.set(topic, set);
  }
  set.add(handler);
  subscribedTopics.add(topic);
  sendSubscribe();
  return () => {
    const current = handlers.get(topic);
    if (current) {
      current.delete(handler);
      if (current.size === 0) {
        handlers.delete(topic);
        subscribedTopics.delete(topic);
        sendSubscribe();
      }
    }
  };
}
