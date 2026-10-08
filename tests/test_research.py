import json, polars as pl, pytest
from backend.ai.provider import LLMProvider, Part, AIError
from backend.data.store import DatasetStore
from backend.research.pipeline import Researcher
from backend.research.run import Run

class Scripted(LLMProvider):
    """Stands in for Gemini: returns scripted JSON, records what it was sent."""
    name = "scripted"
    def __init__(self, handler): self.handler, self.calls, self.sent_log = handler, [], []
    def _generate(self, system, parts):
        self.calls.append((system, parts)); return json.dumps(self.handler(len(self.calls), system, parts))

@pytest.fixture
def ds(tmp_path):
    rows = []
    for m in range(1, 13):
        for r, base in {"East": 100, "West": 100, "North": 100}.items():
            rev = base + m * 2 if r != "West" else (base + m * 2 if m < 7 else 40 + m)   # West collapses from July
            rows.append({"month": f"2024-{m:02d}-01", "region": r, "revenue": float(rev)})
    p = tmp_path / "sales.csv"; pl.DataFrame(rows).write_csv(p)
    store = DatasetStore(); d = store.add(p); return store, d

STEP = {"title": "Monthly revenue by region", "question": "How does revenue trend by region?",
        "sql": "SELECT month, region, SUM(revenue) AS revenue FROM sales GROUP BY 1,2 ORDER BY 1",
        "chart_type": "line", "x": "month", "y": "revenue", "series": "region"}

def handler_factory(bad_number=False):
    def h(n, system, parts):
        if "planning" in system:
            return {"objective": "Regional revenue", "analyses": [STEP,
                    {**STEP, "title": "Bad", "sql": "DROP TABLE sales", "chart_type": "bar"}]}
        if "reading charts" in system:
            chart_txt = next(p.text for p in parts if p.text and p.text.startswith("=== CHART-"))
            cid = chart_txt.split(":")[0].replace("=== ", "")
            stats = json.loads(chart_txt.split("Computed statistics: ")[1].split("\nData table")[0])
            west = stats["series"]["West"]
            findings = [{"claim": f"West revenue fell from {west['max']:.0f} at its peak.", "chart_ids": [cid],
                         "direction": "decrease", "numbers": [{"label": "West peak", "value": west["max"]}],
                         "confidence": "high", "what_in_chart": "West line drops after June"}]
            if bad_number:
                findings.append({"claim": "East grew 73.2%.", "chart_ids": [cid], "direction": "increase",
                                 "numbers": [{"label": "East growth", "value": 73.2}], "confidence": "high", "what_in_chart": "x"})
            return {"findings": findings, "follow_ups": [], "not_enough_evidence": ["Cause of the drop"]}
        return {"executive_summary": "West region revenue dropped after mid-year.", "ranked_finding_ids": ["INSIGHT-001"],
                "hypotheses": ["Possible lost customer (unproven)"], "limitations": ["Single table, no customer data"]}
    return h

def test_end_to_end_pipeline(ds):
    store, d = ds
    llm = Scripted(handler_factory(bad_number=True))
    run = Run(dataset_id=d.id, question="find anything unusual")
    Researcher(store, llm, max_depth=1).run(run)
    assert run.status == "done", run.error
    assert len(run.charts) == 1                                   # DROP TABLE step was refused, not executed
    assert any("skipped" in e["message"] for e in run.events)
    analyze_parts = llm.calls[1][1]
    assert any(p.image_png and p.image_png[:4] == b"\x89PNG" for p in analyze_parts)   # LLM really received the chart image
    verified = [f for f in run.findings if f["verified"]]
    rejected = [f for f in run.findings if not f["verified"]]
    assert len(verified) == 1 and len(rejected) == 1              # hallucinated 73.2% caught
    assert verified[0]["evidence"] == {"charts": ["CHART-001"], "queries": ["QUERY-001"], "datasets": [d.id],
                                       "calculation": ["Monthly revenue by region"]}
    assert run.report["findings"][0]["id"] == verified[0]["id"]
    assert run.report["unverified_count"] == 1
    ch = run.charts["CHART-001"]
    assert ch.stats["series"]["West"]["trend"] == "decrease" and ch.stats["series"]["East"]["trend"] == "increase"
    assert ch.option["series"] and len(ch.option["series"]) == 3

