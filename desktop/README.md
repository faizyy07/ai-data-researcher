# Desktop UI

The React and Vite UI runs in a browser and communicates with the local FastAPI service at `http://127.0.0.1:8765`.

From the project root, start the backend as described in [backend/README.md](../backend/README.md). Then start the UI:

```powershell
Set-Location desktop
npm install
npm run dev -- --host localhost
```

Open <http://localhost:1420/>. Use **AI Settings** to enter the Gemini key; it is held in backend memory for the current session.

Create a production frontend bundle with `npm run build` from this directory. The Tauri shell is configured under `src-tauri` and requires Rust; packaging also expects an analytics sidecar, so native desktop bundling may need additional setup.