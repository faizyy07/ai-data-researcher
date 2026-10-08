export const API = (import.meta.env.VITE_API_URL as string) || "http://127.0.0.1:8765";
export type DatasetSummary = { id: string; filename: string; tables: { name: string; rows: number; columns: number; sheet: string | null }[] };
export type Chart = { id: string; title: string; question: string; query_id: string; dataset_id: string; sql: string; chart_type: string;
  option: Record<string, unknown>; stats: Record<string, unknown>; table: { columns: string[]; rows: unknown[][] } };
export type Finding = { id: string; claim: string; direction: string; confidence: string; what_in_chart: string; verified: boolean; rejection_reasons: string[];
  evidence: { charts: string[]; queries: string[]; datasets: string[]; calculation: string[] } };
export type RunEvent = { i: number; step: string; status: "running" | "done" | "error" | "info"; message: string };
export type Report = { executive_summary: string; findings: Finding[]; hypotheses: string[]; limitations: string[]; unverified_count: number };
export type RunSnapshot = { id: string; status: "running" | "done" | "error"; error: string | null; events: RunEvent[]; next: number; charts: Chart[]; findings: Finding[]; report: Report | null };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try { r = await fetch(API + path, init); } catch { throw new Error("Cannot reach the analytics service. Is the backend running?"); }
  if (!r.ok) { let d = "Request failed."; try { d = (await r.json()).detail ?? d; } catch { /* ignore */ } throw new Error(String(d)); }
  return r.json();
}
export const api = {
  upload: (f: File) => { const fd = new FormData(); fd.append("file", f); return call<DatasetSummary>("/datasets/upload", { method: "POST", body: fd }); },
  profile: (id: string) => call<{ tables: { name: string; rows: number; duplicate_rows: number; columns: { name: string; dtype: string; semantic_role: string | null; missing_pct: number; unique: number }[] }[] }>(`/datasets/${id}/profile`),
  aiStatus: () => call<{ model: string; has_key: boolean }>("/settings/ai"),
  setAi: (b: { api_key?: string; model?: string }) => call("/settings/ai", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(b) }),
  start: (dataset_id: string, question: string) => call<{ id: string }>("/research", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ dataset_id, question }) }),
  poll: (id: string, since: number) => call<RunSnapshot>(`/research/${id}?since=${since}`),
};
