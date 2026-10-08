import type { Report } from "../api";
export function ReportView({ report, onEvidence }: { report: Report; onEvidence: (chartIds: string[]) => void }) {
  return <section className="panel p-5 space-y-4 max-w-3xl"><h2 className="text-base font-semibold">Research report</h2>
    <div><h3 className="muted text-xs uppercase tracking-wide mb-1">Executive summary</h3><p className="leading-relaxed">{report.executive_summary}</p></div>
    {report.findings.length > 0 && <div><h3 className="muted text-xs uppercase tracking-wide mb-2">Key findings</h3><ol className="space-y-3">
      {report.findings.map((f, i) => <li key={f.id} className="flex gap-3"><span className="muted font-mono">{i + 1}</span><div>
        <p>{f.claim}</p><p className="muted text-xs mt-0.5">{f.what_in_chart} · confidence: {f.confidence}</p>
        <button className="text-xs underline" style={{ color: "var(--accent)" }} onClick={() => onEvidence(f.evidence.charts)}>Show evidence</button>
        <span className="muted text-xs"> {f.id} ← {f.evidence.charts.join(", ")} ← {f.evidence.queries.join(", ")} ← {f.evidence.datasets.join(", ")}</span></div></li>)}</ol></div>}
    {report.hypotheses.length > 0 && <div><h3 className="muted text-xs uppercase tracking-wide mb-1">Possible explanations (hypotheses, unproven)</h3><ul className="list-disc pl-5">{report.hypotheses.map((h, i) => <li key={i}>{h}</li>)}</ul></div>}
    <div><h3 className="muted text-xs uppercase tracking-wide mb-1">Limitations</h3><ul className="list-disc pl-5">{report.limitations.map((h, i) => <li key={i}>{h}</li>)}</ul>
      {report.unverified_count > 0 && <p className="muted text-xs mt-2">{report.unverified_count} AI claim(s) were rejected because they did not match chart data.</p>}</div></section>;
}
