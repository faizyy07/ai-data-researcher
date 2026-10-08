import { useState } from "react"; import { api } from "../api";
export function Settings({ onClose, model }: { onClose: () => void; model: string }) {
  const [key, setKey] = useState(""); const [m, setM] = useState(model); const [msg, setMsg] = useState("");
  const save = async () => { try { await api.setAi({ api_key: key || undefined, model: m }); setMsg("Saved."); setTimeout(onClose, 500); } catch (e) { setMsg((e as Error).message); } };
  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/40" onClick={onClose}><div className="panel p-5 w-[420px] space-y-3" onClick={e => e.stopPropagation()}>
    <h2 className="font-semibold">AI settings (Gemini free tier)</h2>
    <label className="block"><span className="muted text-xs">API key (from Google AI Studio)</span><input type="password" value={key} onChange={e => setKey(e.target.value)} placeholder="Paste key" /></label>
    <label className="block"><span className="muted text-xs">Model (free-tier lineups change: check AI Studio)</span><input value={m} onChange={e => setM(e.target.value)} /></label>
    <p className="muted text-xs">The original file stays local. Gemini receives schema details and up to five sample rows per table for planning, plus query results and chart images for analysis. Avoid sensitive data. The key is held in memory by the local service for this session.</p>
    <div className="flex justify-end gap-2 items-center"><span className="muted text-xs">{msg}</span><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={save}>Save</button></div></div></div>;
}
