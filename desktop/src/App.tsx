import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Chart, type DatasetSummary, type RunSnapshot, type RunEvent } from "./api";
import { Timeline } from "./components/Timeline"; import { ChartCard } from "./components/ChartCard";
import { ReportView } from "./components/ReportView"; import { Settings } from "./components/Settings";

type Profile = Awaited<ReturnType<typeof api.profile>>;
const DEFAULT_Q = "Research this dataset and find anything unusual.";

export default function App() {
  const [dark, setDark] = useState(() => localStorage.getItem("theme") !== "light");
  const [ds, setDs] = useState<DatasetSummary | null>(null); const [profile, setProfile] = useState<Profile | null>(null);
  const [question, setQuestion] = useState(DEFAULT_Q); const [run, setRun] = useState<RunSnapshot | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState(false); const [model, setModel] = useState(""); const [hasKey, setHasKey] = useState(true);
  const [focus, setFocus] = useState<string[]>([]); const [drag, setDrag] = useState(false);
  const qRef = useRef<HTMLTextAreaElement>(null); const timer = useRef<number>();

  useEffect(() => { document.documentElement.classList.toggle("dark", dark); localStorage.setItem("theme", dark ? "dark" : "light"); }, [dark]);
  const refreshAi = useCallback(() => api.aiStatus().then(s => { setModel(s.model); setHasKey(s.has_key); }).catch(e => setError(e.message)), []);
  useEffect(() => { refreshAi(); }, [refreshAi, settings]);
  useEffect(() => { const k = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); qRef.current?.focus(); } };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const load = async (f: File) => { setError(""); setBusy(true); setRun(null); setEvents([]);
    try { const d = await api.upload(f); setDs(d); setProfile(await api.profile(d.id)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };

  const start = async (q: string) => {
    if (!ds) return; setError(""); setFocus([]); setEvents([]); setRun(null);
    try { const { id } = await api.start(ds.id, q); let since = 0; let all: RunEvent[] = [];
      const tick = async () => { try { const s = await api.poll(id, since); since = s.next; all = [...all, ...s.events]; setEvents(all); setRun(s);
        if (s.status === "running") timer.current = window.setTimeout(tick, 900); } catch (e) { setError((e as Error).message); } };
      tick();
    } catch (e) { setError((e as Error).message); if ((e as Error).message.includes("API key")) setSettings(true); }
  };
  const investigate = (c: Chart) => { const q = `Investigate ${c.id} ("${c.title}") in more depth: what explains the pattern or anything unusual in it?`; setQuestion(q); start(q); };
  const showEvidence = (ids: string[]) => { setFocus(ids); document.getElementById(ids[0])?.scrollIntoView({ behavior: "smooth", block: "center" }); };
  const running = run?.status === "running";

  return <div className="h-full flex flex-col" onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
    onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) load(f); }}>
    <header className="h-11 shrink-0 flex items-center justify-between px-4 border-b" style={{ borderColor: "var(--line)" }}>
      <div className="font-semibold tracking-tight">Data Researcher</div>
      <div className="flex items-center gap-2 text-xs"><span className="muted">{hasKey ? model : "No API key"}</span>
        <button className="btn" onClick={() => setSettings(true)}>AI settings</button><button className="btn" onClick={() => setDark(d => !d)}>{dark ? "Light" : "Dark"}</button></div></header>

    <div className="flex-1 min-h-0 grid" style={{ gridTemplateColumns: "230px minmax(0,1fr) 330px" }}>
      <aside className="border-r p-3 overflow-auto space-y-3" style={{ borderColor: "var(--line)" }}>
        <div className="muted text-xs uppercase tracking-wide">Dataset</div>
        <label className="btn block text-center cursor-pointer">Open CSV / XLSX<input type="file" hidden accept=".csv,.tsv,.xlsx" onChange={e => e.target.files?.[0] && load(e.target.files[0])} /></label>
        {busy && <div className="skeleton h-16" />}
        {ds && profile && <div className="space-y-2"><div className="font-medium break-all">{ds.filename}</div>
          {profile.tables.map(t => <details key={t.name} open><summary className="cursor-pointer">{t.name} <span className="muted">· {t.rows.toLocaleString()} rows</span></summary>
            <ul className="mt-1 space-y-0.5">{t.columns.map(c => <li key={c.name} className="flex justify-between gap-2 text-xs"><span className="truncate">{c.name}</span>
              <span className="muted shrink-0">{c.semantic_role ?? c.dtype}</span></li>)}</ul>
            {t.duplicate_rows > 0 && <p className="text-xs" style={{ color: "var(--warn)" }}>{t.duplicate_rows} duplicate rows</p>}</details>)}</div>}
      </aside>

      <main className="overflow-auto p-5 space-y-4">
        {!ds && <div className={`panel h-64 grid place-items-center text-center ${drag ? "" : "muted"}`} style={drag ? { borderColor: "var(--accent)" } : { borderStyle: "dashed" }}>
          <div>Drop a CSV or Excel file here<div className="text-xs mt-1">Your file is read locally and never modified.</div></div></div>}
        {ds && !run && !busy && <div className="muted">Ask a question on the right. Charts and evidence will appear here.</div>}
        {run && run.charts.length > 0 && <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(420px,1fr))" }}>
          {run.charts.map(c => <ChartCard key={c.id} chart={c} dark={dark} onInvestigate={investigate} highlight={focus.includes(c.id)} />)}</div>}
        {running && run?.charts.length === 0 && <div className="grid gap-4 grid-cols-2"><div className="skeleton h-72" /><div className="skeleton h-72" /></div>}
        {run?.report && <ReportView report={run.report} onEvidence={showEvidence} />}
      </main>

      <aside className="border-l flex flex-col min-h-0" style={{ borderColor: "var(--line)" }}>
        <div className="p-3 border-b space-y-2" style={{ borderColor: "var(--line)" }}>
          <div className="muted text-xs uppercase tracking-wide">AI analyst <span className="normal-case">· Ctrl/⌘ K</span></div>
          <textarea ref={qRef} rows={3} value={question} onChange={e => setQuestion(e.target.value)} disabled={!ds || running}
            onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) start(question); }} />
          <button className="btn btn-primary w-full" disabled={!ds || running || !question.trim()} onClick={() => start(question)}>{running ? "Researching…" : "Research"}</button>
          {!ds && <p className="muted text-xs">Load a dataset first.</p>}
        </div>
        <div className="flex-1 overflow-auto p-3">
          {error && <p className="mb-2" style={{ color: "var(--bad)" }}>{error}</p>}
          <Timeline events={events} running={running} />
        </div>
      </aside>
    </div>
    {settings && <Settings model={model} onClose={() => setSettings(false)} />}
  </div>;
}
