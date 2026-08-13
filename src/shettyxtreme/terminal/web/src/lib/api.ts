/** Typed fetch helpers for the ShettyXtreme Terminal API. */

import type { Theme } from "./theme";
import type { ColorConvention } from "./color-convention";

type JsonError = { detail?: unknown; message?: string };

const FETCH_TIMEOUT_MS = 10000;

/** fetch with an AbortController deadline. A stalled request aborts after
 *  FETCH_TIMEOUT_MS instead of hanging forever (in-flight requests used to
 *  pile up); the caller maps the AbortError to "Request timeout". */
async function fetchWithTimeout(path: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(path, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === "AbortError";
}

async function describeError(resp: Response): Promise<string> {
  const fallback = `Request to ${resp.url || resp.statusText} failed (HTTP ${resp.status})`;
  try {
    const body = (await resp.json()) as JsonError;
    if (typeof body.message === "string" && body.message) {
      return body.message;
    }
    if (typeof body.detail === "string" && body.detail) {
      return body.detail;
    }
  } catch {
    /* body not JSON — use fallback */
  }
  return fallback;
}

async function request<T>(
  path: string,
  method: string,
  headers?: Record<string, string>,
): Promise<T> {
  let resp: Response;
  try {
    resp = await fetchWithTimeout(path, { method, credentials: "same-origin", headers });
  } catch (err) {
    if (isAbortError(err)) throw new Error("Request timeout");
    throw new Error(`Network error reaching ${path}`);
  }
  if (!resp.ok) {
    throw new Error(await describeError(resp));
  }
  return (await resp.json()) as T;
}

export async function get<T>(path: string): Promise<T> {
  return request<T>(path, "GET");
}

export async function post<T>(path: string, headers?: Record<string, string>): Promise<T> {
  return request<T>(path, "POST", headers);
}

export async function del(path: string): Promise<void> {
  let resp: Response;
  try {
    resp = await fetchWithTimeout(path, { method: "DELETE", credentials: "same-origin" });
  } catch (err) {
    if (isAbortError(err)) throw new Error("Request timeout");
    throw new Error(`Network error reaching ${path}`);
  }
  if (!resp.ok) {
    throw new Error(await describeError(resp));
  }
}

export async function postBody<T>(path: string, body: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetchWithTimeout(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    if (isAbortError(err)) throw new Error("Request timeout");
    throw new Error(`Network error reaching ${path}`);
  }
  if (!resp.ok) {
    throw new Error(await describeError(resp));
  }
  return (await resp.json()) as T;
}

export async function putBody<T>(path: string, body: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetchWithTimeout(path, {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    if (isAbortError(err)) throw new Error("Request timeout");
    throw new Error(`Network error reaching ${path}`);
  }
  if (!resp.ok) {
    throw new Error(await describeError(resp));
  }
  return (await resp.json()) as T;
}

export type ResearchLens = { name: string; description: string };
export type ResearchToolDef = {
  name: string;
  description: string;
  params_schema: Record<string, unknown>;
};
export type ResearchEvidence = {
  item: string;
  source: string;
  unsourced: boolean;
};
export type ResearchBrief = {
  brief_id: string;
  lens: string;
  as_of: string;
  instruments: string[];
  direction: number;
  confidence: number;
  thesis: string;
  rationale: string;
  evidence: ResearchEvidence[];
  risks: string[];
  validity_window_minutes: number;
  status: string;
  outcome: string | null;
  decided_at: string | null;
  regime_at_decision: string | null;
  expired: boolean;
};
export type ResearchRunRequest = {
  lenses?: string[] | null;
  context?: Record<string, string> | null;
  tools?: string[] | null;
};
export type ResearchRunResult = {
  lens: string;
  brief: ResearchBrief | null;
  error: string | null;
};
export type ResearchRunResponse = { results: ResearchRunResult[] };
export type ResearchBriefListResponse = { briefs: ResearchBrief[] };
export type ResearchSchedulerStatus = {
  enabled: boolean;
  interval_minutes: number;
  lenses: string[] | null;
  tools: string[] | null;
  next_run_at: string | null;
  last_run_at: string | null;
  last_result: string | null;
};
export type ResearchDecisionResponse = { brief_id: string; status: string };
export type ResearchScoringItem = {
  lens: string;
  total: number;
  decided: number;
  with_outcome: number;
  win_rate: number;
  avg_confidence: number;
};

// --- Knowledge layer (Phase 4) ---

export type KnowledgeTag = { tag: string; kind: string };
export type KnowledgeNoteRequest = {
  title: string;
  body: string;
};
export type KnowledgeDoc = {
  doc_id: string;
  kind: string;
  source_ref: string;
  payload: Record<string, unknown>;
  status: string;
  created_at: string | null;
  activated_at: string | null;
  tags: KnowledgeTag[];
};
export type KnowledgeSearchHit = {
  doc_id: string;
  kind: string;
  source_ref: string;
  status: string;
  title: string;
  snippet: string;
  tags: KnowledgeTag[];
  bm25_score: number;
};
export type KnowledgeSearchResponse = { hits: KnowledgeSearchHit[] };
export type KnowledgeListResponse = { docs: KnowledgeDoc[] };
export type KnowledgeStatusResponse = {
  docs: number;
  proposed: number;
  activated: number;
  tags: number;
  last_sync_at: string | null;
  last_sync_result: "success" | "partial" | "failed" | null;
};
export type KnowledgeSyncResponse = {
  ingested: number;
  skipped_undecided: number;
  skipped_duplicate: number;
  error: string | null;
};

// --- Symbol Search (P1-2.3) ---

export type SymbolSearchHit = {
  internal_symbol: string;
  fyers_symbol: string;
  exchange: string;
  instrument_type: string;
  expiry: string | null;
  strike: number | null;
  option_type: string | null;
  lot_size: number | null;
  tick_size: number | null;
};

export type SymbolSearchResponse = {
  query: string;
  canonical: string;
  hits: SymbolSearchHit[];
};

// --- Analytics (Phase 4) ---

export type CalibrationPoint = {
  conviction_bin: [number, number];
  actual_win_rate: number;
  sample_size: number;
  confidence_interval: [number, number];
};
export type ScorecardMetric = {
  key: string;
  label: string;
  value: number | boolean | string | null;
  unit: string | null;
  available: boolean;
  note: string | null;
};
export type RegimeRow = {
  regime: string;
  decided: number;
  with_outcome: number;
  win_rate: number;
};
export type ScorecardResponse = {
  reliable_calibration: boolean;
  metrics: ScorecardMetric[];
  by_regime: RegimeRow[];
  calibration: CalibrationPoint[];
  current_regime: string | null;
};
export type SessionRecord = {
  session_id: string;
  started_at: string;
  ended_at: string | null;
  mode: string;
};
export type SessionCounts = {
  total: number;
  open: number;
  live: number;
  observer: number;
};
export type SessionsResponse = { sessions: SessionRecord[]; counts: SessionCounts };

// --- Auth / credential onboarding (P1, Fyers) ---

export type AuthStatus = {
  broker: string;
  has_api_key: boolean;
  has_token: boolean;
  token_valid: boolean;
  token_expiry: string | null;
  connected: boolean;
  setup_complete: boolean;
  client_name: string | null;
  client_id: string | null;
};

export type AuthStart = { login_url: string; state: string };
export type SaveResult = { success: boolean; message: string };
export type ValidationResult = { valid: boolean; message: string };

export async function authStatus(): Promise<AuthStatus> {
  return get<AuthStatus>("/auth/status");
}

export async function saveCredentials(appId: string, secretId: string): Promise<SaveResult> {
  return postBody<SaveResult>("/auth/credentials", { app_id: appId, secret_id: secretId });
}

export async function testCredentials(appId: string, secretId: string): Promise<ValidationResult> {
  return postBody<ValidationResult>("/auth/test", { app_id: appId, secret_id: secretId });
}

export async function startAuth(): Promise<AuthStart> {
  return post<AuthStart>("/auth/start-auth");
}

export async function reauth(): Promise<AuthStart> {
  return post<AuthStart>("/auth/start-auth");
}

export async function logoutAuth(): Promise<SaveResult> {
  return post<SaveResult>("/auth/logout");
}

// --- Execution: proposals (P4b OBSERVER propose→approve flow) ---

export type Proposal = {
  id: string;
  symbol: string;
  exchange: string;
  side: string; // BUY / SELL
  quantity: number;
  price: number | null;
  order_type: string;
  product: string;
  conviction: number;
  D: number;
  P: number;
  G: string;
  source: string;
  hint_kind: string; // default / chain — chain-derived when a real builder is plugged
  signal_id: string;
  status: string; // PENDING / APPROVED / REJECTED / EXPIRED
  reason: string;
  timestamp: string | null;
  strike: number | null;
  expiry: string | null;
  option_type: string | null; // CE / PE
  lot_size: number | null;
  lots: number | null;
  entry_premium: number | null;
  stop_loss: number | null;
  target: number | null;
  rationale: string | null;
  // Enriched fields (P3-4.3): strategy context from chain hint builder.
  confidence: number | null;
  ev_after_cost: number | null;
  strategy: string | null;
  underlying: string | null;
};

// P3-4.3: order history type for the Orders tab.
export type OrderRecord = {
  order_id: string;
  symbol: string;
  exchange: string;
  side: string;
  order_type: string;
  quantity: number;
  price: number;
  status: string; // FILLED / REJECTED / CANCELLED / OPEN / PARTIALLY_FILLED
  filled_quantity: number;
  average_price: number;
  tag: string | null;
  created_at: string | null;
  // Option identity + trade context (P3-4.3).
  strike: number | null;
  expiry: string | null;
  option_type: string | null;
  lot_size: number | null;
  stop_loss: number | null;
  target: number | null;
  rationale: string | null;
  confidence: number | null;
};

export type ExecutionMode = { mode: string; csrf_token: string | null };
export type RiskSummary = {
  daily_pnl: number;
  margin_used: number;
  margin_available: number | null; // null = unknown, never render as ₹0
  loss_limit: number;
  loss_limit_hit: boolean;
  max_positions: number;
  active_positions: number;
};

export async function approveProposal(
  id: string,
  confirm: boolean,
  csrfToken: string | null,
): Promise<Proposal> {
  // LIVE placements require the per-session CSRF token minted on typed LIVE
  // activation (F-EXEC-001).
  const headers = csrfToken ? { "X-CSRF-Token": csrfToken } : undefined;
  return post<Proposal>(
    `/api/execution/proposals/${encodeURIComponent(id)}/approve?confirm=${confirm}`,
    headers,
  );
}

export async function getProposals(status?: string): Promise<Proposal[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return get<Proposal[]>(`/api/execution/proposals${qs}`);
}

export async function rejectProposal(id: string, reason = ""): Promise<Proposal> {
  const qs = reason ? `?reason=${encodeURIComponent(reason)}` : "";
  return post<Proposal>(`/api/execution/proposals/${encodeURIComponent(id)}/reject${qs}`);
}

export async function executionMode(): Promise<ExecutionMode> {
  return get<ExecutionMode>("/api/execution/mode");
}

export async function riskSummary(): Promise<RiskSummary> {
  return get<RiskSummary>("/api/execution/risk");
}

// P3-4.3: order history from the paper trading engine.
export async function getOrders(status?: string): Promise<OrderRecord[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return get<OrderRecord[]>(`/api/execution/orders${qs}`);
}

// --- Market: intraday bars (T2) ---

export type MarketBar = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type MarketBarsResponse = {
  symbol: string;
  exchange: string;
  bars: MarketBar[];
};

export async function getMarketBars(
  symbol: string,
  exchange: string = "NSE_FNO",
  tf: number = 1,
  days: number = 1,
): Promise<MarketBarsResponse> {
  const q = new URLSearchParams({ symbol, exchange, tf: String(tf), days: String(days) });
  return get<MarketBarsResponse>(`/api/market/bars?${q}`);
}

// --- Settings (Phase 7 W3, settings_router.py) ---

export type SettingsScheduler = {
  enabled: boolean;
  interval_minutes: number;
  lenses: string[] | null;
  tools: string[] | null;
  // Live state: is a research loop actually ticking right now?
  running: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_result: string | null;
};

export type SettingsResponse = {
  loss_limit: number;
  max_positions: number;
  theme: Theme;
  color_convention: ColorConvention;
  scheduler: SettingsScheduler;
};

export type SettingsUpdate = {
  loss_limit?: number;
  max_positions?: number;
  theme?: Theme;
  color_convention?: ColorConvention;
};

export type SchedulerUpdate = {
  enabled?: boolean;
  interval_minutes?: number;
  lenses?: string[] | null;
  tools?: string[] | null;
};

export type ThemeResponse = { theme: Theme };

export type ColorConventionResponse = { color_convention: ColorConvention };

export async function getSettings(): Promise<SettingsResponse> {
  return get<SettingsResponse>("/api/settings");
}

export async function updateSettings(update: SettingsUpdate): Promise<SettingsResponse> {
  return putBody<SettingsResponse>("/api/settings", update);
}

export async function setTheme(theme: Theme): Promise<ThemeResponse> {
  return putBody<ThemeResponse>("/api/settings/theme", { theme });
}

export async function setColorConvention(convention: ColorConvention): Promise<ColorConventionResponse> {
  return putBody<ColorConventionResponse>("/api/settings/color-convention", { color_convention: convention });
}

export async function getScheduler(): Promise<SettingsScheduler> {
  return get<SettingsScheduler>("/api/settings/scheduler");
}

export async function updateScheduler(update: SchedulerUpdate): Promise<SettingsScheduler> {
  return putBody<SettingsScheduler>("/api/settings/scheduler", update);
}

// ── V2 API types and functions ────────────────────────────────────────────
// These provide access to the new v2 endpoints with enriched metadata.
// v1 functions remain unchanged for backward compatibility.

export type APIVersionInfo = {
  version: string;
  release_date: string;
  deprecated: string[];
  migration_guide: string;
};

export type WatchlistItemV2 = {
  symbol: string;
  exchange: string;
  ltp: number;
  change_pct: number;
  volume: number;
  timestamp: string | null;
  security_id: string | null;
  expiry: string | null;
  lot_size: number | null;
  // V2 additions
  instrument_type: string | null;
  bid: number | null;
  ask: number | null;
  oi: number | null;
  is_tradable: boolean;
};

export type OptionsChainItemV2 = {
  strike: number;
  option_type: "CE" | "PE";
  ltp: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  oi: number;
  volume: number;
  bid: number;
  ask: number;
  // V2 additions
  spot_distance_pct: number | null;
  open_interest_change: number | null;
};

export type OptionsChainResponseV2 = {
  underlying: string;
  expiry: string;
  timestamp: string | null;
  spot: number | null;
  contracts: OptionsChainItemV2[];
  // V2 additions: aggregate analytics
  max_pain: number | null;
  pcr: number | null;
  iv_rank_percent: number | null;
};

/** Get API version info and migration metadata. */
export async function getAPIVersion(): Promise<APIVersionInfo> {
  return get<APIVersionInfo>("/api/v2/version");
}

/** Get watchlist with v2 enriched metadata. */
export async function getWatchlistV2(): Promise<WatchlistItemV2[]> {
  return get<WatchlistItemV2[]>("/api/v2/watchlist");
}

/** Get options chain with v2 aggregate analytics. */
export async function getOptionsChainV2(
  symbol: string = "NIFTY",
  expiry?: string,
): Promise<OptionsChainResponseV2> {
  const params = new URLSearchParams({ symbol });
  if (expiry) params.set("expiry", expiry);
  return get<OptionsChainResponseV2>(`/api/v2/options/chain?${params}`);
}
