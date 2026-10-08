"""FastAPI service. Thin layer: validation + error mapping only."""
from __future__ import annotations
import logging, shutil, tempfile
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
import duckdb
from backend.data.ingest import IngestError, SUPPORTED
from backend.data.store import DatasetStore
from backend.security.sql_validator import UnsafeQueryError

log = logging.getLogger("backend")
app = FastAPI(title="AI Data Researcher", version="0.1.0")
store = DatasetStore()

class PathBody(BaseModel):
    path: str

class QueryBody(BaseModel):
    sql: str
    max_rows: int = 1000

def _summary(ds) -> dict:
    return {"id": ds.id, "filename": ds.filename, "sha256": ds.sha256,
            "tables": [{"name": t["name"], "sheet": t["sheet"], "rows": t["rows"],
                        "columns": len(t["columns"])} for t in ds.profile["tables"]]}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/datasets/open")
def open_dataset(body: PathBody):
    """Desktop path: Tauri passes a local file path; the file is only read."""
    try:
        return _summary(store.add(body.path))
    except IngestError as e:
        raise HTTPException(422, str(e))

@app.post("/datasets/upload")
async def upload_dataset(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED:
        raise HTTPException(422, f"Unsupported file type '{ext}'. Use CSV, TSV or XLSX.")
    tmpdir = Path(tempfile.mkdtemp(prefix="adr_"))
    dest = tmpdir / Path(file.filename).name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        return _summary(store.add(dest))
    except IngestError as e:
        raise HTTPException(422, str(e))

@app.get("/datasets")
def list_datasets():
    return [_summary(d) for d in store.list()]

@app.get("/datasets/{dataset_id}/profile")
def get_profile(dataset_id: str):
    try:
        return store.get(dataset_id).profile
    except KeyError:
        raise HTTPException(404, "Dataset not found.")

@app.post("/datasets/{dataset_id}/query")
def query(dataset_id: str, body: QueryBody):
    try:
        df = store.run_readonly_query(dataset_id, body.sql, min(body.max_rows, 10_000))
    except KeyError:
        raise HTTPException(404, "Dataset not found.")
    except UnsafeQueryError as e:
        raise HTTPException(400, str(e))
    except duckdb.Error as e:
        log.warning("query failed: %s", e)
        raise HTTPException(400, "The query could not be executed. Check table/column names and syntax.")
    return {"columns": df.columns, "rows": df.rows(), "row_count": df.height}


# ---------------- AI settings + research ----------------
import threading
from fastapi.middleware.cors import CORSMiddleware
from backend.ai.gemini import GeminiProvider
from backend.ai.provider import AIError, LLMProvider
from backend.config import settings
from backend.research.pipeline import Researcher
from backend.research.run import Run

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:1420", "http://localhost:5173", "tauri://localhost", "http://tauri.localhost"],
                   allow_methods=["*"], allow_headers=["*"])
state: dict = {"llm": None}
runs: dict[str, Run] = {}

class AISettings(BaseModel):
    api_key: str | None = None
    model: str | None = None

def get_llm() -> LLMProvider:
    if state["llm"] is None:
        try:
            state["llm"] = GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.gemini_rpm)
        except AIError as e:
            raise HTTPException(400, str(e))
    return state["llm"]

@app.get("/settings/ai")
def ai_status():
    return {"provider": settings.ai_provider, "model": settings.gemini_model, "has_key": bool(settings.gemini_api_key)}

@app.post("/settings/ai")
def set_ai(body: AISettings):
    if body.api_key is not None: settings.gemini_api_key = body.api_key.strip()
    if body.model: settings.gemini_model = body.model.strip()
    state["llm"] = None
    return ai_status()

@app.get("/settings/ai/sent-log")
def sent_log():
    llm = state["llm"]
    return llm.sent_log if llm else []

class ResearchBody(BaseModel):
    dataset_id: str
    question: str

@app.post("/research")
def start_research(body: ResearchBody):
    try:
        store.get(body.dataset_id)
    except KeyError:
        raise HTTPException(404, "Dataset not found.")
    if not body.question.strip():
        raise HTTPException(422, "Please enter a research question.")
    llm = get_llm()
    run = Run(dataset_id=body.dataset_id, question=body.question.strip())
    runs[run.id] = run
    threading.Thread(target=Researcher(store, llm).run, args=(run,), daemon=True).start()
    return {"id": run.id}

@app.get("/research/{run_id}")
def get_research(run_id: str, since: int = 0):
    if run_id not in runs:
        raise HTTPException(404, "Research run not found.")
    return runs[run_id].snapshot(since)

@app.get("/research/{run_id}/charts/{chart_id}.png")
def chart_png(run_id: str, chart_id: str):
    from fastapi.responses import Response
    run = runs.get(run_id)
    if not run or chart_id not in run.charts:
        raise HTTPException(404, "Chart not found.")
    return Response(run.charts[chart_id].png, media_type="image/png")
