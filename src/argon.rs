use crate::studio::{
    parse_universe, read_places_block, write_places_block, StudioRpc, UNIVERSE_LUAU,
};
use anyhow::{anyhow, bail, Result};
use clap::{Parser, Subcommand};
use fs2::FileExt;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet, HashMap},
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    net::{TcpListener, ToSocketAddrs},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicBool, Ordering},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

static STOP: AtomicBool = AtomicBool::new(false);
#[cfg(unix)]
extern "C" fn stop_signal(_: libc::c_int) {
    STOP.store(true, Ordering::SeqCst);
}
#[derive(Parser)]
#[command(name = "argon")]
struct Args {
    #[command(subcommand)]
    action: Action,
}
#[derive(Subcommand)]
enum Action {
    Ensure {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        port: Option<i64>,
    },
    Status,
    Stop,
    Map {
        name: String,
        place_id: i64,
    },
    #[command(name = "_supervisor", hide = true)]
    Supervisor,
}

fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
fn state_dir() -> PathBuf {
    match std::env::var_os("ARGON_STATE_DIR").filter(|s| !s.is_empty()) {
        Some(p) => {
            let p = PathBuf::from(p);
            if let Ok(rest) = p.strip_prefix("~") {
                dirs::home_dir().unwrap_or_default().join(rest)
            } else {
                p
            }
        }
        None => dirs::home_dir().unwrap_or_default().join(".argon/harness"),
    }
}
fn atomic_json(path: &Path, value: &Value, preserve_mode: bool) -> Result<()> {
    let parent = path.parent().ok_or_else(|| anyhow!("invalid path"))?;
    fs::create_dir_all(parent)?;
    let mut temp = tempfile::Builder::new()
        .prefix(&format!(
            ".{}-",
            path.file_name().unwrap_or_default().to_string_lossy()
        ))
        .tempfile_in(parent)?;
    serde_json::to_writer_pretty(&mut temp, value)?;
    writeln!(temp)?;
    temp.as_file().sync_all()?;
    if preserve_mode {
        fs::set_permissions(temp.path(), fs::metadata(path)?.permissions())?;
    }
    temp.persist(path).map_err(|e| e.error)?;
    Ok(())
}
fn registry_lock() -> Result<File> {
    let dir = state_dir();
    fs::create_dir_all(&dir)?;
    let f = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .open(dir.join("ports.lock"))?;
    f.lock_exclusive()?;
    Ok(f)
}
fn read_registry() -> Result<Value> {
    let data = match fs::read_to_string(state_dir().join("ports.json")) {
        Ok(s) => s,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Ok(json!({"version":1,"roots":[],"ports":{}}))
        }
        Err(e) => bail!("Port registry is unreadable: {e}"),
    };
    let v: Value =
        serde_json::from_str(&data).map_err(|e| anyhow!("Port registry is unreadable: {e}"))?;
    if !v.is_object() || v["version"] != 1 {
        bail!("Port registry has an unsupported format")
    }
    let roots = v["roots"]
        .as_array()
        .ok_or_else(|| anyhow!("Port registry is incomplete"))?;
    let ports = v["ports"]
        .as_object()
        .ok_or_else(|| anyhow!("Port registry is incomplete"))?;
    if roots.iter().any(|r| !r.is_string()) {
        bail!("Port registry is incomplete")
    }
    let mut seen = BTreeSet::new();
    for p in ports.values() {
        let p = p
            .as_u64()
            .filter(|p| *p > 0 && *p <= 65535)
            .ok_or_else(|| anyhow!("Port registry contains an invalid port"))?;
        if !seen.insert(p) {
            bail!("Port registry assigns one port to multiple projects")
        }
    }
    Ok(v)
}
fn register(root: &Path) -> Result<()> {
    let _lock = registry_lock()?;
    let mut v = read_registry()?;
    let mut roots: BTreeSet<String> = v["roots"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_owned)
        .collect();
    roots.insert(root.display().to_string());
    v["roots"] = json!(roots);
    atomic_json(&state_dir().join("ports.json"), &v, false)
}
fn project_path(root: &Path, name: &str) -> Result<PathBuf> {
    let name_ext = if name.ends_with(".project.json") {
        name.to_owned()
    } else {
        format!("{name}.project.json")
    };
    let p = root
        .join(name_ext)
        .canonicalize()
        .map_err(|_| anyhow!("Project file is absent or outside the project root: {name}"))?;
    if !p.starts_with(root) {
        bail!("Project file is absent or outside the project root: {name}")
    }
    if !p.is_file() {
        bail!("Project file is absent: {}", p.display())
    }
    Ok(p)
}
#[derive(Clone)]
struct Mapping {
    name: String,
    place: u64,
    project: PathBuf,
}
fn project_maps(root: &Path) -> Result<Vec<Mapping>> {
    let map = read_places_block(&root.join("AGENTS.md"))
        .map_err(|e| anyhow!("Cannot read the managed places map: {e}"))?;
    let mut result = Vec::new();
    let mut seen = BTreeMap::new();
    for (name, place) in map {
        if place == 0 {
            continue;
        }
        if Path::new(&name).file_name().and_then(|s| s.to_str()) != Some(&name)
            || name == "."
            || name == ".."
        {
            bail!("Invalid project name in places map: {name}")
        }
        let p = root.join(format!("{name}.project.json"));
        if !p.is_file() {
            continue;
        }
        if let Some(prev) = seen.insert(place, name.clone()) {
            bail!("PlaceId {place} is assigned to both {prev} and {name}")
        }
        result.push(Mapping {
            name,
            place,
            project: p.canonicalize()?,
        });
    }
    Ok(result)
}
fn port_available(port: u16) -> bool {
    ("localhost", port)
        .to_socket_addrs()
        .map(|mut a| a.any(|addr| TcpListener::bind(addr).is_ok()))
        .unwrap_or_else(|_| TcpListener::bind(("127.0.0.1", port)).is_ok())
}
fn reserve(project: &Path, requested: Option<i64>) -> Result<u16> {
    let _lock = registry_lock()?;
    let mut v = read_registry()?;
    let key = project.canonicalize()?.display().to_string();
    let ports = v["ports"].as_object_mut().unwrap();
    if let Some(port) = ports.get(&key).and_then(Value::as_u64) {
        if requested.is_some_and(|p| p != port as i64) {
            bail!("Project already owns permanent port {port}")
        }
        return Ok(port as u16);
    }
    if let Some(p) = requested {
        if !(1..=65535).contains(&p) {
            bail!("Port must be between 1 and 65535")
        }
        if let Some((owner, _)) = ports.iter().find(|(_, v)| v.as_u64() == Some(p as u64)) {
            bail!("Port {p} is permanently assigned to {owner}")
        }
    }
    let range: Box<dyn Iterator<Item = u16>> = if let Some(p) = requested {
        Box::new(std::iter::once(p as u16))
    } else {
        Box::new(8000..=65535)
    };
    for p in range {
        if !ports.values().any(|v| v.as_u64() == Some(p as u64)) && port_available(p) {
            ports.insert(key, json!(p));
            atomic_json(&state_dir().join("ports.json"), &v, false)?;
            return Ok(p);
        }
    }
    bail!("No unreserved, available port remains")
}
fn update_identity(project: &Path, place: u64, universe: u64) -> Result<()> {
    let name = project.file_name().unwrap_or_default().to_string_lossy();
    let data = fs::read_to_string(project).map_err(|e| anyhow!("Cannot read {name}: {e}"))?;
    let mut doc: Value =
        serde_json::from_str(&data).map_err(|e| anyhow!("Cannot read {name}: {e}"))?;
    if !doc.is_object() || !doc["tree"].is_object() {
        bail!("Project document has no tree: {name}")
    }
    if !doc["gameId"].is_null() && doc["gameId"] != json!(universe) {
        bail!("{name} restricts syncing to a different universe")
    }
    let current = &doc["placeIds"];
    if !current.is_null() && *current != json!([]) && *current != json!([place]) {
        bail!("{name} has placeIds that conflict with the verified place map")
    }
    if *current != json!([place]) {
        doc["placeIds"] = json!([place]);
        atomic_json(project, &doc, true)?
    }
    Ok(())
}
#[derive(Clone)]
struct Studio {
    id: String,
    name: String,
    place: u64,
    universe: u64,
    places: BTreeMap<u64, String>,
}
#[derive(Debug)]
struct McpError(String);
impl std::fmt::Display for McpError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for McpError {}
fn mcp<T>(r: Result<T>) -> Result<T> {
    r.map_err(|e| McpError(e.to_string()).into())
}
type Cache = HashMap<u64, (Instant, BTreeMap<u64, String>)>;
fn discover(rpc: &mut StudioRpc, cache: &mut Cache) -> Result<Vec<Studio>> {
    let list = mcp(rpc.list_studios())?;
    if list.is_empty() {
        return Err(McpError(
            "no-studio: Open a Roblox Studio place with Studio MCP enabled, then retry.".into(),
        )
        .into());
    }
    let mut result = Vec::new();
    let mut universes = BTreeMap::new();
    for s in list {
        if !s["mode"].is_null() && s["mode"] != "Edit" {
            return Err(McpError(
                "studio-not-edit: Switch the open Studio place to Edit mode, then retry.".into(),
            )
            .into());
        }
        let id = s["id"]
            .as_str()
            .ok_or_else(|| McpError("Studio has no identity".into()))?
            .to_owned();
        let identity = mcp(rpc.read_place_identity(&id))?;
        let place = identity["place_id"].as_u64().unwrap_or(0);
        let universe = identity["universe_id"].as_u64().unwrap_or(0);
        if place == 0 || universe == 0 {
            return Err(McpError(
                "unpublished-place: Publish the open place in Roblox Studio, then retry.".into(),
            )
            .into());
        }
        if !universes.contains_key(&universe) {
            let places = if let Some((at, p)) = cache
                .get(&universe)
                .filter(|(at, _)| at.elapsed() < Duration::from_secs(60))
            {
                let _ = at;
                p.clone()
            } else {
                let response = mcp(rpc.call(
                    "execute_luau",
                    json!({"code":UNIVERSE_LUAU,"datamodel_type":"Edit"}),
                    Some(&id),
                ))?;
                let p = mcp(parse_universe(&response))?;
                cache.insert(universe, (Instant::now(), p.clone()));
                p
            };
            universes.insert(universe, places);
        }
        let places = universes[&universe].clone();
        if !places.contains_key(&place) {
            return Err(McpError(
                "place-outside-universe: Reopen the published place in Roblox Studio, then retry."
                    .into(),
            )
            .into());
        }
        let raw = s["name"].as_str().unwrap_or("");
        let re = regex::Regex::new(r"\s*\(placeId:.*\)$").unwrap();
        let trimmed = re.replace(raw, "");
        let name = if trimmed.trim().is_empty() {
            identity["name"]
                .as_str()
                .filter(|s| !s.is_empty())
                .unwrap_or("unknown")
                .to_owned()
        } else {
            trimmed.trim().to_owned()
        };
        result.push(Studio {
            id,
            name,
            place,
            universe,
            places,
        });
    }
    Ok(result)
}
fn map_place(root: &Path, name: &str, place: i64) -> Result<Value> {
    let target = project_path(root, name)?;
    if place <= 0 {
        bail!("PlaceId must be a positive integer")
    }
    let mut rpc = mcp(StudioRpc::new(None, 12))?;
    let studios = discover(&mut rpc, &mut Cache::new())?;
    let matches: Vec<_> = studios
        .iter()
        .filter(|s| s.places.contains_key(&(place as u64)))
        .collect();
    if matches.len() != 1 {
        bail!("PlaceId {place} was not found in exactly one verified open universe")
    }
    let mut map = read_places_block(&root.join("AGENTS.md"))?;
    if let Some((owner, _)) = map
        .iter()
        .find(|(n, p)| **p == place as u64 && n.as_str() != name)
    {
        bail!("PlaceId {place} is already assigned to {owner}")
    }
    map.insert(name.to_owned(), place as u64);
    write_places_block(&root.join("AGENTS.md"), &map)?;
    Ok(
        json!({"project":target.display().to_string(),"name":name,"placeId":place,"universeId":matches[0].universe,"state":"mapped; automatic sync will retry"}),
    )
}
#[cfg(unix)]
fn signal(pid: i32, sig: i32) -> std::io::Result<()> {
    if unsafe { libc::kill(pid, sig) } == 0 {
        Ok(())
    } else {
        Err(std::io::Error::last_os_error())
    }
}
#[cfg(not(unix))]
fn signal(_pid: i32, _sig: i32) -> std::io::Result<()> {
    Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "signals unsupported",
    ))
}
fn alive(pid: i32) -> bool {
    signal(pid, 0).is_ok()
}
fn read_json(path: &Path) -> Option<Value> {
    serde_json::from_slice(&fs::read(path).ok()?).ok()
}
fn status() -> Value {
    let dir = state_dir();
    let mut v = read_json(&dir.join("status.json"))
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({"projects":{}}));
    let pid = read_json(&dir.join("supervisor.json")).and_then(|v| v["pid"].as_i64());
    let running = pid.is_some_and(|p| alive(p as i32));
    v["running"] = json!(running);
    if !running {
        v["supervisorPid"] = Value::Null
    }
    v
}
fn launch(root: &Path) -> Result<u32> {
    if let Some(pid) = read_json(&state_dir().join("supervisor.json"))
        .and_then(|v| v["pid"].as_i64())
        .filter(|p| alive(*p as i32))
    {
        return Ok(pid as u32);
    }
    let mut cmd = Command::new(std::env::current_exe()?);
    cmd.arg("--root")
        .arg(root)
        .args(["argon", "_supervisor"])
        .current_dir(root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0);
    }
    Ok(cmd.spawn()?.id())
}
fn ensure(root: &Path, project: Option<String>, port: Option<i64>) -> Result<Value> {
    register(root)?;
    let port = if let Some(p) = port {
        let project = project.ok_or_else(|| anyhow!("--port requires --project NAME"))?;
        Some(reserve(&project_path(root, &project)?, Some(p))?)
    } else {
        None
    };
    let pid = if std::env::var_os("RBLX_HARNESS_TESTING").is_some_and(|s| !s.is_empty()) {
        None
    } else {
        Some(launch(root)?)
    };
    Ok(
        json!({"root":root.display().to_string(),"registered":true,"port":port,"supervisorPid":pid,"state":if pid.is_some(){"starting"}else{"registered"}}),
    )
}
fn stop() -> Result<Value> {
    let v = status();
    let pid = v["supervisorPid"].as_i64();
    if let Some(p) = pid.filter(|p| alive(*p as i32)) {
        signal(p as i32, libc::SIGTERM).map_err(|e| anyhow!("Cannot stop Argon supervisor: {e}"))?
    }
    Ok(json!({"stopping":pid.is_some_and(|p|alive(p as i32)),"supervisorPid":pid}))
}
fn session(project: &Path) -> u64 {
    let digest = Sha256::digest(project.to_string_lossy().as_bytes());
    u64::from_be_bytes(digest[..8].try_into().unwrap()) % 9_000_000_000 + 1
}
fn argon() -> Result<Command> {
    let path = crate::gates::bundled_tool("argon");
    if !path.is_file() {
        bail!("Argon CLI is not installed or is absent from PATH")
    }
    Ok(Command::new(path))
}
fn flags(cmd: &mut Command) {
    cmd.args(["--yes", "--color", "never"]);
}
struct Server {
    child: Child,
    log: PathBuf,
    port: u16,
    session: u64,
    studio_id: String,
    place: u64,
    universe: u64,
}
fn start(project: &Path, port: u16, studio: &Studio) -> Result<Server> {
    let sid = session(project);
    let log = state_dir().join("logs").join(format!("{sid}.log"));
    fs::create_dir_all(log.parent().unwrap())?;
    let file = File::create(&log)?;
    let mut cmd = argon()?;
    cmd.arg("serve").arg(project).arg(sid.to_string()).args([
        "--host",
        "localhost",
        "--port",
        &port.to_string(),
        "--sourcemap",
    ]);
    flags(&mut cmd);
    cmd.current_dir(project.parent().unwrap())
        .stdin(Stdio::null())
        .stdout(Stdio::from(file.try_clone()?))
        .stderr(Stdio::from(file));
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0);
    }
    Ok(Server {
        child: cmd.spawn()?,
        log,
        port,
        session: sid,
        studio_id: studio.id.clone(),
        place: studio.place,
        universe: studio.universe,
    })
}
fn stop_server(s: &mut Server) {
    if s.child.try_wait().ok().flatten().is_some() {
        return;
    }
    let _ = signal(-(s.child.id() as i32), libc::SIGINT);
    let deadline = Instant::now() + Duration::from_secs(3);
    while Instant::now() < deadline {
        if s.child.try_wait().ok().flatten().is_some() {
            return;
        }
        std::thread::sleep(Duration::from_millis(50))
    }
    let _ = signal(-(s.child.id() as i32), libc::SIGTERM);
    let deadline = Instant::now() + Duration::from_secs(2);
    while Instant::now() < deadline {
        if s.child.try_wait().ok().flatten().is_some() {
            return;
        }
        std::thread::sleep(Duration::from_millis(50))
    }
}
fn tail(path: &Path, n: u64) -> String {
    let Ok(mut f) = File::open(path) else {
        return String::new();
    };
    let len = f.metadata().map(|m| m.len()).unwrap_or(0);
    let _ = f.seek(SeekFrom::Start(len.saturating_sub(n)));
    let mut v = Vec::new();
    let _ = f.read_to_end(&mut v);
    String::from_utf8_lossy(&v).into_owned()
}
fn connected(s: &Server) -> bool {
    let re = regex::Regex::new(
        r"(?i)(?:plugin|client).{0,40}connected|connected.{0,40}(?:plugin|client)",
    )
    .unwrap();
    if re.is_match(&tail(&s.log, 65536)) {
        return true;
    }
    Command::new("lsof")
        .args([
            "-nP",
            "-a",
            "-p",
            &s.child.id().to_string(),
            &format!("-iTCP:{}", s.port),
            "-sTCP:ESTABLISHED",
        ])
        .stderr(Stdio::null())
        .output()
        .map(|o| {
            o.stdout
                .split(|b| *b == b'\n')
                .filter(|l| !l.is_empty())
                .count()
                > 1
        })
        .unwrap_or(false)
}
fn cli_update() -> (bool, String) {
    let result = (|| -> Result<(bool, String)> {
        let mut cmd = argon()?;
        cmd.args(["update", "cli"]);
        flags(&mut cmd);
        let tmp = tempfile::tempfile()?;
        let mut child = cmd
            .stdin(Stdio::null())
            .stdout(Stdio::from(tmp.try_clone()?))
            .stderr(Stdio::from(tmp.try_clone()?))
            .spawn()?;
        let deadline = Instant::now() + Duration::from_secs(90);
        let status = loop {
            if let Some(s) = child.try_wait()? {
                break s;
            }
            if Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                bail!("Argon CLI update timed out")
            }
            std::thread::sleep(Duration::from_millis(100));
        };
        let mut tmp = tmp;
        tmp.seek(SeekFrom::Start(0))?;
        let mut data = String::new();
        tmp.read_to_string(&mut data)?;
        let text = data.trim();
        let text = text
            .chars()
            .rev()
            .take(1000)
            .collect::<String>()
            .chars()
            .rev()
            .collect();
        Ok((status.success(), text))
    })();
    result.unwrap_or_else(|e| (false, e.to_string()))
}
fn desired(
    studios: &[Studio],
    candidates: &[Mapping],
) -> (
    BTreeMap<PathBuf, (Studio, Mapping)>,
    BTreeMap<String, Value>,
) {
    let mut grouped: BTreeMap<PathBuf, Vec<(Studio, Mapping)>> = BTreeMap::new();
    let mut issues = BTreeMap::new();
    for s in studios {
        let matches: BTreeMap<_, _> = candidates
            .iter()
            .filter(|m| m.place == s.place && s.places.contains_key(&s.place))
            .map(|m| (m.project.clone(), m.clone()))
            .collect();
        if matches.is_empty() {
            issues.insert(s.id.clone(),json!({"state":"unmatched","message":format!("No project matches the place id for the open place '{}'.",s.name),"placeId":s.place}));
        } else if matches.len() != 1 {
            issues.insert(s.id.clone(),json!({"state":"ambiguous","message":format!("More than one Argon project maps to the open place '{}'.",s.name),"placeId":s.place}));
        } else {
            let (p, m) = matches.into_iter().next().unwrap();
            grouped.entry(p).or_default().push((s.clone(), m));
        }
    }
    let mut out = BTreeMap::new();
    for (p, mut entries) in grouped {
        if entries.len() != 1 {
            for (s, _) in entries {
                issues.insert(s.id,json!({"state":"ambiguous","message":"More than one Studio has this Argon project open."}));
            }
        } else {
            out.insert(p, entries.pop().unwrap());
        }
    }
    (out, issues)
}
fn supervisor() -> Result<i32> {
    let folder = state_dir();
    fs::create_dir_all(&folder)?;
    let lock = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .open(folder.join("supervisor.lock"))?;
    if lock.try_lock_exclusive().is_err() {
        return Ok(0);
    }
    atomic_json(
        &folder.join("supervisor.json"),
        &json!({"pid":std::process::id(),"startedAt":now()}),
        false,
    )?;
    STOP.store(false, Ordering::SeqCst);
    #[cfg(unix)]
    unsafe {
        libc::signal(libc::SIGINT, stop_signal as *const () as libc::sighandler_t);
        libc::signal(
            libc::SIGTERM,
            stop_signal as *const () as libc::sighandler_t,
        );
    }
    #[cfg(not(unix))]
    ctrlc::set_handler(|| STOP.store(true, Ordering::SeqCst))?;
    let stop = &STOP;
    let mut servers: BTreeMap<PathBuf, Server> = BTreeMap::new();
    let mut cache = Cache::new();
    let mut retry: HashMap<PathBuf, f64> = HashMap::new();
    let mut last_update = 0.0;
    let mut update_error = None::<String>;
    let result = (|| -> Result<()> {
        while !stop.load(Ordering::SeqCst) {
            let time = now();
            if time - last_update >= 86400.0 {
                let (ok, detail) = cli_update();
                last_update = if ok { time } else { time - 86400.0 + 3600.0 };
                update_error = if ok {
                    None
                } else {
                    Some(if detail.is_empty() {
                        "CLI update failed".into()
                    } else {
                        detail
                    })
                };
            }
            let state = read_registry()?;
            let mut report = json!({"supervisorPid":std::process::id(),"updatedAt":time,"projects":{},"studios":[]});
            if let Some(e) = &update_error {
                report["cliUpdate"] = json!(e)
            }
            let operation = (|| -> Result<()> {
                let mut rpc = mcp(StudioRpc::new(None, 8))?;
                let studios = discover(&mut rpc, &mut cache)?;
                report["studios"]=json!(studios.iter().map(|s|json!({"id":s.id,"name":s.name,"placeId":s.place,"universeId":s.universe})).collect::<Vec<_>>());
                let mut candidates = Vec::new();
                for root in state["roots"].as_array().unwrap() {
                    let p = PathBuf::from(root.as_str().unwrap());
                    if p.is_dir() {
                        if let Ok(items) = project_maps(&p.canonicalize()?) {
                            candidates.extend(items)
                        }
                    }
                }
                let (desired, issues) = desired(&studios, &candidates);
                servers.retain(|p, s| {
                    let keep = desired.get(p).is_some_and(|(studio, _)| {
                        studio.id == s.studio_id
                            && studio.place == s.place
                            && studio.universe == s.universe
                    }) && s.child.try_wait().ok().flatten().is_none();
                    if !keep {
                        stop_server(s)
                    }
                    keep
                });
                for (id, issue) in issues {
                    report["projects"][format!("studio:{id}")] = issue;
                }
                for (path, (studio, mapping)) in desired {
                    let key = path.to_string_lossy().to_string();
                    if let Some(s) = servers.get(&path) {
                        report["projects"][&key] = json!({"state":if connected(s){"connected"}else{"listening"},"name":mapping.name,"placeId":studio.place,"port":s.port,"session":s.session,"processId":s.child.id()});
                        continue;
                    }
                    if time < *retry.get(&path).unwrap_or(&0.0) {
                        report["projects"][&key] = json!({"state":"blocked","message":"Argon server restart is delayed after failure."});
                        continue;
                    }
                    let attempt = (|| -> Result<Server> {
                        update_identity(&path, studio.place, studio.universe)?;
                        let port = reserve(&path, None)?;
                        if !port_available(port) {
                            bail!("Assigned port {port} is occupied; it remains reserved for this project.")
                        }
                        let mut s = start(&path, port, &studio)?;
                        std::thread::sleep(Duration::from_millis(200));
                        if s.child.try_wait()?.is_some() {
                            bail!("Argon exited during startup: {}", tail(&s.log, 1000).trim())
                        }
                        Ok(s)
                    })();
                    match attempt {
                        Ok(s) => {
                            report["projects"][&key] = json!({"state":if connected(&s){"connected"}else{"starting"},"name":mapping.name,"placeId":studio.place,"port":s.port,"session":s.session,"processId":s.child.id()});
                            servers.insert(path, s);
                        }
                        Err(e) => {
                            report["projects"][&key] = json!({"state":"blocked","name":mapping.name,"placeId":studio.place,"message":e.to_string()});
                            retry.insert(path, time + 15.0);
                        }
                    }
                }
                Ok(())
            })();
            if let Err(e) = operation {
                for s in servers.values_mut() {
                    stop_server(s)
                }
                servers.clear();
                report["mcp"] = json!({"state":"unavailable","message":e.to_string()});
            }
            atomic_json(&folder.join("status.json"), &report, false)?;
            for _ in 0..30 {
                if stop.load(Ordering::SeqCst) {
                    break;
                }
                std::thread::sleep(Duration::from_millis(100))
            }
        }
        Ok(())
    })();
    for s in servers.values_mut() {
        stop_server(s)
    }
    let _ = atomic_json(
        &folder.join("status.json"),
        &json!({"supervisorPid":null,"updatedAt":now(),"projects":{}}),
        false,
    );
    let _ = fs::remove_file(folder.join("supervisor.json"));
    result?;
    Ok(0)
}
pub fn run(args: &[OsString]) -> Result<i32> {
    let parsed = match Args::try_parse_from(
        std::iter::once(OsString::from("argon")).chain(args.iter().cloned()),
    ) {
        Ok(v) => v,
        Err(e) => {
            let code = e.exit_code();
            e.print()?;
            return Ok(code);
        }
    };
    let root = std::env::current_dir()?.canonicalize()?;
    if matches!(parsed.action, Action::Supervisor) {
        return supervisor();
    }
    let result = match parsed.action {
        Action::Ensure { project, port } => ensure(&root, project, port),
        Action::Status => Ok(status()),
        Action::Stop => stop(),
        Action::Map { name, place_id } => map_place(&root, &name, place_id),
        Action::Supervisor => unreachable!(),
    };
    match result {
        Ok(v) => {
            println!("{}", serde_json::to_string(&v)?);
            Ok(0)
        }
        Err(e) => {
            eprintln!("argon|blocked|{e}");
            Ok(if e.downcast_ref::<McpError>().is_some() {
                3
            } else {
                2
            })
        }
    }
}
