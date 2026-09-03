use serde::Serialize;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, RunEvent};

struct BackendState {
    child: Mutex<Option<Child>>,
    base_url: Mutex<String>,
    ready: Mutex<bool>,
}

#[derive(Serialize, Clone)]
struct BackendInfo {
    base_url: String,
    ready: bool,
    offline_mode: bool,
}

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| PathBuf::from("."))
}

fn venv_python(root: &Path) -> PathBuf {
    root.join("backend/.venv/bin/python")
}

fn production_data_dir() -> PathBuf {
    if let Ok(v) = std::env::var("OFFLINEVOICE_DATA_DIR") {
        return PathBuf::from(v);
    }
    dirs_next::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Library/Application Support/AYUAKSHU Audio")
}

fn production_models_dir(data: &Path) -> PathBuf {
    if let Ok(v) = std::env::var("OFFLINEVOICE_MODELS_DIR") {
        return PathBuf::from(v);
    }
    data.join("models")
}

fn wait_for_endpoint(endpoint_file: &Path, timeout: Duration) -> Result<String, String> {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if endpoint_file.is_file() {
            if let Ok(raw) = fs::read_to_string(endpoint_file) {
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw) {
                    if let Some(url) = v.get("base_url").and_then(|x| x.as_str()) {
                        return Ok(url.to_string());
                    }
                }
            }
        }
        thread::sleep(Duration::from_millis(200));
    }
    Err(format!(
        "Timed out waiting for backend endpoint at {}",
        endpoint_file.display()
    ))
}

fn drain_child_pipes(child: &mut Child) {
    if let Some(stdout) = child.stdout.take() {
        thread::spawn(move || {
            for line in BufReader::new(stdout).lines().flatten() {
                log::info!("[backend] {line}");
            }
        });
    }
    if let Some(stderr) = child.stderr.take() {
        thread::spawn(move || {
            for line in BufReader::new(stderr).lines().flatten() {
                log::warn!("[backend] {line}");
            }
        });
    }
}

fn resolve_bundled_backend(app: &AppHandle) -> Option<PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    let candidates = [
        // Tauri copies `bundle.resources` paths under Contents/Resources/, preserving
        // the relative path from src-tauri (e.g. resources/backend/...).
        resource_dir.join("resources/backend/offlinevoice-backend/offlinevoice-backend"),
        resource_dir.join("backend/offlinevoice-backend/offlinevoice-backend"),
        resource_dir.join("offlinevoice-backend/offlinevoice-backend"),
        // Dev convenience: resources may live next to src-tauri during local testing.
        project_root().join("src-tauri/resources/backend/offlinevoice-backend/offlinevoice-backend"),
    ];
    candidates.into_iter().find(|p| p.is_file())
}

fn spawn_backend_dev(root: &Path) -> Result<(Child, String, PathBuf), String> {
    let python = venv_python(root);
    if !python.is_file() {
        return Err(format!(
            "Python venv not found at {}. Run ./scripts/setup_dev.sh first.",
            python.display()
        ));
    }

    let data = if let Ok(v) = std::env::var("OFFLINEVOICE_DATA_DIR") {
        PathBuf::from(v)
    } else {
        root.join("outputs/app_data")
    };
    let models = if let Ok(v) = std::env::var("OFFLINEVOICE_MODELS_DIR") {
        PathBuf::from(v)
    } else {
        root.join("models")
    };

    fs::create_dir_all(data.join("cache")).map_err(|e| e.to_string())?;
    let endpoint_file = data.join("cache/backend_endpoint.json");
    let _ = fs::remove_file(&endpoint_file);

    let mut cmd = Command::new(&python);
    cmd.env("PYTHONPATH", root.join("backend"))
        .env("HF_HUB_OFFLINE", "1")
        .env("TRANSFORMERS_OFFLINE", "1")
        .env("HF_DATASETS_OFFLINE", "1")
        .env("OFFLINEVOICE_MODELS_DIR", &models)
        .env("OFFLINEVOICE_DATA_DIR", &data)
        .arg("-m")
        .arg("app.main")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg("0")
        .arg("--data-dir")
        .arg(&data)
        .current_dir(root.join("backend"))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start backend: {e}"))?;
    drain_child_pipes(&mut child);
    let base_url = wait_for_endpoint(&endpoint_file, Duration::from_secs(90))?;
    Ok((child, base_url, data))
}

