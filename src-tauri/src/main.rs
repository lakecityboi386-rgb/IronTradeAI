#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
#[cfg(not(debug_assertions))]
use tauri::Manager;
#[cfg(not(debug_assertions))]
struct EngineProcess(std::sync::Mutex<Option<std::process::Child>>);
fn main() {
    let builder = tauri::Builder::default();
    #[cfg(not(debug_assertions))]
    let builder = builder.setup(|app| {
        let data = app.path().app_data_dir()?;
        std::fs::create_dir_all(&data)?;
        let exe = std::env::current_exe()?.parent().ok_or("Missing executable directory")?.join("nightshift-engine.exe");
        // The sidecar only serves paper operations on loopback; no credentials or live orders.
        let child = std::process::Command::new(exe)
            .env("IRONTRADE_DATA_DIR", data)
            .spawn()?;
        app.manage(EngineProcess(std::sync::Mutex::new(Some(child))));
        Ok(())
    });
    let app = builder.build(tauri::generate_context!()).expect("Could not start NightShift");
    app.run(|_handle, _event| {
        #[cfg(not(debug_assertions))]
        if let tauri::RunEvent::Exit = _event {
            if let Some(state) = _handle.try_state::<EngineProcess>() {
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(mut child) = guard.take() { let _ = child.kill(); let _ = child.wait(); }
                }
            }
        }
    });
}
