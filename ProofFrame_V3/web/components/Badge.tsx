export function Badge({ v }: { v: string }) {
  return <span className={`badge s-${v}`}>{v}</span>;
}
