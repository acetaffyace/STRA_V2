use std::net::TcpListener;
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, State};
use tauri_plugin_shell::ShellExt;

/// Find a free port by binding to port 0.
fn find_free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .expect("Failed to bind to find free port")
        .local_addr()
        .expect("Failed to get local address")
        .port()
}

/// Health-check the backend within the same bounded window exposed by the UI.
async fn wait_for_backend(port: u16) -> bool {
    let url = format!("http://127.0.0.1:{}/health", port);
    let client = reqwest::Client::new();
    let interval = Duration::from_millis(500);
    let deadline = tokio::time::Instant::now() + Duration::from_secs(60);

    loop {
        match client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => return true,
            _ => {}
        }

        if tokio::time::Instant::now() >= deadline {
            return false;
        }
        tokio::time::sleep(interval).await;
    }
}

/// Inject a boot error into the webview so the frontend can display it.
fn inject_boot_error(handle: &tauri::AppHandle, error: &str) {
    let escaped = error.replace('\\', "\\\\").replace('\'', "\\'");
    let js = format!(
        "window.__SENTINEXT_BACKEND_BOOT_ERROR__ = '{}';",
        escaped
    );
    if let Some(window) = handle.get_webview_window("main") {
        let _ = window.eval(&js);
    }
}

/// Authoritative desktop bootstrap contract: the UI asks Tauri for the port
/// selected for this process instead of racing a page-load JavaScript hook.
#[tauri::command]
fn get_backend_url(state: State<'_, Mutex<u16>>) -> String {
    let port = state.lock().expect("backend port state poisoned");
    format!("http://127.0.0.1:{}", *port)
}

pub fn run() {
    let port = find_free_port();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(move |app| {
            let handle = app.handle().clone();

            // Store port in app state for later access
            app.manage(Mutex::new(port));

            // Spawn the Python sidecar — handle errors gracefully so the
            // window still opens and can show an error message to the user.
            let shell = handle.shell();
            let sidecar = match shell.sidecar("sentinext-backend") {
                Ok(cmd) => cmd.args(["--port", &port.to_string()]),
                Err(err) => {
                    eprintln!("Failed to create sidecar command: {err}");
                    let handle_clone = handle.clone();
                    let err_msg = format!("Failed to create sidecar command: {err}");
                    tauri::async_runtime::spawn(async move {
                        inject_boot_error(&handle_clone, &err_msg);
                    });
                    return Ok(());
                }
            };

            match sidecar.spawn() {
                Ok((_rx, child)) => {
                    // Store the child process for cleanup
                    app.manage(Mutex::new(Some(child)));

                    // Run a bounded health check. The Started page-load hook
                    // is the canonical URL handoff; this task only reports a
                    // sidecar that never became ready.
                    let handle_clone = handle.clone();
                    tauri::async_runtime::spawn(async move {
                        if !wait_for_backend(port).await {
                            inject_boot_error(
                                &handle_clone,
                                "本地分析服务启动超时，请重试。",
                            );
                        }
                    });
                }
                Err(err) => {
                    eprintln!("Failed to spawn sidecar: {err}");
                    let handle_clone = handle.clone();
                    let err_msg = format!("Failed to spawn sidecar: {err}");
                    tauri::async_runtime::spawn(async move {
                        inject_boot_error(&handle_clone, &err_msg);
                    });
                }
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_backend_url])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // Kill the sidecar process on window close
                let app = window.app_handle();
                if let Some(state) = app.try_state::<Mutex<Option<tauri_plugin_shell::process::CommandChild>>>() {
                    if let Ok(mut guard) = state.lock() {
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
