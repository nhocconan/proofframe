"use client";
import { useMemo, useRef, useState } from "react";
import type { Check, Envelope, Evidence, Interval } from "@/lib/types";
import { MODE_LABEL, usd } from "@/lib/fmt";

/* ------------------------------------------------------------------ data shaping */
type Finding = {
  candidate: number; start_ms: number; end_ms: number; category: string; severity: string; verdict: string;
  description: string; innocent_explanation_considered: string; explanation: string; evidence_ids: string[]; sources?: string[];
  ref_start_ms?: number; ref_end_ms?: number; entity?: string; shot_a_description?: string; shot_b_description?: string;
};
type ScanCheck = Check & { findings?: Finding[]; target_asset_id?: string };
type Tone = "block" | "review" | "ok" | "muted";
type Item = {
  key: string; testId: string; tone: Tone; title: string; kindLabel: string; time: Interval | null;
  expected?: string; seen?: string | null; summary?: string; evidenceIds: string[];
  why?: string; modelNote?: string; limitations?: string[]; question?: string; regression?: Check["regression"];
  check: ScanCheck; ref?: Interval | null; aDesc?: string; bDesc?: string;
  entity?: string; pairs?: Item[];
  scanEvidence?: Evidence[];
};

const tokens = (e?: string) => new Set((e ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").split(" ")
  .filter((w) => w && !["the", "a", "an", "of", "s"].includes(w)));
const sameEntity = (a?: string, b?: string) => {
  const ta = tokens(a), tb = tokens(b);
  if (!ta.size || !tb.size) return false;
  const [small, big] = ta.size <= tb.size ? [ta, tb] : [tb, ta];
  return [...small].every((w) => big.has(w));
};

/** Many shot pairs often show the same entity's contradiction: one card per entity, pairs listed inside. */
function groupCrossShot(items: Item[]): Item[] {
  const out: Item[] = [];
  for (const it of items) {
    if (!it.ref) { out.push(it); continue; }
    const g = out.find((o) => o.pairs && o.tone === it.tone && sameEntity(o.entity, it.entity));
    if (!g) { out.push({ ...it, pairs: [it] }); continue; }
    g.pairs!.push(it);
    g.evidenceIds = [...g.evidenceIds, ...it.evidenceIds];
  }
  for (const g of out) {
    if (g.pairs && g.pairs.length > 1) {
      const kinds = [...new Set(g.pairs.map((p) => p.title))];
      g.title = `${(g.entity ?? "").replace(/_/g, " ")} — ${kinds.length === 1 ? kinds[0].toLowerCase() : "changes between shots"}`;
      g.summary = `Contradicts itself in ${g.pairs.length} shot pairs. ${g.summary ?? ""}`;
    }
  }
  return out;
}

const CATEGORY: Record<string, string> = {
  anatomy: "Body / anatomy defect", ownership: "Hands or limbs with no visible owner", object: "Object defect",
  text: "Garbled text", physics: "Impossible physics", continuity: "Continuity break in one shot", other: "Visual defect",
  prop_scale: "Prop changes size between shots", prop_design: "Prop changes design between shots",
  wardrobe: "Wardrobe changes between shots", accessory: "Accessory appears / disappears between shots",
  set: "Set or furniture changes within a scene", presence: "Person appears / vanishes without a transition",
  holder: "Object's holder contradicts the previous shot", identity: "Character looks like a different person",
  new_prop: "Object not in the reference still", missing_prop: "Reference object missing from the clip",
  scene_changed: "Setting differs from the reference still",
};

const scanLabel = (c: ScanCheck) =>
  c.assertion_id === "reference-match" ? "Reference still comparison"
    : (c.limitations ?? []).some((l) => l.includes("shot pairs")) ? "Cross-shot continuity audit" : "AI-artifact scan";

const clean = (s?: string) => (s ?? "").replace(/^\[[^\]]*\]\s*/, "").trim();
const firstSentence = (s: string, n = 160) => {
  const t = s.split(/(?<=[.!?])\s/)[0] ?? s;
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
};
const sec = (ms: number) => {
  const s = Math.max(0, ms) / 1000; const m = Math.floor(s / 60);
  return `${m}:${(s % 60).toFixed(1).padStart(4, "0")}`;
};
const span = (iv: Interval | null) => (iv ? `${sec(iv.start_ms)}–${sec(iv.end_ms)}` : "");
const mid = (iv: Interval) => Math.round((iv.start_ms + iv.end_ms) / 2);

