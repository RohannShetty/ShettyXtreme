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
