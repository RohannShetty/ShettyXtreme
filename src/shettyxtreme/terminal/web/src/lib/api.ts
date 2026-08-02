/** Typed fetch helpers for the ShettyXtreme Terminal API. */

type JsonError = { detail?: unknown; message?: string };

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

async function request<T>(path: string, method: string): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, { method, credentials: "same-origin" });
  } catch {
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

export async function post<T>(path: string): Promise<T> {
  return request<T>(path, "POST");
}

export async function del(path: string): Promise<void> {
  let resp: Response;
  try {
    resp = await fetch(path, { method: "DELETE", credentials: "same-origin" });
  } catch {
    throw new Error(`Network error reaching ${path}`);
  }
  if (!resp.ok) {
    throw new Error(await describeError(resp));
  }
}

export async function postBody<T>(path: string, body: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
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

// --- Auth / credential onboarding (P1) ---

export type AuthStatus = {
  has_api_key: boolean;
  has_token: boolean;
  token_valid: boolean;
  token_expiry: string | null;
  connected: boolean;
  setup_complete: boolean;
  client_name: string | null;
  client_id: string | null;
  data_token_valid: boolean;
  data_token_expiry: string | null;
};

export type ConsentStart = { consent_app_id: string; login_url: string };
export type SaveResult = { success: boolean; message: string };
export type ValidationResult = { valid: boolean; message: string };

export async function authStatus(): Promise<AuthStatus> {
  return get<AuthStatus>("/auth/status");
}

export async function saveCredentials(apiKey: string, apiSecret: string): Promise<SaveResult> {
  return postBody<SaveResult>("/auth/credentials", { api_key: apiKey, api_secret: apiSecret });
}

export async function testCredentials(apiKey: string, apiSecret: string): Promise<ValidationResult> {
  return postBody<ValidationResult>("/auth/test", { api_key: apiKey, api_secret: apiSecret });
}

export async function startConsent(): Promise<ConsentStart> {
  return post<ConsentStart>("/auth/start-consent");
}

export async function saveDirectToken(accessToken: string): Promise<SaveResult> {
  return postBody<SaveResult>("/auth/token", { access_token: accessToken });
}

export async function savePinTotp(clientId: string, pin: string, totp: string): Promise<SaveResult> {
  return postBody<SaveResult>("/auth/token/pin-totp", { client_id: clientId, pin, totp });
}

export async function saveDataToken(accessToken: string, expiry: string | null = null): Promise<SaveResult> {
  return postBody<SaveResult>("/auth/data-token", { access_token: accessToken, expiry });
}

export async function reauth(): Promise<ConsentStart> {
  return post<ConsentStart>("/auth/start-consent");
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
  signal_id: string;
  status: string; // PENDING / APPROVED / REJECTED / EXPIRED
  reason: string;
  timestamp: string | null;
};

export type ExecutionMode = { mode: string };
export type RiskSummary = {
  daily_pnl: number;
  margin_used: number;
  margin_available: number;
  loss_limit: number;
  loss_limit_hit: boolean;
  max_positions: number;
  active_positions: number;
};

export async function getProposals(status?: string): Promise<Proposal[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return get<Proposal[]>(`/api/execution/proposals${qs}`);
}

export async function approveProposal(id: string, confirm: boolean): Promise<Proposal> {
  return post<Proposal>(`/api/execution/proposals/${encodeURIComponent(id)}/approve?confirm=${confirm}`);
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