fn spawn_backend_prod(app: &AppHandle) -> Result<(Child, String, PathBuf), String> {
    let backend_bin = resolve_bundled_backend(app).ok_or_else(|| {
        "Bundled backend binary missing. Rebuild with ./scripts/bundle_backend.sh".to_string()
    })?;

    let data = production_data_dir();
    let models = production_models_dir(&data);
    fs::create_dir_all(data.join("cache")).map_err(|e| e.to_string())?;
    fs::create_dir_all(&models).map_err(|e| e.to_string())?;
    let endpoint_file = data.join("cache/backend_endpoint.json");
    let _ = fs::remove_file(&endpoint_file);

    let mut cmd = Command::new(&backend_bin);
    cmd.env("HF_HUB_OFFLINE", "1")
        .env("TRANSFORMERS_OFFLINE", "1")
        .env("HF_DATASETS_OFFLINE", "1")
        .env("OFFLINEVOICE_MODELS_DIR", &models)
        .env("OFFLINEVOICE_DATA_DIR", &data)
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg("0")
        .arg("--data-dir")
        .arg(&data)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    // Run next to _internal libs.
    if let Some(dir) = backend_bin.parent() {
        cmd.current_dir(dir);
    }

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start bundled backend: {e}"))?;
    drain_child_pipes(&mut child);
    let base_url = wait_for_endpoint(&endpoint_file, Duration::from_secs(120))?;
    Ok((child, base_url, data))
}

fn spawn_backend(app: &AppHandle) -> Result<(Child, String), String> {
    let (child, url, _data) = if cfg!(debug_assertions) {
        spawn_backend_dev(&project_root())?
    } else if resolve_bundled_backend(app).is_some() {
        spawn_backend_prod(app)?
    } else {
        // Fallback for local `tauri build` testing without a full bundle.
        spawn_backend_dev(&project_root())?
    };
    Ok((child, url))
}

fn stop_backend(state: &BackendState) {
    if let Ok(mut guard) = state.child.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[tauri::command]
fn get_backend_info(state: tauri::State<'_, BackendState>) -> BackendInfo {
    BackendInfo {
        base_url: state.base_url.lock().unwrap().clone(),
        ready: *state.ready.lock().unwrap(),
        offline_mode: true,
    }
}

#[tauri::command]
fn get_backend_url(state: tauri::State<'_, BackendState>) -> Result<String, String> {
    let ready = *state.ready.lock().unwrap();
    let url = state.base_url.lock().unwrap().clone();
    if !ready || url.is_empty() {
        return Err("Backend is not ready yet".into());
    }
    Ok(url)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState {
            child: Mutex::new(None),
            base_url: Mutex::new(String::new()),
            ready: Mutex::new(false),
        })
        .invoke_handler(tauri::generate_handler![get_backend_url, get_backend_info])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let handle = app.handle().clone();
            thread::spawn(move || match spawn_backend(&handle) {
                Ok((child, url)) => {
                    let state = handle.state::<BackendState>();
                    *state.child.lock().unwrap() = Some(child);
                    *state.base_url.lock().unwrap() = url.clone();
                    *state.ready.lock().unwrap() = true;
                    log::info!("AYUAKSHU Audio backend ready at {url}");
                    let _ = handle.emit("backend-ready", url);
                }
                Err(err) => {
                    log::error!("Backend failed to start: {err}");
                    let _ = handle.emit("backend-error", err);
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building AYUAKSHU Audio")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                let state = app_handle.state::<BackendState>();
                stop_backend(&state);
            }
        });
}