def test_ungrounded_summary_numbers_removed(ds):
    store, d = ds
    base = handler_factory()
    def h(n, s, p):
        r = base(n, s, p)
        if "executive_summary" in r: r["executive_summary"] = "Revenue fell 87.5% in West."
        return r
    run = Run(dataset_id=d.id, question="q"); Researcher(store, Scripted(h), max_depth=0).run(run)
    assert "87.5" not in run.report["executive_summary"] and run.report["ungrounded_numbers_removed"]

def test_no_verified_findings_says_not_enough_evidence(ds):
    store, d = ds
    base = handler_factory()
    def h(n, s, p):
        r = base(n, s, p)
        if "findings" in r: r["findings"] = [{"claim": "Sales are great.", "chart_ids": [], "direction": "none", "confidence": "low", "what_in_chart": ""}]
        return r
    run = Run(dataset_id=d.id, question="q"); Researcher(store, Scripted(h), max_depth=0).run(run)
    assert "not enough evidence" in run.report["executive_summary"].lower()

def test_deep_dive_loop_respects_max_depth(ds):
    store, d = ds
    base = handler_factory()
    def h(n, s, p):
        r = base(n, s, p)
        if "follow_ups" in r: r["follow_ups"] = [{**STEP, "title": f"Deeper {n}"}]
        return r
    run = Run(dataset_id=d.id, question="q"); llm = Scripted(h)
    Researcher(store, llm, max_depth=2).run(run)
    analyze_calls = [c for c in llm.calls if "reading charts" in c[0]]
    assert len(analyze_calls) == 3 and run.status == "done"       # initial + 2 deep-dives, then stops

def test_ai_failure_is_friendly(ds):
    store, d = ds
    class Boom(LLMProvider):
        sent_log = []
        def _generate(self, s, p): raise AIError("Gemini free-tier limit reached.")
    run = Run(dataset_id=d.id, question="q"); Researcher(store, Boom()).run(run)
    assert run.status == "error" and "free-tier" in run.error

def test_gemini_client_payload_and_rate_limit_retry(monkeypatch):
    import httpx, time
    from backend.ai.gemini import GeminiProvider
    monkeypatch.setattr(time, "sleep", lambda s: None)
    seen = []
    def handler(req: httpx.Request):
        seen.append(req)
        if len(seen) == 1: return httpx.Response(429, json={"error": "quota"})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{\"objective\":\"x\",\"analyses\":[]}"}]}}]})
    g = GeminiProvider("KEY", "gemini-test", rpm=600, transport=httpx.MockTransport(handler))
    from backend.models.schemas import Plan
    out = g.structured("sys", [Part(text="hi"), Part(image_png=b"\x89PNGfake")], Plan)
    assert out.objective == "x" and len(seen) == 2
    body = json.loads(seen[1].content)
    assert seen[1].headers["x-goog-api-key"] == "KEY" and "gemini-test" in str(seen[1].url)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert any("inline_data" in p for p in body["contents"][0]["parts"])
    assert g.sent_log and g.sent_log[0]["images"] == 1


def test_research_api_flow(ds, tmp_path):
    import time
    from fastapi.testclient import TestClient
    from backend.api import app as appmod
    store, d = ds
    appmod.store = store                       # use the dataset created in the fixture
    appmod.state["llm"] = Scripted(handler_factory())
    c = TestClient(appmod.app)
    rid = c.post("/research", json={"dataset_id": d.id, "question": "unusual?"}).json()["id"]
    for _ in range(100):
        snap = c.get(f"/research/{rid}").json()
        if snap["status"] != "running": break
        time.sleep(0.1)
    assert snap["status"] == "done" and snap["report"]["findings"] and snap["charts"][0]["option"]["series"]
    assert c.get(f"/research/{rid}/charts/CHART-001.png").content[:4] == b"\x89PNG"
    assert c.post("/research", json={"dataset_id": "nope", "question": "x"}).status_code == 404
    appmod.state["llm"] = None
