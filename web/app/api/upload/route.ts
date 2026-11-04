import { apiFetch } from "@/lib/api";
import { randomUUID } from "node:crypto";
export const dynamic = "force-dynamic";
const fail = (msg: string, status = 400) => Response.json({ error: msg }, { status });

async function step<T>(name: string, p: Promise<Response>): Promise<T> {
  const r = await p;
  if (!r.ok) throw new Error(`${name} failed: HTTP ${r.status} ${(await r.text()).slice(0, 300)}`);
  return (await r.json()) as T;
}

function defaultAssetId(filename: string): string {
  const base = filename.replace(/^.*[/\\]/, "").replace(/\.[^.]+$/, "");
  const clean = base
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[đĐ]/g, (c) => (c === "đ" ? "d" : "D"))
    .replace(/[^A-Za-z0-9_.:-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 200);
  return clean || "video";
}

export async function POST(req: Request) {
  const f = await req.formData();
  const file = f.get("file");
  if (!(file instanceof File) || file.size === 0) return fail("mp4 file is required");
  if (!/\.mp4$/i.test(file.name) && file.type !== "video/mp4") return fail("mp4 file is required");

  const rawAssetId = String(f.get("asset_id") ?? "").trim();
  const assetId = rawAssetId || defaultAssetId(file.name);
  const briefText = String(f.get("brief_text") ?? "").trim();
  if (briefText.length > 20000) return fail("brief_text must be 20,000 characters or fewer");

  let contractText = String(f.get("contract_text") ?? "").trim();
  const cf = f.get("contract_file");
  if (!contractText && cf instanceof File && cf.size > 0) contractText = (await cf.text()).trim();

  let contract: unknown = undefined;
  if (contractText) {
    try { contract = JSON.parse(contractText); }
    catch { return fail("contract is not valid JSON"); }
  }

  try {
    const fd = new FormData();
    fd.set("file", file, file.name);
    fd.set("asset_id", assetId);
    fd.set("media_type", "video");
    const asset = await step<{ asset_id: string; sha256: string }>(
      "POST /v1/assets",
      apiFetch("/v1/assets", { method: "POST", body: fd, signal: AbortSignal.timeout(300000) })
    );
    if (contract !== undefined) {
      const c = await step<{ contract_sha256: string }>(
        "POST /v1/contracts",
        apiFetch("/v1/contracts", {
          method: "POST",
          body: JSON.stringify(contract),
          headers: { "Content-Type": "application/json" },
        })
      );
      const run = await step<{ run_id: string }>(
        "POST /v1/verifications",
        apiFetch("/v1/verifications", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Idempotency-Key": randomUUID() },
          body: JSON.stringify({
            contract_sha256: c.contract_sha256,
            assets: [{ asset_id: asset.asset_id, sha256: asset.sha256 }],
            run_mode: "live",
          }),
        })
      );
      return Response.json({ run_id: run.run_id });
    }
    const verBody: Record<string, unknown> = {
      mode: "video_only",
      assets: [{ asset_id: asset.asset_id, sha256: asset.sha256 }],
      run_mode: "live",
    };
    if (briefText) verBody.brief_text = briefText;
    const run = await step<{ run_id: string }>(
      "POST /v1/verifications",
      apiFetch("/v1/verifications", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": randomUUID() },
        body: JSON.stringify(verBody),
      })
    );
    return Response.json({ run_id: run.run_id });
  } catch (e) {
    return fail((e as Error).message, 502);
  }
}
