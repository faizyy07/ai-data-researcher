# AI Data Researcher

AI-assisted exploratory analysis for CSV, TSV, and Excel files. The app profiles data and runs analytics locally with DuckDB and Polars; Gemini helps plan questions and interpret charts. Findings are checked against computed chart data before they appear in the report.

## Features

- Load CSV, TSV, and XLSX files and inspect their profiles.
- Generate read-only DuckDB analyses and interactive ECharts visualizations.
- Ask Gemini to plan analyses, interpret chart images, and suggest follow-up questions.
- Verify claims and reported numbers against computed results, with links from findings to charts, queries, and datasets.
- Use the browser UI locally, with an optional Tauri desktop shell.

## Requirements

- Python 3.10 or newer
- Node.js and npm
- A Gemini API key for AI research (the UI can be opened without one)
- Rust toolchain only if building the optional Tauri desktop shell

## Run on Windows

From the project root, install backend dependencies:

```powershell
python -m pip install -r backend/requirements.txt
```

In a first PowerShell terminal, start the backend:

```powershell
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765
```

In a second terminal, start the browser UI:

```powershell
Set-Location desktop
npm install
npm run dev -- --host localhost
```

Open <http://localhost:1420/>. Use **AI Settings** to enter your Gemini API key and select a model available to your account. The key is held in backend memory and is cleared when the backend restarts. Do not commit API keys or `.env` files.

To configure the key through the environment instead, set `GEMINI_API_KEY` before starting the backend. `GEMINI_MODEL` and `GEMINI_RPM` can also be set; check Google AI Studio for currently available models and account limits.

## Run on macOS or Linux

From the project root, install dependencies with `python -m pip install -r backend/requirements.txt`. Start the backend with `python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765`. In another terminal, run `cd desktop`, `npm install`, and `npm run dev -- --host localhost`, then open <http://localhost:1420/>.

## Tests and build

Run backend tests from the project root:

```powershell
python -m pytest -q tests
```

Check and build the UI from `desktop`:

```powershell
npm run build
```

## Data and privacy

The original file is read locally and is not uploaded by the app. For AI planning, the backend sends Gemini dataset schema/profile information and up to five sample rows per table. For chart analysis, it also sends query results, computed statistics, and chart images. Do not use sensitive data unless you are comfortable sharing those excerpts with Google under the terms of your account. Check Google AI Studio for current data-use terms. The local backend exposes a sent-log at `/settings/ai/sent-log`.

The backend is intended for local use and binds to `127.0.0.1` in the commands above. Keep it bound to loopback unless you have separately configured appropriate access controls.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | empty | Gemini API key; alternatively enter it in AI Settings |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model name; availability can change |
| `GEMINI_RPM` | `8` | Request pacing per minute |
| `MAX_INVESTIGATION_DEPTH` | `2` | Maximum follow-up analysis rounds |

See [backend/README.md](backend/README.md) for the service and [desktop/README.md](desktop/README.md) for the UI and optional desktop shell.
