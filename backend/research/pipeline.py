"""Research pipeline: schema -> plan -> fetch -> charts -> analyze charts -> deep-dive -> verified report.

Two lanes: the LLM may explore schema/samples freely when PLANNING, but findings are
accepted only when they cite charts and pass the verifier against computed chart data.
"""
from __future__ import annotations
import json, logging
import duckdb
from backend.ai.provider import LLMProvider, Part, AIError
from backend.charts.builder import build_chart, ChartError, Chart
from backend.config import settings
from backend.data.store import DatasetStore
from backend.evidence.verifier import verify_finding, summary_numbers_grounded, chart_numbers
from backend.models.schemas import Plan, Analysis, Report, AnalysisStep, Finding
from backend.research.run import Run
from backend.security.sql_validator import UnsafeQueryError

log = logging.getLogger("pipeline")

PLAN_SYS = """You are a careful data research analyst planning an investigation. A deterministic analytics
engine (DuckDB) will execute your SQL and render charts; you never compute results yourself.
Rules: write read-only DuckDB SQL against the listed tables only; aggregate in SQL (<=500 rows per result);
every analysis must produce one chart (line for time trends, bar for rankings/comparisons, scatter for relationships,
histogram for distributions). Cover the user's question and, if asked, anything unusual (trends, segment gaps, outliers,
concentration). Name result columns exactly as used in x/y/series."""

ANALYZE_SYS = """You are a data analyst reading charts. You receive each chart as an IMAGE plus its computed statistics and data table.
Rules for findings: (1) every finding must cite chart_ids it is based on; (2) copy every number EXACTLY from the provided
statistics/table, never estimate values off the axes or compute new ones; (3) state `direction` honestly; (4) do not claim
causation, only what the charts show; (5) if the charts cannot answer something, list it in not_enough_evidence instead of guessing;
(6) if something interesting needs a deeper look (a segment, period or driver), propose follow_ups as new analyses (SQL + chart)."""

REPORT_SYS = """Write the executive summary of a research report using ONLY the verified findings provided. Do not add facts or numbers
not present in them. Rank findings by importance via ranked_finding_ids. Give hypotheses only as clearly-labelled possibilities
and list limitations of what this data cannot establish."""

def schema_context(store: DatasetStore, dataset_id: str) -> str:
    ds = store.get(dataset_id)
    out = []
    for t, lt in zip(ds.profile["tables"], ds.tables):
        cols = []
        for c in t["columns"]:
            d = {k: c[k] for k in ("name", "dtype", "semantic_role", "missing_pct", "unique") if k in c}
            if "stats" in c: d["range"] = [c["stats"]["min"], c["stats"]["max"]]
            if "top_values" in c: d["top"] = [v["value"] for v in c["top_values"]]
            cols.append(d)
        out.append({"table": t["name"], "rows": t["rows"], "columns": cols, "date_columns": t["date_columns"],
                    "sample_rows": lt.df.head(5).to_dicts()})
    return json.dumps({"tables": out, "relationships": ds.profile["relationships"]}, default=str)

