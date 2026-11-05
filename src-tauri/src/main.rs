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
        // Loopback engine; live activation resets on restart and credentials use Windows DPAPI.
        let mut command = std::process::Command::new(exe);
        command.env("IRONTRADE_DATA_DIR", data)
            .env("NIGHTSHIFT_MANAGED_STDIN", "1")
            .stdin(std::process::Stdio::piped())
            // Windows GUI processes have no console; provide valid inherited handles.
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null());
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW; retain the managed stdin pipe.
        }
        let child = command.spawn()?;
        app.manage(EngineProcess(std::sync::Mutex::new(Some(child))));
        Ok(())
    });
    let app = builder.build(tauri::generate_context!()).expect("Could not start NightShift");
    app.run(|_handle, _event| {
        #[cfg(not(debug_assertions))]
        if let tauri::RunEvent::Exit = _event {
            if let Some(state) = _handle.try_state::<EngineProcess>() {
                let child = state.0.lock().ok().and_then(|mut guard| guard.take());
                if let Some(mut child) = child {
                    drop(child.stdin.take());
                    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
                    while matches!(child.try_wait(), Ok(None)) && std::time::Instant::now() < deadline {
                        std::thread::sleep(std::time::Duration::from_millis(50));
                    }
                    if matches!(child.try_wait(), Ok(None)) {
                        #[cfg(target_os = "windows")]
                        {
                            use std::os::windows::process::CommandExt;
                            let _ = std::process::Command::new("taskkill")
                                .args(["/PID", &child.id().to_string(), "/T", "/F"])
                                .creation_flags(0x08000000)
                                .status();
                        }
                        let _ = child.kill();
                    }
                    let _ = child.wait();
                }
            }
        }
    });
}
