"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
export default function Upload() {
  const r = useRouter();
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: new FormData(e.currentTarget) });
      const j = await res.json();
      if (!res.ok) throw new Error(j.error ?? `HTTP ${res.status}`);
      r.push(`/runs/${j.run_id}`);
    } catch (x) { setErr((x as Error).message); setBusy(false); }
  }
  return (<form onSubmit={submit} className="card">
    <h1>New verification</h1>
    <label>asset_id <input type="text" name="asset_id" required defaultValue="shot-01" /></label>
    <label>Video (mp4) <input type="file" name="file" accept="video/mp4" required /></label>
    <label>Contract JSON (upload) <input type="file" name="contract_file" accept="application/json,.json" /></label>
    <label>...or paste contract JSON <textarea name="contract_text" /></label>
    <button className="primary" disabled={busy}>{busy ? "Submitting..." : "Upload and verify"}</button>
    {err && <div className="err" data-testid="upload-error" style={{ marginTop: 8 }}>{err}</div>}
  </form>);
}
