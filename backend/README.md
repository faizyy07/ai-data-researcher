# Backend

FastAPI service for dataset ingestion, profiling, read-only DuckDB queries, AI research runs, charts, and evidence verification. Start commands from the project root so imports resolve correctly.

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765
```

The browser UI uses `http://127.0.0.1:8765`. The backend CORS allowlist includes the local Vite origins configured by this project.

## Gemini configuration

Set `GEMINI_API_KEY` in the environment before launching the service, or enter the key through the app's AI Settings window. Keys entered in the UI are held in process memory and are not persisted. `GEMINI_MODEL`, `GEMINI_RPM`, and `MAX_INVESTIGATION_DEPTH` are also configurable through environment variables; model availability may change.

The original dataset is read locally. Gemini receives schema/profile details and up to five sample rows per table for planning, plus query output, computed statistics, and chart images for analysis. Avoid sending sensitive datasets unless sharing those excerpts is acceptable.

Run tests from the project root with `python -m pytest -q tests`.