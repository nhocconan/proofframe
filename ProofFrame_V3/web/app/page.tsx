import Link from "next/link";
import { apiJson } from "@/lib/api";
import type { RunRow } from "@/lib/types";
import { Badge } from "@/components/Badge";
import { MODE_LABEL, usd } from "@/lib/fmt";
export const dynamic = "force-dynamic";

export default async function Home() {
  let runs: RunRow[] = []; let error: string | null = null;
  try { runs = await apiJson<RunRow[]>("/v1/verifications"); } catch (e) { error = (e as Error).message; }
  return (<div>
    <h1>Runs</h1>
    {error && <div className="err" data-testid="api-error">Cannot load runs. {error}</div>}
    {!error && runs.length === 0 && <p>No runs yet. <Link href="/upload">Start one</Link>.</p>}
    {runs.length > 0 && <table><thead><tr><th>Run</th><th>Status</th><th>Mode</th><th>Decision</th><th>Est. cost</th><th>Created</th></tr></thead><tbody>
      {runs.map((r) => (<tr key={r.run_id}>
        <td><Link href={`/runs/${r.run_id}`}>{r.run_id}</Link></td><td><Badge v={r.status} /></td>
        <td>{MODE_LABEL[r.run_mode] ?? r.run_mode}</td><td>{r.decision ? <Badge v={r.decision} /> : "-"}</td>
        <td>{usd(r.cost_usd_estimated)}</td><td>{r.created_at}</td></tr>))}
    </tbody></table>}
  </div>);
}