function intervalOf(c: Check, env: Envelope): Interval | null {
  if (c.focus) return c.focus;
  const ev = env.evidence.filter((e) => c.evidence_ids.includes(e.evidence_id) && e.kind !== "metadata")
    .sort((a, b) => a.start_ms - b.start_ms)[0];
  return ev ? { start_ms: ev.start_ms, end_ms: Math.max(ev.end_ms, ev.start_ms) } : null;
}

function toneOfStatus(s: string, blocking: boolean): Tone {
  if (s === "PASS" || s === "NOT_APPLICABLE") return "ok";
  if (s === "FAIL") return blocking ? "block" : "review";
  return "review"; // UNCERTAIN, NOT_CHECKED, ERROR: unresolved, never OK
}

function buildItems(env: Envelope): Item[] {
  const items: Item[] = [];
  for (const c of env.checks as ScanCheck[]) {
    if (c.findings !== undefined) {
      for (const f of c.findings) {
        if (f.verdict === "rejected") continue;
        const blocking = f.verdict === "confirmed" && (f.severity === "major" || f.severity === "critical");
        const cross = f.ref_start_ms !== undefined;
        items.push({
          key: `${c.assertion_id}#${f.candidate}`, testId: cross ? `continuity-${f.candidate}` : `finding-${f.candidate}`,
          tone: blocking ? "block" : "review", kindLabel: cross ? "Cross-shot continuity" : scanLabel(c),
          title: CATEGORY[f.category] ?? f.category, time: { start_ms: f.start_ms, end_ms: f.end_ms },
          ref: cross ? { start_ms: f.ref_start_ms!, end_ms: f.ref_end_ms! } : null,
          aDesc: f.shot_a_description, bDesc: f.shot_b_description, entity: f.entity,
          summary: firstSentence(f.description), evidenceIds: f.evidence_ids,
          why: f.description, modelNote: f.explanation.replace(/^\[auto-clear disabled for ownership\]\s*/, ""),
          limitations: c.limitations, question: c.observation_question, regression: c.regression, check: c,
        });
      }
      if (c.status !== "PASS" && !c.findings.some((f) => f.verdict !== "rejected")) {
        items.push(assertionItem(c, env)); // e.g. scan ERROR / NOT_CHECKED
      }
      if (c.status === "PASS") items.push({ ...assertionItem(c, env),
        title: scanLabel(c),
        seen: "nothing survived review" });
      continue;
    }
    items.push(assertionItem(c, env));
  }
  return items;
}

function assertionItem(c: ScanCheck, env: Envelope): Item {
  const tech = (c.limitations ?? []).some((l) => l.includes("ffprobe"));
  return {
    key: c.assertion_id, testId: `check-${c.assertion_id}`, tone: toneOfStatus(c.status, c.blocking),
    title: clean(c.predicate) || c.assertion_id, kindLabel: c.technical_measurement ? "Decoded media check" : tech ? "File check" : c.status === "NOT_CHECKED" ? "Not checked" : "Requirement",
    time: tech ? null : intervalOf(c, env), expected: c.expected, seen: c.observed,
    evidenceIds: c.evidence_ids, why: c.rationale, limitations: c.limitations, question: c.observation_question,
    regression: c.regression, check: c,
    scanEvidence: env.evidence.filter((e) => c.evidence_ids.includes(e.evidence_id) && e.kind === "scan"),
  };
}

function plainWhy(i: Item, nFrames: number): string {
  const c = i.check;
  if (c.findings !== undefined) return "";
  if (c.technical_measurement) return c.rationale;
  if (i.kindLabel === "File check") return c.status === "PASS" ? "File metadata matches the requirement." : `File metadata: ${c.rationale}`;
  const seen = i.seen ?? "nothing readable";
  switch (c.status) {
    case "PASS": return `${nFrames} frame${nFrames === 1 ? "" : "s"} checked — all show the approved value “${i.expected}”.`;
    case "FAIL": return `${nFrames} frame${nFrames === 1 ? "" : "s"} checked — all show “${seen}”, but the approved value is “${i.expected}”.`;
    case "UNCERTAIN": {
      const head = (c.rationale.split("Frame readings:")[0] ?? "").replace(/^\d+ frames inspected;[^.]*\.\s*/, "").trim();
      return `Could not confirm “${i.expected}”. ${head || "The evidence was not clear enough."}`;
    }
    case "NOT_CHECKED": return `Not checked: ${firstSentence(c.rationale.replace(/^NOT_CHECKED:\s*/, ""))}`;
    case "ERROR": return `A technical error stopped this check (not a problem in the video): ${firstSentence(c.rationale)}`;
    default: return firstSentence(c.rationale);
  }
}

