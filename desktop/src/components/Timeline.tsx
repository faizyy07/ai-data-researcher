import type { RunEvent } from "../api";
const icon = (s: RunEvent["status"]) => s === "done" ? "✓" : s === "error" ? "✕" : s === "info" ? "·" : "→";
const color = (s: RunEvent["status"]) => s === "done" ? "var(--ok)" : s === "error" ? "var(--bad)" : s === "info" ? "var(--warn)" : "var(--accent)";
export function Timeline({ events, running }: { events: RunEvent[]; running: boolean }) {
  // collapse "running" rows that were later completed for the same step
  const rows = events.filter((e, i) => !(e.status === "running" && events.slice(i + 1).some(n => n.step === e.step && n.status !== "running")));
  return <ol className="space-y-1.5">{rows.map(e => <li key={e.i} className="flex gap-2 leading-snug">
    <span style={{ color: color(e.status), width: 12 }} className="shrink-0 font-mono">{icon(e.status)}</span>
    <span className={e.status === "info" ? "muted" : ""}>{e.message}</span></li>)}
    {running && <li className="skeleton h-3 w-2/3 mt-2" aria-label="working" />}</ol>;
}
