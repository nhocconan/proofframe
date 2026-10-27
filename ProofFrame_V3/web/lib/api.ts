import "server-only";
export const API_URL = (process.env.PROOFFRAME_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const t = process.env.PROOFFRAME_API_TOKEN;
  return { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...extra };
}
export class ApiError extends Error {
  constructor(public status: number, msg: string) { super(msg); }
}
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(API_URL + path, {
      ...init, cache: "no-store",
      headers: authHeaders(init.headers as Record<string, string> | undefined),
      signal: init.signal ?? AbortSignal.timeout(15000),
    });
  } catch (e) {
    throw new ApiError(0, `API unreachable at ${API_URL}: ${(e as Error).message}`);
  }
}
export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await apiFetch(path, init);
  if (!r.ok) throw new ApiError(r.status, `API ${path} -> HTTP ${r.status}: ${(await r.text()).slice(0, 300)}`);
  return (await r.json()) as T;
}
