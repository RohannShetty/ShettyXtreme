/** Typed fetch helpers for the ShettyXtreme Terminal API. */

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
};
export type KnowledgeSyncResponse = {
  ingested: number;
  skipped_undecided: number;
  skipped_duplicate: number;
  error: string | null;
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