const VERDICT: Record<string, { label: string; line: string }> = {
  BLOCK: { label: "Blocked", line: "Do not release — fix the red issues below." },
  REVIEW: { label: "Needs review", line: "Nothing is proven broken, but some items need a human look." },
  ELIGIBLE: { label: "Eligible", line: "All required checks passed. Still not an approval to publish." },
};
const REG: Record<string, string> = {
  FIXED: "Fixed", STILL_FAILING: "Still failing", REGRESSION: "New regression", UNCERTAIN: "Unclear",
  NOT_COMPARABLE: "Not comparable", UNCHANGED_PASS: "Still OK",
};

/* ------------------------------------------------------------------ view */
export default function RunView({ env }: { env: Envelope; fixture?: boolean }) {
  const vref = useRef<HTMLVideoElement>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const items = useMemo(() => groupCrossShot(buildItems(env)), [env]);
  const evById = useMemo(() => Object.fromEntries(env.evidence.map((e) => [e.evidence_id, e])), [env]);

  const firstTarget = (env.checks[0] as ScanCheck | undefined)?.target_asset_id;
  const target = env.assets.find((a) => a.asset_id === firstTarget) ?? env.assets[0];
  const dur = target?.duration_ms ?? 0;
  const blockers = items.filter((i) => i.tone === "block");
  const reviews = items.filter((i) => i.tone === "review");
  const passed = items.filter((i) => i.tone === "ok");
  const cov = env.coverage;
  const skipped = Math.max(0, (cov.contract_total ?? env.checks.length) - (cov.selected ?? env.checks.length));
  const hasScan = (env.checks as ScanCheck[]).some((c) => c.findings !== undefined);
  const budgetStop = env.checks.filter((c) => /Budget exhausted|budget exhausted|cap .* would be exceeded/.test(c.rationale ?? ""))
    .map((c) => c.assertion_id);
  const regs = env.checks.filter((c) => c.regression);
  const regCount = (k: string) => regs.filter((c) => c.regression?.classification === k).length;
  const d = env.decision.decision;
  const videoOnly = env.labels?.includes("VIDEO_ONLY_NO_BRIEF") ?? false;
  const dismissed = (env.checks as ScanCheck[]).flatMap((c) => (c.findings ?? []).filter((f) => f.verdict === "rejected"));

  const seek = (ms: number) => { if (vref.current) { vref.current.currentTime = ms / 1000; } };
  const pick = (it: Item) => {
    setSel(it.key);
    setOpen((o) => ({ ...o, [it.key]: true }));
    if (it.time) seek(it.testId.startsWith("check-") ? it.time.start_ms : mid(it.time));
  };
  const frames = (ids: string[]): Evidence[] =>
    ids.map((i) => evById[i]).filter((e): e is Evidence => !!e && e.kind === "frame").sort((a, b) => a.start_ms - b.start_ms);

  return (
    <div className="rv">
      {/* ---------- verdict hero */}
      <section className={`hero hero-${d}`} data-testid="run-header">
        <div className="hero-main">
          <div className={`verdict v-${d}`} data-testid="decision">{VERDICT[d]?.label ?? d}</div>
          <div>
            <div className="hero-line">{videoOnly && d === "ELIGIBLE"
              ? "No confirmed defects in sampled scan — nothing was checked against a brief."
              : VERDICT[d]?.line}</div>
            <div className="chips" data-testid="coverage">
              <span className="chip c-block">{blockers.length} blocking</span>
              <span className="chip c-review">{reviews.length} to review</span>
              <span className="chip c-ok">{passed.length} passed</span>
              {regs.length > 0 && <span className="chip">vs previous: {regCount("FIXED")} fixed · {regCount("REGRESSION")} regressed · {regCount("STILL_FAILING")} still failing</span>}
            </div>
          </div>
        </div>
        <div className="hero-meta">
          <span className={`mode mode-${env.run.run_mode}`} data-testid="run-mode">{MODE_LABEL[env.run.run_mode] ?? env.run.run_mode}</span>
          <span data-testid="cost">{usd(env.cost.estimated_usd)} est.{env.cost.unknown_cost_calls ? ` · ${env.cost.unknown_cost_calls} unpriced calls` : ""}</span>
          <span className="mut">{env.run.contract_id} r{env.run.contract_revision} · {env.run.finished_at?.slice(0, 16).replace("T", " ")}</span>
        </div>
      </section>

      {skipped > 0 && <div className="warn" data-testid="partial-run">
        <b>Partial run.</b> Only {cov.selected} of {cov.contract_total} requirements were checked — this is not a verdict on the whole video.</div>}
      {budgetStop.length > 0 && <div className="warn" data-testid="budget-stop">
        <b>Budget ran out during the run.</b> {budgetStop.join(", ")} stopped early: findings already paid for are kept,
        but these checks cannot pass — rerun with a higher run cap for full coverage.</div>}
      {(env.plan?.reductions.length ?? 0) > 0 && <div className="note" data-testid="budget-plan">
        <b>Scaled to budget.</b> Full plan est. ${env.plan!.full_estimate_usd.toFixed(2)}, ${(env.plan!.budget_usd ?? 0).toFixed(2)} available,
        so: {env.plan!.reductions.join("; ")}.{env.plan!.fits ? "" : " Still over budget — some calls may not be made."}</div>}
      {!hasScan && <div className="warn" data-testid="no-scan">
        <b>No AI-artifact scan.</b> Defects nobody wrote a requirement for (floating hands, morphing props…) were not looked for.</div>}

      <div className="layout">
        {/* ---------- player + timeline */}
        <div className="player">
          {target && <>
            <video ref={vref} data-testid="target-video" controls preload="metadata" src={`/media/${target.sha256}`} />
            <div className="track" aria-label="issue timeline">
              {dur > 0 && items.filter((i) => i.time && i.tone !== "ok").map((i) => (
                <button key={i.key} title={`${i.title} · ${span(i.time)}`}
                  className={`mark m-${i.tone} ${sel === i.key ? "on" : ""}`}
                  style={{ left: `${(i.time!.start_ms / dur) * 100}%`, width: `max(10px, ${((i.time!.end_ms - i.time!.start_ms) / dur) * 100}%)` }}
                  onClick={() => pick(i)} />))}
            </div>
            <div className="ruler"><span>0:00</span><span>{sec(dur / 2)}</span><span>{sec(dur)}</span></div>
            <div className="legend"><i className="m-block" /> blocks release <i className="m-review" /> needs review
              <span className="mut"> · click a marker or a card to jump there</span></div>
          </>}
        </div>

        {/* ---------- issues */}
        <div className="issues">
          <Group title="Must fix" tone="block" items={blockers} empty="No blocking issues." {...{ sel, open, setOpen, pick, frames, seek }} />
          <Group title="Please review" tone="review" items={reviews} empty="Nothing waiting for review." {...{ sel, open, setOpen, pick, frames, seek }} />

          <details className="fold" data-testid="passed">
            <summary>✓ {passed.length} checks passed</summary>
            <ul className="passlist">
              {passed.map((i) => (
                <li key={i.key}>
                  <button data-testid={i.testId} onClick={() => pick(i)}
                    data-focus-start-ms={i.time?.start_ms ?? ""} data-focus-end-ms={i.time?.end_ms ?? ""}>
                    <span className="dot ok" /> <span className="pl-title">{i.title}</span>
                    <span className="pl-val">{i.seen ?? i.expected}</span>
                    {i.time && <span className="time">{span(i.time)}</span>}
                    {i.regression && <span className={`reg r-${i.regression.classification}`}>{REG[i.regression.classification]}</span>}
                  </button>
                </li>))}
            </ul>
          </details>

          <details className="fold">
            <summary>Technical details</summary>
            <div className="tech">
              {dismissed.length > 0 && <>
                <h4>Scan candidates dismissed after review ({dismissed.length})</h4>
                <ul>{dismissed.map((f) => <li key={f.candidate}><button className="linkish" onClick={() => seek(f.start_ms)}>{sec(f.start_ms)}</button> {firstSentence(f.description)} — <i>{firstSentence(f.explanation, 200)}</i></li>)}</ul>
              </>}
              <h4>Model calls ({env.traces.length})</h4>
              <table><thead><tr><th>Step</th><th>Model</th><th>Time</th><th>Tokens in/out</th><th>Cost</th><th>Result</th></tr></thead>
                <tbody>{env.traces.map((t) => {
                  const u = (t.usage ?? {}) as Record<string, number>;
                  return <tr key={t.trace_id}><td>{(t.purpose ?? "").split(":")[0]}</td><td>{t.model}</td><td>{t.latency_s ?? "–"}s</td>
                    <td>{u.input_tokens ?? "–"}/{u.output_tokens ?? "–"}</td><td>{usd(t.cost_usd)}</td><td>{t.outcome}</td></tr>;
                })}</tbody></table>
              <p className="mut">Run {env.run.run_id} · contract {env.run.contract_sha256?.slice(0, 12)}… · costs are usage × list price estimates.
                {env.decision.publish_authorized === false && " ProofFrame never authorizes publishing."}</p>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}

function Group({ title, tone, items, empty, sel, open, setOpen, pick, frames, seek }: {
  title: string; tone: Tone; items: Item[]; empty: string; sel: string | null; open: Record<string, boolean>;
  setOpen: (f: (o: Record<string, boolean>) => Record<string, boolean>) => void; pick: (i: Item) => void;
  frames: (ids: string[]) => Evidence[]; seek: (ms: number) => void;
}) {
  return (
    <section className={`group g-${tone}`} data-testid={tone === "block" ? "findings" : undefined}>
      <h3>{title} <span className="count">{items.length}</span></h3>
      {items.length === 0 && <p className="mut">{empty}</p>}
      {items.map((i) => {
        const fr = frames(i.evidenceIds);
        const isOpen = !!open[i.key];
        return (
          <article key={i.key} className={`issue t-${i.tone} ${sel === i.key ? "on" : ""}`}>
            <button className="issue-head" data-testid={i.testId} onClick={() => pick(i)}
              data-focus-start-ms={i.time?.start_ms ?? ""} data-focus-end-ms={i.time?.end_ms ?? ""}>
              {i.ref && fr.length >= 2 ? (
                <div className="pair">
                  <img src={`/media/${fr[0].sha256}`} alt="earlier shot" className="thumb half" />
                  <span className="arrow">→</span>
                  <img src={`/media/${fr[fr.length - 1].sha256}`} alt="later shot" className="thumb half" />
                </div>)
                : fr[0] ? <img src={`/media/${fr[Math.min(1, fr.length - 1)].sha256}`} alt="" className="thumb" />
                : <div className="thumb ph">{i.kindLabel === "File check" ? "FILE" : "—"}</div>}
              <div className="issue-body">
                <div className="issue-top">
                  <span className="kind">{i.kindLabel}</span>
                  {i.ref && <span className="time">shot {span(i.ref)} →</span>}
                  {i.time && <span className="time">▶ {span(i.time)}</span>}
                  {i.regression && <span className={`reg r-${i.regression.classification}`}>{REG[i.regression.classification]}</span>}
                </div>
                <div className="issue-title">{i.title}</div>
                {i.expected !== undefined
                  ? <div className="ev"><span>Expected <b>{i.expected}</b></span><span>Seen <b>{i.seen ?? "—"}</b></span></div>
                  : <div className="issue-sum">{i.summary}</div>}
              </div>
            </button>
            <button className="more" onClick={() => setOpen((o) => ({ ...o, [i.key]: !isOpen }))}>{isOpen ? "Hide details" : "Why? Show evidence"}</button>
            {isOpen && <div className="detail">
              {i.scanEvidence?.map((e) => <p key={e.evidence_id}>
                <a href={`/media/${e.sha256}`} target="_blank" rel="noreferrer">Open decoded scan measurements (JSON)</a>
              </p>)}
              {fr.length > 0 && <div className="strip">{fr.map((e) => (
                <button key={e.evidence_id} onClick={() => seek(e.start_ms)} title={e.label}>
                  <img src={`/media/${e.sha256}`} alt={e.label ?? ""} /><span>{sec(e.start_ms)}</span></button>))}</div>}
              {i.pairs && i.pairs.length > 1 && <div className="pairs">
                <b>Shot pairs</b>
                {i.pairs.map((p) => (
                  <button key={p.key} onClick={() => seek(mid(p.time!))}>
                    <span className="time">{span(p.ref!)} → {span(p.time!)}</span> {firstSentence(p.summary ?? "", 140)}
                  </button>))}
              </div>}
              {i.ref && (!i.pairs || i.pairs.length === 1) && <div className="ab">
                <button onClick={() => seek(mid(i.ref!))}><b>Earlier shot</b> ({span(i.ref)}){i.aDesc ? `: ${i.aDesc}` : ""}</button>
                <button onClick={() => seek(mid(i.time!))}><b>Later shot</b> ({span(i.time)}){i.bDesc ? `: ${i.bDesc}` : ""}</button>
              </div>}
              {i.summary && i.why && i.why !== i.summary && <p><b>What was flagged:</b> {i.why}</p>}
              {i.modelNote && <p><b>Reviewer model:</b> {i.modelNote}</p>}
              {!i.modelNote && <p className="plain">{plainWhy(i, fr.length)}</p>}
              {!i.modelNote && i.why && <details><summary className="mut">Technical reasoning</summary><p className="mut">{i.why}</p></details>}
              {i.limitations?.length ? <details><summary className="mut">Limits of this check</summary><ul className="mut">{i.limitations.map((l) => <li key={l}>{l}</li>)}</ul></details> : null}
              {i.question && <details><summary className="mut">Question sent to the model</summary><p className="q">{i.question}</p></details>}
            </div>}
          </article>);
      })}
    </section>
  );
}
