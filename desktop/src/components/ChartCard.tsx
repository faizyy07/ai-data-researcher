import { useState } from "react"; import { EChart } from "../charts/EChart"; import type { Chart } from "../api";
export function ChartCard({ chart, dark, onInvestigate, highlight }: { chart: Chart; dark: boolean; onInvestigate: (c: Chart) => void; highlight?: boolean }) {
  const [full, setFull] = useState(false);
  return <div id={chart.id} className={`panel p-3 ${full ? "fixed inset-6 z-50 shadow-2xl" : ""}`} style={highlight ? { borderColor: "var(--accent)" } : undefined}>
    <div className="flex items-center justify-between gap-2"><div className="min-w-0"><div className="font-medium truncate">{chart.title}</div>
      <div className="muted text-xs">{chart.id} · {chart.query_id}</div></div>
      <div className="flex gap-1.5 shrink-0"><button className="btn text-xs" onClick={() => onInvestigate(chart)}>Investigate</button>
        <button className="btn text-xs" onClick={() => setFull(f => !f)}>{full ? "Close" : "Fullscreen"}</button></div></div>
    <EChart option={chart.option} dark={dark} height={full ? window.innerHeight - 160 : 260} />
    <details className="text-xs muted"><summary className="cursor-pointer">SQL & computed stats</summary>
      <pre className="whitespace-pre-wrap mt-1">{chart.sql}</pre><pre className="whitespace-pre-wrap mt-1 max-h-40 overflow-auto">{JSON.stringify(chart.stats, null, 1)}</pre></details></div>;
}