class Researcher:
    def __init__(self, store: DatasetStore, llm: LLMProvider, max_depth: int | None = None):
        self.store, self.llm = store, llm
        self.max_depth = settings.max_depth if max_depth is None else max_depth

    # ---- step 3+4: fetch and chart -------------------------------------------------
    def _execute(self, run: Run, step: AnalysisStep, label: str) -> Chart | None:
        qid = run.next_id("QUERY")
        try:
            df = self.store.run_readonly_query(run.dataset_id, step.sql, 5000)
            chart = build_chart(run.next_id("CHART"), step, df, qid, run.dataset_id)
        except (UnsafeQueryError, ChartError) as e:
            run.event(label, "error", f"'{step.title}' skipped: {e}"); return None
        except duckdb.Error:
            run.event(label, "error", f"'{step.title}' skipped: the query failed to run."); return None
        run.charts[chart.id] = chart
        run.event(label, "done", f"{chart.id}: {chart.title}")
        return chart

    def _chart_parts(self, charts: list[Chart]) -> list[Part]:
        parts: list[Part] = []
        for c in charts:
            parts.append(Part(text=f"=== {c.id}: {c.title}\nQuestion: {c.question}\nChart type: {c.step.chart_type}\n"
                                   f"Computed statistics: {json.dumps(c.stats, default=str)}\n"
                                   f"Data table ({len(c.table['rows'])} rows): {json.dumps(c.table, default=str)[:6000]}"))
            parts.append(Part(image_png=c.png))
        return parts

    def _record(self, run: Run, findings: list[Finding]) -> int:
        ok_count = 0
        for f in findings:
            ok, reasons = verify_finding(f, run.charts)
            iid = run.next_id("INSIGHT")
            charts = [run.charts[c] for c in f.chart_ids if c in run.charts]
            run.findings.append({"id": iid, "claim": f.claim, "direction": f.direction, "confidence": f.confidence,
                                 "what_in_chart": f.what_in_chart, "numbers": [n.model_dump() for n in f.numbers],
                                 "verified": ok, "rejection_reasons": reasons,
                                 "evidence": {"charts": f.chart_ids, "queries": [c.query_id for c in charts],
                                              "datasets": sorted({c.dataset_id for c in charts}),
                                              "calculation": [c.title for c in charts]}})
            ok_count += ok
            run.event("verify", "done" if ok else "info", f"{iid} {'verified' if ok else 'rejected: ' + '; '.join(reasons)}")
        return ok_count

    # ---- full run ---------------------------------------------------------------------
    def run(self, run: Run) -> None:
        self.llm.on_wait = lambda m: run.event("ai", "info", m)
        try:
            run.event("schema", "running", "Analyzing dataset schema")
            ctx = schema_context(self.store, run.dataset_id)
            run.event("schema", "done", "Dataset schema analyzed")

            run.event("plan", "running", "Understanding your question and planning the investigation")
            plan = self.llm.structured(PLAN_SYS, [Part(text=f"Dataset:\n{ctx}\n\nUser request: {run.question}\n"
                                       f"Plan at most {settings.max_steps_per_round} analyses.")], Plan)
            run.event("plan", "done", f"Plan: {plan.objective} ({len(plan.analyses)} analyses)")

            steps = plan.analyses[: settings.max_steps_per_round]
            for depth in range(self.max_depth + 1):
                label = "fetch" if depth == 0 else f"deep-dive {depth}"
                run.event(label, "running", f"Running {len(steps)} analyses")
                charts = [c for s in steps if (c := self._execute(run, s, label))]
                if not charts:
                    run.event(label, "error", "No charts could be generated this round"); break
                run.event("analyze", "running", f"Reading {len(charts)} charts")
                prior = [f["claim"] for f in run.findings if f["verified"]]
                a = self.llm.structured(ANALYZE_SYS, [Part(text=f"User request: {run.question}\nAlready established: {json.dumps(prior)}\n"
                                        f"Schema (for follow-up SQL): {ctx}")] + self._chart_parts(charts), Analysis)
                n = self._record(run, a.findings)
                run.event("analyze", "done", f"{n}/{len(a.findings)} findings verified against chart data")
                for gap in a.not_enough_evidence:
                    run.event("analyze", "info", f"Not enough evidence: {gap}")
                if not a.follow_ups or depth == self.max_depth:
                    break
                steps = a.follow_ups[: settings.max_steps_per_round]
                run.event("deep-dive", "info", f"Investigating further: {', '.join(s.title for s in steps)}")

            verified = [f for f in run.findings if f["verified"]]
            run.event("report", "running", "Writing report from verified evidence")
            if not verified:
                run.report = {"executive_summary": "There is not enough evidence in the available data to determine this.",
                              "findings": [], "hypotheses": [], "limitations": ["No finding could be verified against chart evidence."],
                              "unverified_count": len(run.findings)}
            else:
                payload = json.dumps([{"id": f["id"], "claim": f["claim"], "confidence": f["confidence"]} for f in verified])
                rep = self.llm.structured(REPORT_SYS, [Part(text=f"User request: {run.question}\nVerified findings: {payload}")], Report)
                grounded = [n["value"] for f in verified for n in f["numbers"]] + [n for f in verified for c in f["evidence"]["charts"] for n in chart_numbers(run.charts[c])]
                bad = summary_numbers_grounded(rep.executive_summary, grounded)
                summary = rep.executive_summary if not bad else \
                    "Summary withheld numbers that could not be traced to evidence. See the verified findings below."
                order = {i: k for k, i in enumerate(rep.ranked_finding_ids)}
                verified.sort(key=lambda f: order.get(f["id"], 999))
                run.report = {"executive_summary": summary, "findings": verified, "hypotheses": rep.hypotheses,
                              "limitations": rep.limitations, "unverified_count": len(run.findings) - len(verified),
                              "ungrounded_numbers_removed": bad}
            run.event("report", "done", "Report ready")
            run.status = "done"
        except AIError as e:
            run.status, run.error = "error", str(e); run.event("error", "error", str(e))
        except Exception:  # noqa: BLE001
            log.exception("research run failed")
            run.status, run.error = "error", "The research run failed unexpectedly. See logs."
            run.event("error", "error", run.error)
