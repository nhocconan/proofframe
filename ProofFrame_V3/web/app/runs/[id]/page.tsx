import fixture from "@/fixtures/sample-envelope.json";
import { apiFetch } from "@/lib/api";
import type { Envelope, RunRow } from "@/lib/types";
import RunView from "@/components/RunView";
import Poller from "@/components/Poller";
export const dynamic = "force-dynamic";

export default async function RunPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ fixture?: string }>;
}) {
  const { id } = await params; const sp = await searchParams;
  if (sp.fixture === "1") return <RunView env={fixture as unknown as Envelope} fixture />;
  let run: RunRow;
  try {
    const r = await apiFetch(`/v1/verifications/${encodeURIComponent(id)}`);
    if (!r.ok) return <div className="err">Run lookup failed: HTTP {r.status}</div>;
    run = await r.json();
  } catch (e) { return <div className="err" data-testid="api-error">{(e as Error).message}</div>; }
  if (run.status === "queued" || run.status === "running")
    return <div><h1>{id}</h1><p>Status: <b>{run.status}</b> (polling...)</p><Poller /></div>;
  if (run.status !== "succeeded")
    return <div><h1>{id}</h1><p>Status: <b>{run.status}</b></p>{run.error && <div className="err">{run.error}</div>}</div>;
  try {
    const r = await apiFetch(`/v1/verifications/${encodeURIComponent(id)}/report`);
    if (!r.ok) return <div className="err">Report unavailable: HTTP {r.status}</div>;
    return <RunView env={(await r.json()) as Envelope} />;
  } catch (e) { return <div className="err" data-testid="api-error">{(e as Error).message}</div>; }
}
