import Link from "next/link";
import { apiJson } from "@/lib/api";
import type { RunRow } from "@/lib/types";
import { Badge } from "@/components/Badge";
import { MODE_LABEL, usd } from "@/lib/fmt";
export const dynamic = "force-dynamic";

export default async function Home() {
  let runs: RunRow[] = []; let error: string | null = null;
  try { runs = await apiJson<RunRow[]>("/v1/verifications"); } catch (e) { error = (e as Error).message; }
  return (
    <div className="home">
      <section className="home-hero">
        <h1>Every render, verified.</h1>
        <p className="home-lead">
          ProofFrame checks generated video against the brief approved before generation — blind observation, fail-closed verdicts, every finding tied to frames and timestamps.
        </p>
        <div className="home-cta">
          <Link href="/upload" className="btn-primary">Start a verification</Link>
        </div>
      </section>

      <section className="runs-section" aria-labelledby="runs-heading">
        <div className="section-head">
          <h2 id="runs-heading">Runs</h2>
          {runs.length > 0 && <span className="section-count">{runs.length}</span>}
        </div>
        {error && <div className="err" data-testid="api-error">Cannot load runs. {error}</div>}
        {!error && runs.length === 0 && (
          <div className="card empty-card">
            <p className="empty-title">No verification runs yet</p>
            <p className="empty-copy">
              Upload a rendered MP4 clip and its approved contract JSON to run a blind, evidence-backed check.
            </p>
            <Link href="/upload" className="btn-primary">Start a verification</Link>
          </div>
        )}
        {runs.length > 0 && (
          <div className="table-card">
            <table className="runs-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Mode</th>
                  <th>Decision</th>
                  <th>Est. cost</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.run_id}>
                    <td className="cell-run"><Link href={`/runs/${r.run_id}`}>{r.run_id}</Link></td>
                    <td><Badge v={r.status} /></td>
                    <td className="cell-mode">{MODE_LABEL[r.run_mode] ?? r.run_mode}</td>
                    <td>{r.decision ? <Badge v={r.decision} /> : <span className="cell-empty">-</span>}</td>
                    <td className="cell-num">{usd(r.cost_usd_estimated)}</td>
                    <td className="cell-date">{r.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
