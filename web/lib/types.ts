export type CheckStatus = "PASS" | "FAIL" | "UNCERTAIN" | "NOT_CHECKED" | "ERROR" | "NOT_APPLICABLE";
export type RunMode = "live" | "recorded_replay" | "synthetic_fixture";
export type Interval = { start_ms: number; end_ms: number };
export type Regression = {
  before: string; after: string;
  classification: "FIXED" | "STILL_FAILING" | "REGRESSION" | "UNCERTAIN" | "NOT_COMPARABLE" | "UNCHANGED_PASS";
};
export type Check = {
  assertion_id: string; status: CheckStatus; blocking: boolean; global_sentinel?: boolean;
  source_pointer?: string; predicate?: string; expected: string; observed: string | null;
  observation_question?: string; scope: Interval | null; focus: Interval | null;
  evidence_ids: string[]; trace_ids: string[]; rationale: string; limitations: string[];
  regression: Regression | null;
  technical_measurement?: { value: number; intervals: Interval[]; limitations: string[] };
};
export type Evidence = {
  evidence_id: string; asset_id: string; kind: "frame" | "clip" | "metadata" | "scan" | "audio" | "reference";
  start_ms: number; end_ms: number; sha256: string; url: string; role?: string; label?: string;
};
export type Trace = {
  trace_id: string; provider?: string; model: string; endpoint?: string; purpose?: string;
  http_status?: number; latency_s?: number; usage?: Record<string, unknown>;
  cost_usd: number | null; cost_basis?: string; outcome: string;
};
export type EnvAsset = { asset_id: string; revision: number; sha256: string; duration_ms?: number; url: string };
export type Envelope = {
  schema_version: string;
  run: { run_id: string; run_mode: RunMode; profile?: string; contract_id?: string; contract_revision?: number;
         contract_sha256?: string; started_at?: string; finished_at?: string; previous_run_id?: string | null };
  decision: { decision: "BLOCK" | "REVIEW" | "ELIGIBLE"; unresolved?: unknown[]; blocking_failures?: unknown[];
              advisory_findings?: unknown[]; publish_authorized?: boolean };
  assets: EnvAsset[]; checks: Check[]; evidence: Evidence[]; traces: Trace[];
  coverage: Record<string, number>;
  cost: { estimated_usd: number; unknown_cost_calls: number; reserved_open_usd?: number };
  plan?: { estimate_usd: number; full_estimate_usd: number; budget_usd: number | null; reductions: string[]; fits: boolean };
  labels?: string[];
};
export type RunRow = {
  run_id: string; status: string; run_mode: RunMode; decision?: string | null;
  cost_usd_estimated?: number | null; created_at: string; error?: string | null;
};
