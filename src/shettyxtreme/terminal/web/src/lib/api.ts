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
