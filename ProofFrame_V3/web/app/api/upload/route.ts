import { apiFetch } from "@/lib/api";
import { randomUUID } from "node:crypto";
export const dynamic = "force-dynamic";
const fail = (msg: string, status = 400) => Response.json({ error: msg }, { status });

async function step<T>(name: string, p: Promise<Response>): Promise<T> {
  const r = await p;
  if (!r.ok) throw new Error(`${name} failed: HTTP ${r.status} ${(await r.text()).slice(0, 300)}`);
  return (await r.json()) as T;
}

export async function POST(req: Request) {
  const f = await req.formData();
  const file = f.get("file"); const assetId = String(f.get("asset_id") ?? "").trim();
  if (!(file instanceof File) || file.size === 0 || !assetId) return fail("asset_id and mp4 file are required");
  let text = String(f.get("contract_text") ?? "").trim();
  const cf = f.get("contract_file");
  if (!text && cf instanceof File && cf.size > 0) text = await cf.text();
  let contract: unknown;
  try { contract = JSON.parse(text); } catch { return fail("contract is missing or not valid JSON"); }
  try {
    const fd = new FormData();
    fd.set("file", file, file.name); fd.set("asset_id", assetId); fd.set("media_type", "video");
    const asset = await step<{ asset_id: string; sha256: string }>("POST /v1/assets", apiFetch("/v1/assets", { method: "POST", body: fd, signal: AbortSignal.timeout(300000) }));
    const c = await step<{ contract_sha256: string }>("POST /v1/contracts", apiFetch("/v1/contracts", {
      method: "POST", body: JSON.stringify(contract), headers: { "Content-Type": "application/json" } }));
    const run = await step<{ run_id: string }>("POST /v1/verifications", apiFetch("/v1/verifications", {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": randomUUID() },
      body: JSON.stringify({ contract_sha256: c.contract_sha256, assets: [{ asset_id: asset.asset_id, sha256: asset.sha256 }], run_mode: "live" }) }));
    return Response.json({ run_id: run.run_id });
  } catch (e) { return fail((e as Error).message, 502); }
}
