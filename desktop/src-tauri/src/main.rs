// Starts the Python analytics service as a sidecar (bundle with PyInstaller as binaries/analytics-service-<target-triple>).
// In dev you can instead run `uvicorn backend.api.app:app --port 8765` yourself; the UI talks to 127.0.0.1:8765.
use tauri_plugin_shell::ShellExt;
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            if let Ok(cmd) = app.shell().sidecar("analytics-service") { let _ = cmd.spawn(); }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running application");
}
