"use client";
import { useRef, useState } from "react";
import type { Check, Envelope, Interval } from "@/lib/types";
import { Badge } from "./Badge";
import { MODE_LABEL, mmss, usd } from "@/lib/fmt";

const intervalOf = (c: Check, env: Envelope): Interval | null => {
  if (c.focus) return c.focus;
  const ev = env.evidence.filter((e) => c.evidence_ids.includes(e.evidence_id)).sort((a, b) => a.start_ms - b.start_ms)[0];
  return ev ? { start_ms: ev.start_ms, end_ms: Math.max(ev.end_ms, ev.start_ms) } : null;
};

export default function RunView({ env, fixture }: { env: Envelope; fixture?: boolean }) {
  const vref = useRef<HTMLVideoElement>(null);
  const [sel, setSel] = useState<string | null>(null);
  const check0 = env.checks.find((c) => c.assertion_id === sel) ?? null;
  const targetId = (check0 as (Check & { target_asset_id?: string }) | null)?.target_asset_id
    ?? (env.checks[0] as (Check & { target_asset_id?: string }) | undefined)?.target_asset_id;
  const target = env.assets.find((a) => a.asset_id === targetId) ?? env.assets[0];
  const dur = target?.duration_ms ?? 0;
  const cov = env.coverage;
  const unresolved = (cov.uncertain ?? 0) + (cov.not_checked ?? 0) + (cov.error ?? 0);
  const check = env.checks.find((c) => c.assertion_id === sel) ?? null;
  const regs = env.checks.filter((c) => c.regression);

  const pick = (c: Check) => {
    setSel(c.assertion_id);
    const iv = intervalOf(c, env);
    if (iv && vref.current) vref.current.currentTime = iv.start_ms / 1000;
  };
  const seek = (ms: number) => { if (vref.current) vref.current.currentTime = ms / 1000; };
  const mode = env.run.run_mode;

  return (
    <div>
      <div className="hdr" data-testid="run-header">
        <span className={`mode mode-${mode}`} data-testid="run-mode">{MODE_LABEL[mode] ?? mode}</span>
        <div><Badge v={env.decision.decision} /> <b data-testid="decision">{env.decision.decision}</b>
          <div style={{ fontSize: 12 }}>not a publishing authorization</div></div>
        <div data-testid="coverage">Mandatory {cov.mandatory}: pass {cov.pass} · fail {cov.fail} · uncertain {cov.uncertain} ·
          not_checked {cov.not_checked} · error {cov.error} · n/a {cov.not_applicable}
          <br /><b>Unresolved mandatory: {unresolved}</b></div>
        <div data-testid="cost">Est. cost {usd(env.cost.estimated_usd)} · unknown-cost calls {env.cost.unknown_cost_calls}</div>
      </div>
      {fixture && <p className="err">Fixture view (?fixture=1): synthetic data, not from the API.</p>}
      {(env.labels ?? []).map((l) => <div key={l} style={{ fontSize: 12 }}>{l}</div>)}
      {regs.length > 0 && (
        <div className="card" data-testid="regressions">
          <b>Before/after (regression run vs {env.run.previous_run_id ?? "previous"})</b>
          <table><thead><tr><th>Assertion</th><th>Before</th><th>After</th><th>Classification</th></tr></thead><tbody>
            {[...regs].sort((a, b) => (b.regression!.classification === "REGRESSION" ? 1 : 0) - (a.regression!.classification === "REGRESSION" ? 1 : 0))
              .map((c) => (
              <tr key={c.assertion_id}><td>{c.assertion_id}</td><td><Badge v={c.regression!.before} /></td>
                <td><Badge v={c.regression!.after} /></td>
                <td><Badge v={c.regression!.classification} /></td></tr>))}
          </tbody></table>
        </div>)}
      <div className="grid">
        <div>
          {target ? (<>
            <video ref={vref} data-testid="target-video" controls preload="metadata" src={`/media/${target.sha256}`} />
            <div className="tl" data-testid="timeline" aria-label="evidence timeline">
              {dur > 0 && env.checks.map((c) => {
                const iv = intervalOf(c, env); if (!iv) return null;
                return <div key={c.assertion_id} title={`${c.assertion_id} ${c.status}`}
                  className={`iv s-${c.status} ${sel === c.assertion_id ? "hl" : ""}`}
                  style={{ left: `${(iv.start_ms / dur) * 100}%`, width: `${Math.max(((iv.end_ms - iv.start_ms) / dur) * 100, 0.4)}%` }}
                  onClick={() => pick(c)} />;
              })}
            </div>
            <div style={{ fontSize: 12 }}>{target.asset_id} r{target.revision} · {dur ? mmss(dur) : "duration unknown"}</div>
          </>) : <p className="err">No target asset in envelope.</p>}
          <div className="checks card"><b>Checks</b>
            {env.checks.map((c) => (
              <button key={c.assertion_id} data-testid={`check-${c.assertion_id}`} className={sel === c.assertion_id ? "sel" : ""}
                data-focus-start-ms={intervalOf(c, env)?.start_ms ?? ""} data-focus-end-ms={intervalOf(c, env)?.end_ms ?? ""}
                onClick={() => pick(c)}>
                <Badge v={c.status} /> <span>{c.assertion_id}{c.blocking ? " (blocking)" : ""}</span>
                {c.regression && <Badge v={c.regression.classification} />}
              </button>))}
          </div>
        </div>
        <div>
          {!check ? <div className="card">Select a check.</div> : (
            <div className="card" data-testid="check-detail">
              <h3 style={{ margin: 0 }}>{check.assertion_id} <Badge v={check.status} /></h3>
              {check.source_pointer && <div style={{ fontSize: 12 }}>{check.source_pointer}</div>}
              <div className="sbs">
                <div><b>Expected (approved)</b><br />{check.expected}</div>
                <div><b>Observed</b><br />{check.observed ?? <i>none (no observation)</i>}</div>
              </div>
              <p><b>Rationale:</b> {check.rationale}</p>
              {check.limitations.length > 0 && <><b>Limitations</b><ul>{check.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></>}
              {check.observation_question && <><b>Neutral question sent to model</b><div className="q">{check.observation_question}</div></>}
              {check.regression && (
                <div className="reg"><b>Regression:</b> <Badge v={check.regression.before} /> → <Badge v={check.regression.after} />{" "}
                  <Badge v={check.regression.classification} /></div>)}
              <b>Evidence</b>
              <div className="thumbs">
                {env.evidence.filter((e) => check.evidence_ids.includes(e.evidence_id)).map((e) => (
                  <figure key={e.evidence_id}>
                    {e.kind === "frame" ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={`/media/${e.sha256}`} alt={e.label ?? e.evidence_id} loading="lazy" />) : <div>{e.kind}</div>}
                    <button onClick={() => seek(e.start_ms)}>{mmss(e.start_ms)}</button> {e.label}
                  </figure>))}
                {check.evidence_ids.length === 0 && <i>no evidence recorded</i>}
              </div>
              <b>Traces</b>
              <table><thead><tr><th>Model</th><th>Latency</th><th>Tokens</th><th>Cost</th><th>Outcome</th></tr></thead><tbody>
                {env.traces.filter((t) => check.trace_ids.includes(t.trace_id)).map((t) => (
                  <tr key={t.trace_id}><td>{t.model}</td><td>{t.latency_s != null ? `${t.latency_s}s` : "?"}</td>
                    <td>{t.usage ? `${t.usage["input_tokens"] ?? "?"} in / ${t.usage["output_tokens"] ?? "?"} out` : "?"}</td>
                    <td>{usd(t.cost_usd)}</td><td>{t.outcome}</td></tr>))}
              </tbody></table>
            </div>)}
        </div>
      </div>
    </div>
  );
}
