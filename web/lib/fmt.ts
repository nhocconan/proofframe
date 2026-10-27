export const mmss = (ms: number) => {
  const s = ms / 1000; return `${String(Math.floor(s / 60)).padStart(2, "0")}:${(s % 60).toFixed(3).padStart(6, "0")}`;
};
export const usd = (n: number | null | undefined) => (n == null ? "unknown" : `$${n.toFixed(4)}`);
export const MODE_LABEL: Record<string, string> = {
  live: "LIVE RUN", recorded_replay: "RECORDED REPLAY (not live)", synthetic_fixture: "SYNTHETIC FIXTURE (not real)",
};
