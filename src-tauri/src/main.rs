#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{ChildStdin, Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::thread;
use std::time::Duration;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use tauri::{webview::NewWindowResponse, Manager, Theme, Url, WebviewUrl, WebviewWindowBuilder};

struct Engine {
    _stdin: Mutex<ChildStdin>,
}

fn workspace() -> Result<PathBuf, String> {
    if let Some(root) = std::env::var_os("CAPTION_BABY_HOME").map(PathBuf::from) {
        return root.is_dir().then_some(root).ok_or_else(|| {
            "CAPTION_BABY_HOME does not point to an existing folder.".to_string()
        });
    }

    let executable = std::env::current_exe().map_err(|error| error.to_string())?;
    let build_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    executable
        .ancestors()
        .skip(1)
        .map(PathBuf::from)
        .chain(std::iter::once(build_root))
        .find(|folder| folder.join("app.py").is_file())
        .ok_or_else(|| "Could not find the Caption Baby project folder.".into())
}

fn local_endpoint(line: &str) -> Option<Url> {
    let url = Url::parse(line.trim()).ok()?;
    let token = url.path().strip_prefix('/')?.strip_suffix('/')?;
    (url.scheme() == "http"
        && url.host_str() == Some("127.0.0.1")
        && url.port().is_some()
        && url.username().is_empty()
        && url.password().is_none()
        && url.query().is_none()
        && url.fragment().is_none()
        && token.len() == 32
        && token.bytes().all(|byte| byte.is_ascii_hexdigit()))
    .then_some(url)
}

fn start_engine(app: &tauri::App) -> Result<(Engine, Url), String> {
    let bundled = app.path().resource_dir().ok().map(|folder| folder.join("engine"));
    let (root, data, executable, bundled_python) = if let Some(root) = bundled.filter(|root| {
        root.join("app.py").is_file()
            || root.join(if cfg!(windows) { "caption-baby-engine.exe" } else { "caption-baby-engine" }).is_file()
    }) {
        let data = app.path().app_local_data_dir().map_err(|error| error.to_string())?;
        let bundled_python = root.join("app.py").is_file();
        let executable = if bundled_python {
            root.join("python").join("python.exe")
        } else {
            root.join(if cfg!(windows) { "caption-baby-engine.exe" } else { "caption-baby-engine" })
        };
        (root, data, executable, bundled_python)
    } else {
        let root = workspace()?;
        let data = root.join(".venv");
        let executable = if cfg!(windows) {
            data.join("Scripts").join("python.exe")
        } else {
            data.join("bin").join("python")
        };
        (root, data, executable, true)
    };
    if !executable.is_file() {
        return Err("The Python environment is missing. Run Setup Caption Baby.cmd.".into());
    }
    std::fs::create_dir_all(&data).map_err(|error| error.to_string())?;
    let log_path = data.join(format!("desktop-engine-{}.log", std::process::id()));
    let log = File::create(&log_path).map_err(|error| error.to_string())?;
    let search_path = std::env::join_paths(
        std::iter::once(root.join("bin")).chain(std::iter::once(root.clone())).chain(
            std::env::var_os("PATH").iter().flat_map(std::env::split_paths)
        )
    ).map_err(|error| error.to_string())?;
    let mut command = Command::new(executable);
    if bundled_python {
        command.arg(root.join("app.py"));
    }
    command
        .arg("--desktop-engine")
        .current_dir(&root)
        .env("PATH", search_path)
        .env("CAPTION_BABY_DATA", data)
        .env_remove("PYTHONHOME")
        .env_remove("PYTHONPATH")
        .env("PYTHONNOUSERSITE", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::from(log));
    if std::env::args_os().any(|arg| arg == "--from-resolve") {
        command.arg("--from-resolve");
    }
    #[cfg(windows)]
    command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW

    let mut child = command.spawn().map_err(|error| error.to_string())?;
    let stdout = child.stdout.take().expect("stdout is piped");
    let stdin = child.stdin.take().expect("stdin is piped");
    let (send, receive) = mpsc::sync_channel(1);
    thread::spawn(move || {
        let mut stdout = BufReader::new(stdout);
        let mut first_line = String::new();
        let url = stdout
            .read_line(&mut first_line)
            .ok()
            .and_then(|_| local_endpoint(&first_line));
        if send.send(url).is_ok() {
            let _ = std::io::copy(&mut stdout, &mut std::io::sink());
        }
    });
    let url = match receive.recv_timeout(Duration::from_secs(15)) {
        Ok(Some(url)) => url,
        _ => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("The Python engine did not start. See {}.", log_path.display()));
        }
    };
    thread::spawn(move || {
        let _ = child.wait();
    });
    Ok((Engine { _stdin: Mutex::new(stdin) }, url))
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let (target, allowed, error) = match start_engine(app) {
                Ok((engine, url)) => {
                    app.manage(engine);
                    (WebviewUrl::External(url.clone()), Some(url), None)
                }
                Err(error) => (
                    WebviewUrl::App("desktop-error.html".into()),
                    None,
                    Some(error),
                ),
            };
            let detail = error
                .map(|text| serde_json::to_string(&text))
                .transpose()?;
            let desktop_script = match detail {
                Some(detail) => format!(
                    "window.addEventListener('DOMContentLoaded', () => {{ document.getElementById('startup-detail').textContent = {detail}; }});"
                ),
                None => "window.captionBabyDesktop = true;".into(),
            };
            WebviewWindowBuilder::new(app, "main", target)
                .title("Caption Baby")
                .theme(Some(Theme::Dark))
                .inner_size(1360.0, 860.0)
                .min_inner_size(900.0, 620.0)
                .center()
                .disable_drag_drop_handler()
                .on_navigation(move |url| allowed.as_ref().is_none_or(|endpoint| {
                    endpoint.origin() == url.origin() && url.path().starts_with(endpoint.path())
                }))
                .on_new_window(|_, _| NewWindowResponse::Deny)
                .initialization_script(desktop_script)
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Caption Baby could not start");
}

#[cfg(test)]
mod tests {
    use super::local_endpoint;

    #[test]
    fn accepts_only_a_local_session_endpoint() {
        let path = "/0123456789abcdef0123456789abcdef/";
        assert!(local_endpoint(&format!("http://127.0.0.1:51320{path}")).is_some());
        assert!(local_endpoint(&format!("https://127.0.0.1:51320{path}")).is_none());
        assert!(local_endpoint(&format!("http://192.168.0.4:51320{path}")).is_none());
        assert!(local_endpoint(&format!("http://127.0.0.1:51320{path}?other=1")).is_none());
        assert!(local_endpoint("http://127.0.0.1:51320/").is_none());
    }
}
