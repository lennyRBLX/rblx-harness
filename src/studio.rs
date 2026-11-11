use anyhow::{anyhow, bail, Result};
use clap::Parser;
use std::{
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
};

#[derive(Parser)]
struct Generate {
    action: String,
    #[arg(long)]
    side: String,
    #[arg(long, conflicts_with = "path_file")]
    path: Option<String>,
    #[arg(long)]
    path_file: Option<PathBuf>,
    #[arg(long)]
    source: Option<PathBuf>,
    #[arg(long)]
    expected: Option<PathBuf>,
    #[arg(long)]
    expected_editor: Option<PathBuf>,
    #[arg(long)]
    output: PathBuf,
    #[arg(long)]
    session: Option<String>,
    #[arg(long)]
    revision: Option<i64>,
    #[arg(long)]
    audited: bool,
}
fn literal(s: &str) -> String {
    let mut out = String::from("\"");
    for b in s.bytes() {
        if b < 32 || b > 126 || b == b'"' || b == b'\\' {
            out.push_str(&format!("\\{b:03}"));
        } else {
            out.push(b as char);
        }
    }
    out.push('"');
    out
}
fn side_guard(side: &str) -> Result<String> {
    let mut out = "local RunService = game:GetService(\"RunService\")\nassert(RunService:IsStudio(), \"Studio only\")\n".to_string();
    match side {
        "Edit" => out.push_str("assert(not RunService:IsRunning(), \"Select stopped Edit\")\n"),
        "Server" | "Client" => out.push_str(&format!(
            "assert(RunService:IsRunning() and RunService:Is{side}(), \"Select running {side}\")\n"
        )),
        _ => bail!("Select Edit, Server or Client"),
    };
    Ok(out)
}
fn target_code(path: Option<&str>) -> Result<String> {
    let items: Vec<String> = serde_json::from_str(
        path.ok_or_else(|| anyhow!("--path must be a JSON array of nonempty instance names"))?,
    )
    .map_err(|_| anyhow!("--path must be a JSON array of nonempty instance names"))?;
    if items.is_empty() || items.iter().any(|s| s.is_empty()) {
        bail!("--path must be a JSON array of nonempty instance names");
    }
    Ok(format!("local Target = game\nfor _, Segment in {{{}}} do\n    local Match\n    for _, Child in Target:GetChildren() do\n        if Child.Name == Segment then\n            assert(not Match, \"Ambiguous path segment: \" .. Segment)\n            Match = Child\n        end\n    end\n    assert(Match, \"Missing path segment: \" .. Segment)\n    Target = Match\nend\n", items.iter().map(|s|literal(s)).collect::<Vec<_>>().join(", ")))
}
fn content(p: Option<&PathBuf>) -> Result<String> {
    Ok(fs::read_to_string(
        p.ok_or_else(|| anyhow!("missing source file"))?,
    )?)
}
fn check(expected: Option<&PathBuf>) -> Result<String> {
    Ok(format!("local Editor = game:GetService(\"ScriptEditorService\")\nlocal Expected = {}\nassert(Target.Source == Expected, \"Stored source changed; inspect before retrying\")\n", literal(&content(expected)?)))
}
fn asset(s: &str) -> String {
    if s.contains('\r') {
        return literal(s);
    }
    let mut eq = "=".to_string();
    while s.contains(&format!("]{eq}]")) {
        eq.push('=')
    }
    format!("[{eq}[\n{s}]{eq}]")
}
fn generate(a: Generate, reload: bool) -> Result<i32> {
    let path_text = match &a.path_file {
        Some(p) => Some(fs::read_to_string(p)?),
        None => a.path.clone(),
    };
    let mut out = side_guard(&a.side)?;
    if !reload {
        if !["snapshot", "persist"].contains(&a.action.as_str()) {
            bail!("Unknown source action")
        }
        if a.action == "persist"
            && (a.side != "Edit"
                || a.source.is_none()
                || a.expected.is_none()
                || a.expected_editor.is_none())
        {
            bail!("persist requires stopped Edit, --source, --expected and --expected-editor")
        }
        out.push_str(&target_code(path_text.as_deref())?);
        out.push_str(
            "assert(Target:IsA(\"LuaSourceContainer\"), \"Target must contain source\")\n",
        );
        if a.action == "snapshot" {
            out.push_str("local Editor = game:GetService(\"ScriptEditorService\")\nreturn {Path = Target:GetFullName(), Stored = Target.Source, Editor = Editor:GetEditorSource(Target)}\n");
        } else {
            out.push_str(&check(a.expected.as_ref())?);
            out.push_str(&format!("local ExpectedEditor = {}\nlocal NewSource = {}\nassert(Editor:GetEditorSource(Target) == ExpectedEditor, \"Editor draft changed; inspect before retrying\")\nEditor:UpdateSourceAsync(Target, function(Current)\n    if Current ~= ExpectedEditor or Target.Source ~= Expected then\n        return nil\n    end\n    return NewSource\nend)\nassert(Editor:GetEditorSource(Target) == NewSource, \"Editor update was not applied\")\nassert(Target.Source == Expected or Target.Source == NewSource, \"Stored source changed during edit\")\nif Target.Source ~= NewSource then\n    Target.Source = NewSource\nend\nassert(Target.Source == NewSource and Editor:GetEditorSource(Target) == NewSource, \"Source verification failed\")\nreturn {{Path = Target:GetFullName(), StoredMatches = true, EditorMatches = true}}\n",literal(&content(a.expected_editor.as_ref())?),literal(&content(a.source.as_ref())?)));
        }
    } else {
        let session = a.session.as_deref().unwrap_or("");
        if session.is_empty()
            || session.len() > 48
            || !session
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
        {
            bail!("--session must be 1-48 ASCII letters, digits, underscores or hyphens")
        }
        if a.side != "Server" && a.side != "Client" {
            bail!("Reload requires Server or Client")
        }
        let parent = if a.side == "Server" {
            "game:GetService(\"ServerScriptService\")"
        } else {
            "game:GetService(\"Players\").LocalPlayer:WaitForChild(\"PlayerScripts\", 5)"
        };
        let name = literal(&format!("__HarnessHotReload_{session}"));
        out.push_str(&format!("local Parent = {parent}\nassert(Parent, \"Runtime container missing\")\nlocal Session = {}\nlocal Root = Parent:FindFirstChild({name})\n",literal(session)));
        if a.action == "bootstrap" {
            let core = asset(include_str!("../tools/hot_reload/PatchCore.luau"));
            let bridge = asset(include_str!("../tools/hot_reload/Bridge.server.luau"));
            let class = literal(if a.side == "Server" {
                "Script"
            } else {
                "LocalScript"
            });
            out.push_str(&format!("if Root then\n    assert(Root:GetAttribute(\"Session\") == Session, \"Name collision\")\n    return Root:GetAttributes()\nend\nRoot = Instance.new(\"Folder\")\nRoot.Name = {name}\nRoot:SetAttribute(\"Session\", Session)\nRoot:SetAttribute(\"Status\", \"Booting\")\nlocal Core = Instance.new(\"ModuleScript\")\nCore.Name = \"PatchCore\"\nCore.Source = {core}\nCore.Parent = Root\nlocal Command = Instance.new(\"BindableFunction\")\nCommand.Name = \"Command\"\nCommand.Parent = Root\nlocal Runner = Instance.new({class})\nRunner.Name = \"Runner\"\nRunner.Source = {bridge}\nRunner.Parent = Root\nRoot.Parent = Parent\nreturn Root:GetAttributes()\n"));
        } else {
            out.push_str("assert(Root and Root:GetAttribute(\"Session\") == Session, \"Bootstrap this side first\")\n");
            if a.action == "poll" {
                out.push_str("return Root:GetAttributes()\n");
            } else {
                out.push_str("assert(Root:GetAttribute(\"Status\") ~= \"Booting\", \"Bridge is not ready\")\n");
                out.push_str(&target_code(path_text.as_deref())?);
                out.push_str(
                    "assert(Target:IsA(\"ModuleScript\"), \"Target must be a ModuleScript\")\n",
                );
                if a.action == "status" {
                    out.push_str("return Root.Command:Invoke({Action = \"Status\", Target = Target, Session = Session})\n");
                } else {
                    if a.action != "patch" && a.action != "undo" {
                        bail!("Unknown reload action")
                    }
                    let revision = a.revision.filter(|r| *r >= 0).ok_or_else(|| {
                        anyhow!("--revision must be the current nonnegative target revision")
                    })?;
                    let id = uuid::Uuid::new_v4().simple().to_string();
                    let action = if a.action == "patch" { "Patch" } else { "Undo" };
                    out.push_str(&format!("local Request = {{\n    Action = {}, Session = Session, Target = Target,\n    ExpectedRevision = {revision}, RequestId = {},\n}}\n",literal(action),literal(&id)));
                    if a.action == "undo" {
                        out.push_str("return Root.Command:Invoke(Request)\n");
                    } else {
                        if a.source.is_none() || a.expected.is_none() || !a.audited {
                            bail!("patch requires --source, --expected and --audited after reviewing the module and callers")
                        }
                        out.push_str(&check(a.expected.as_ref())?);
                        out.push_str(&format!("assert(Editor:GetEditorSource(Target) == Expected, \"Editor draft differs; inspect before retrying\")\nassert(Target.Archivable, \"Target is not Archivable\")\nlocal State = Root.Command:Invoke({{Action = \"Status\", Target = Target, Session = Session}})\nassert(State.Revision == Request.ExpectedRevision, \"Stale revision\")\nassert(State.Status ~= \"Pending\" and State.Status ~= \"TimedOut\", \"Bridge unavailable\")\nassert(State.RetainedCandidates < State.CandidateLimit, \"Candidate limit reached\")\nlocal Candidate = Target:Clone()\nfor _, Descendant in Candidate:GetDescendants() do\n    if Descendant:IsA(\"BaseScript\") then\n        Candidate:Destroy()\n        error(\"Executable descendants require a project adapter\")\n    end\nend\nCandidate.Name = {}\nCandidate:SetAttribute(\"HarnessHotReloadSession\", Session)\nCandidate.Source = {}\nCandidate.Parent = Target.Parent\nRequest.Candidate = Candidate\nlocal Success, Result = pcall(function() return Root.Command:Invoke(Request) end)\nif not Success then\n    Candidate:Destroy()\n    error(Result)\nend\nreturn {{RequestId = Request.RequestId, Candidate = Candidate:GetFullName(), Accepted = Result.Accepted}}\n",literal(&format!("__HotCandidate_{id}")),literal(&content(a.source.as_ref())?)));
                    }
                }
            }
        }
    }
    let output_abs = absolute(&a.output)?;
    for p in [&a.source, &a.expected, &a.expected_editor, &a.path_file]
        .into_iter()
        .flatten()
    {
        if absolute(p)? == output_abs {
            bail!("--output must not overwrite an input source or snapshot")
        }
    }
    fs::write(&a.output, out)?;
    println!(
        "Generated {} for {}: {}",
        a.action,
        a.side,
        a.output.display()
    );
    Ok(0)
}
fn absolute(p: &Path) -> Result<PathBuf> {
    if p.exists() {
        Ok(fs::canonicalize(p)?)
    } else {
        let parent = p
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        Ok(fs::canonicalize(parent)?.join(p.file_name().ok_or_else(|| anyhow!("invalid path"))?))
    }
}
pub fn run(args: &[OsString]) -> Result<i32> {
    let (cmd, rest) = args
        .split_first()
        .ok_or_else(|| anyhow!("missing studio command"))?;
    match cmd.to_str().unwrap_or("") {
        "source" | "reload" => {
            let mut argv = vec![OsString::from("studio")];
            argv.extend_from_slice(rest);
            match Generate::try_parse_from(argv) {
                Ok(a) => generate(a, cmd == "reload"),
                Err(e) => {
                    e.print()?;
                    Ok(2)
                }
            }
        }
        "clean" => clean(rest),
        "map" => map(rest),
        "census" => census(rest),
        "boot" => boot(rest),
        "output" => output(rest),
        _ => bail!("unknown studio command: {}", cmd.to_string_lossy()),
    }
}

use regex::Regex;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{BufRead, BufReader, Write},
    process::{Child, Command, Stdio},
    sync::mpsc,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const MCP_REMEDY: &str = "Restart Roblox Studio, open the project place, enable MCP, then retry.";
fn studio_mcp_path() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("ROBLOX_STUDIO_MCP")
        .map(PathBuf::from)
        .filter(|p| p.is_file())
    {
        return Some(path);
    }
    #[cfg(target_os = "windows")]
    {
        let versions = PathBuf::from(std::env::var_os("LOCALAPPDATA")?).join("Roblox/Versions");
        fs::read_dir(versions)
            .ok()?
            .filter_map(|entry| entry.ok())
            .filter_map(|entry| {
                let path = entry.path().join("StudioMCP.exe");
                if !path.is_file() {
                    return None;
                }
                Some((fs::metadata(&path).ok()?.modified().ok()?, path))
            })
            .max_by(|a, b| a.0.cmp(&b.0))
            .map(|(_, path)| path)
    }
    #[cfg(not(target_os = "windows"))]
    {
        Some(PathBuf::from(
            "/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP",
        ))
    }
}
pub struct StudioRpc {
    child: Child,
    lines: mpsc::Receiver<String>,
    id: u64,
    timeout: Duration,
    active: Option<String>,
}
impl StudioRpc {
    pub fn new(cmd: Option<&str>, timeout: u64) -> Result<Self> {
        let default = studio_mcp_path()
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_default();
        let cmd = cmd.unwrap_or(&default);
        let argv = if Path::new(cmd).exists() {
            vec![cmd.to_string()]
        } else {
            shell_words::split(cmd)?
        };
        if argv.is_empty() || !Path::new(&argv[0]).exists() {
            bail!("studiomcp-absent: Install or repair Roblox Studio, then retry.")
        }
        let mut child = Command::new(&argv[0])
            .args(&argv[1..])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|_| {
                anyhow!("studiomcp-spawn-failed: Install or repair Roblox Studio, then retry.")
            })?;
        let stdout = child.stdout.take().unwrap();
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                match line {
                    Ok(line) => {
                        if tx.send(line).is_err() {
                            break;
                        }
                    }
                    Err(_) => break,
                }
            }
        });
        let mut rpc = Self {
            child,
            lines: rx,
            id: 0,
            timeout: Duration::from_secs(timeout),
            active: None,
        };
        rpc.request("initialize",json!({"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"harness","version":"1.0"}}))?;
        rpc.send(json!({"jsonrpc":"2.0","method":"notifications/initialized"}))?;
        Ok(rpc)
    }
    fn send(&mut self, msg: Value) -> Result<()> {
        let stdin = self
            .child
            .stdin
            .as_mut()
            .ok_or_else(|| anyhow!("studiomcp-unreachable: {MCP_REMEDY}"))?;
        writeln!(stdin, "{msg}")
            .and_then(|_| stdin.flush())
            .map_err(|_| anyhow!("studiomcp-unreachable: {MCP_REMEDY}"))
    }
    fn request(&mut self, method: &str, params: Value) -> Result<Value> {
        self.id += 1;
        let id = self.id;
        self.send(json!({"jsonrpc":"2.0","id":id,"method":method,"params":params}))?;
        let deadline = Instant::now() + self.timeout;
        loop {
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                bail!("studiomcp-timeout: {MCP_REMEDY}")
            }
            let line = match self.lines.recv_timeout(remaining) {
                Ok(l) => l,
                Err(mpsc::RecvTimeoutError::Timeout) => bail!("studiomcp-timeout: {MCP_REMEDY}"),
                Err(_) => bail!("studiomcp-unreachable: {MCP_REMEDY}"),
            };
            if let Ok(v) = serde_json::from_str::<Value>(&line) {
                if v["id"].as_u64() == Some(id) {
                    if !v["error"].is_null() {
                        bail!(
                            "studiomcp-error: {}",
                            v["error"]["message"].as_str().unwrap_or("unknown error")
                        )
                    }
                    return Ok(v["result"].clone());
                }
            }
        }
    }
    pub fn call(
        &mut self,
        name: &str,
        mut arguments: Value,
        studio_id: Option<&str>,
    ) -> Result<String> {
        let selected = studio_id.or(self.active.as_deref());
        if name != "list_roblox_studios" {
            if let Some(id) = selected {
                arguments["studio_id"] = json!(id)
            }
        }
        let result = self.request("tools/call", json!({"name":name,"arguments":arguments}))?;
        let text = result["content"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter(|v| v["type"] == "text")
                    .filter_map(|v| v["text"].as_str())
                    .collect::<Vec<_>>()
                    .join("\n")
            })
            .unwrap_or_default();
        if result["isError"].as_bool().unwrap_or(false) {
            bail!(
                "studiomcp-tool-error: {}",
                if text.is_empty() { name } else { &text }
            )
        }
        Ok(text)
    }
    pub fn list_studios(&mut self) -> Result<Vec<Value>> {
        let raw = self.call("list_roblox_studios", json!({}), None)?;
        let mut result = Vec::new();
        if let Ok(v) = serde_json::from_str::<Value>(&raw) {
            let data = if v.is_array() { &v } else { &v["studios"] };
            if let Some(a) = data.as_array() {
                for s in a {
                    let id = s["id"]
                        .as_str()
                        .map(str::to_string)
                        .unwrap_or_else(|| s["id"].to_string());
                    result.push(json!({"id":id,"name":s["name"],"active":s["active"].as_bool().unwrap_or(false),"mode":s["mode"],"place_id":s["placeId"],"universe_id":s["universeId"]}));
                }
            }
        }
        if result.is_empty() {
            let re = Regex::new(r"(\d{6,})\s+(\S[^\n]*)").unwrap();
            for c in re.captures_iter(&raw) {
                result.push(json!({"id":&c[1],"name":c[2].trim(),"active":false}));
            }
        }
        Ok(result)
    }
    pub fn read_place_identity(&mut self, id: &str) -> Result<Value> {
        let code="local h = game:GetService(\"HttpService\") return h:JSONEncode({place_id = game.PlaceId, universe_id = game.GameId, name = game.Name})";
        let raw = self.call(
            "execute_luau",
            json!({"code":code,"datamodel_type":"Edit"}),
            Some(id),
        )?;
        let v: Value = serde_json::from_str(raw.trim()).map_err(|_| {
            anyhow!("no-place: Open the project place in Roblox Studio, then retry.")
        })?;
        if v["place_id"].as_u64().is_none()
            || v["universe_id"].as_u64().is_none()
            || v["name"].as_str().is_none()
        {
            bail!("no-place: Open the project place in Roblox Studio, then retry.")
        }
        Ok(v)
    }
    fn select(&mut self, wanted: &BTreeSet<u64>) -> Result<(String, u64)> {
        let deadline = Instant::now() + self.timeout.min(Duration::from_secs(5));
        let studios = loop {
            let s = self.list_studios()?;
            if !s.is_empty() {
                break s;
            }
            if Instant::now() >= deadline {
                bail!("no-studio: Open the project place and enable MCP in Roblox Studio Assistant Settings, then retry.")
            }
            std::thread::sleep(Duration::from_millis(100));
        };
        let mut found = Vec::new();
        let mut seen = Vec::new();
        for s in studios {
            let id = s["id"].as_str().unwrap_or("").to_string();
            if let Ok(raw) = self.call(
                "execute_luau",
                json!({"code":"return game.PlaceId","datamodel_type":"Edit"}),
                Some(&id),
            ) {
                if let Ok(pid) = raw.trim().parse::<u64>() {
                    seen.push(pid);
                    if pid > 0 && (wanted.is_empty() || wanted.contains(&pid)) {
                        found.push((id, pid));
                    }
                }
            }
        }
        if found.len() > 1 {
            bail!("ambiguous-studio: Close other Roblox Studio places, keep the project place open, then retry.")
        }
        if let Some((id, pid)) = found.pop() {
            let confirm = self.call(
                "execute_luau",
                json!({"code":"return game.PlaceId","datamodel_type":"Edit"}),
                Some(&id),
            )?;
            if confirm.trim().parse::<u64>().ok() != Some(pid) {
                bail!("wrong-place: Open the project place in Roblox Studio, then retry.")
            }
            self.active = Some(id.clone());
            return Ok((id, pid));
        }
        if !seen.is_empty() && seen.iter().all(|p| *p == 0) {
            bail!("unpublished-place: Publish the project place in Roblox Studio, then retry.")
        }
        bail!("wrong-place: Open the project place in Roblox Studio, then retry.")
    }
}
impl Drop for StudioRpc {
    fn drop(&mut self) {
        self.child.stdin.take();
        let end = Instant::now() + Duration::from_secs(5);
        while Instant::now() < end {
            if self.child.try_wait().ok().flatten().is_some() {
                return;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub const UNIVERSE_LUAU:&str = "\nlocal AssetService = game:GetService(\"AssetService\")\nlocal pages = AssetService:GetGamePlacesAsync()\nlocal out = {}\nwhile true do\n\tfor _, place in pages:GetCurrentPage() do\n\t\ttable.insert(out, place.PlaceId .. \"|\" .. place.Name)\n\tend\n\tif pages.IsFinished then break end\n\tpages:AdvanceToNextPageAsync()\nend\nreturn \"<<PLACES \" .. #out .. \"\\n\" .. table.concat(out, \"\\n\") .. \"\\nPLACES>>\"\n";
fn records(response: &str, tag: &str, cause: &str) -> Result<Vec<String>> {
    let re = Regex::new(&format!(r"(?s)<<{} (\d+)\n(.*?){}>>", tag, tag)).unwrap();
    let c = re
        .captures(response)
        .ok_or_else(|| anyhow!("{cause}-unparseable: sentinels missing; rerun"))?;
    let rows = c[2]
        .lines()
        .filter(|s| !s.trim().is_empty())
        .map(str::to_string)
        .collect::<Vec<_>>();
    let count = c[1].parse::<usize>()?;
    if rows.len() != count {
        bail!(
            "{cause}-truncated: expected {count} records, got {}",
            rows.len()
        )
    }
    Ok(rows)
}
pub fn parse_universe(response: &str) -> Result<BTreeMap<u64, String>> {
    let mut out = BTreeMap::new();
    for row in records(response, "PLACES", "universe")? {
        let (id, name) = row.split_once('|').unwrap_or((&row, ""));
        out.insert(
            id.parse()
                .map_err(|_| anyhow!("universe-unparseable: {MCP_REMEDY}"))?,
            name.to_string(),
        );
    }
    Ok(out)
}
const BEGIN: &str = "<!-- BEGIN rblx-harness project guidance -->";
const END: &str = "<!-- END rblx-harness project guidance -->";
fn guidance(text: &str) -> Result<(usize, usize)> {
    let b = text.match_indices(BEGIN).collect::<Vec<_>>();
    let e = text.match_indices(END).collect::<Vec<_>>();
    if b.is_empty() && e.is_empty() {
        return Ok((0, text.len()));
    }
    if b.len() != 1 || e.len() != 1 || e[0].0 < b[0].0 {
        bail!("AGENTS.md has malformed harness guidance markers")
    }
    Ok((b[0].0 + BEGIN.len(), e[0].0))
}
fn places_span(text: &str) -> Option<(usize, usize)> {
    let start = Regex::new(r"(?m)^## places\s*\n")
        .unwrap()
        .find(text)?
        .start();
    let after = start + text[start..].find('\n')? + 1;
    let end = Regex::new(r"(?m)^(?:#{1,2} |<!-- END)")
        .unwrap()
        .find(&text[after..])
        .map(|m| after + m.start())
        .unwrap_or(text.len());
    Some((start, end))
}
pub fn read_places_block(path: &Path) -> Result<BTreeMap<String, u64>> {
    let text = match fs::read_to_string(path) {
        Ok(s) => s,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(BTreeMap::new()),
        Err(e) => return Err(e.into()),
    };
    let (b, e) = guidance(&text)?;
    let mut result = BTreeMap::new();
    if let Some((s, t)) = places_span(&text[b..e]) {
        for line in text[b + s..b + t].lines().skip(1) {
            if let Some((name, id)) = line.trim().split_once('|') {
                if let Ok(pid) = id.parse() {
                    result.insert(name.to_string(), pid);
                }
            }
        }
    }
    Ok(result)
}
pub fn write_places_block(path: &Path, mapping: &BTreeMap<String, u64>) -> Result<()> {
    let block = format!(
        "## places\n\n{}\n",
        mapping
            .iter()
            .map(|(n, p)| format!("{n}|{p}"))
            .collect::<Vec<_>>()
            .join("\n")
    );
    let text = match fs::read_to_string(path) {
        Ok(s) => s,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(fs::write(path, block)?),
        Err(e) => return Err(e.into()),
    };
    let (b, e) = guidance(&text)?;
    let section = &text[b..e];
    let updated = if let Some((s, t)) = places_span(section) {
        format!("{}{}{}", &section[..s], block, &section[t..])
    } else {
        format!("{}\n\n{}", section.trim_end_matches('\n'), block)
    };
    fs::write(path, format!("{}{}{}", &text[..b], updated, &text[e..]))?;
    Ok(())
}

const CENSUS_LUAU: &str = r#"
local out = {}
local roots = { workspace }
for _, root in roots do
	for _, model in root:GetChildren() do
		if model:IsA("Model") or model:IsA("Folder") then
			local parts, castShadow, canQuery, canCollide, anchored, massless, canTouch = 0, 0, 0, 0, 0, 0, 0
			for _, d in model:GetDescendants() do
				if d:IsA("BasePart") then
					parts += 1
					if d.CastShadow then castShadow += 1 end
					if d.CanQuery then canQuery += 1 end
					if d.CanCollide then canCollide += 1 end
					if d.Anchored then anchored += 1 end
					if d.Massless then massless += 1 end
					if d.CanTouch then canTouch += 1 end
				end
			end
			if parts > 0 then
				table.insert(out, model:GetFullName() .. "|" .. parts .. "|" .. castShadow .. "|" .. canQuery .. "|" .. canCollide .. "|" .. anchored .. "|" .. massless .. "|" .. canTouch)
			end
		end
	end
end
print("<<CENSUS " .. #out)
print(table.concat(out, "\n"))
print("CENSUS>>")
"#;
const SCAN_LUAU: &str = r#"
local found = {}
for _, service in game:GetChildren() do
	local ok, descendants = pcall(function()
		return service:GetDescendants()
	end)
	if ok then
		for _, inst in descendants do
			if inst.Name == "AnimSaves" then
				table.insert(found, inst:GetFullName())
			end
		end
	end
end
print("<<RIGS " .. #found)
print(table.concat(found, "\n"))
print("RIGS>>")
"#;
const DELETE_LUAU: &str = r#"
local results = {}
for _, service in game:GetChildren() do
	local ok, descendants = pcall(function()
		return service:GetDescendants()
	end)
	if ok then
		for _, inst in descendants do
			if inst.Name == "AnimSaves" then
				local path = inst:GetFullName()
				local deleted = pcall(function()
					inst:Destroy()
				end)
				table.insert(results, path .. "|" .. (deleted and "done" or "fail"))
			end
		end
	end
end
print("<<RIGS " .. #results)
print(table.concat(results, "\n"))
print("RIGS>>")
"#;
fn opts(args: &[OsString], name: &str, default: &str) -> String {
    args.windows(2)
        .find(|w| w[0] == name)
        .map(|w| w[1].to_string_lossy().into_owned())
        .unwrap_or_else(|| default.to_string())
}
fn cache_dir() -> Result<PathBuf> {
    Ok(dirs::home_dir()
        .ok_or_else(|| anyhow!("home directory unavailable"))?
        .join(".cache/harness"))
}
struct PlaceLock(PathBuf, String, fs::File);
impl PlaceLock {
    fn new(pid: u64, session: &str, tool: &str) -> Result<Self> {
        let dir = cache_dir()?;
        fs::create_dir_all(&dir)?;
        let path = dir.join(format!("studio-{pid}.lock"));
        let guard = fs::OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .open(dir.join(format!("studio-{pid}.guard")))?;
        if fs2::FileExt::try_lock_exclusive(&guard).is_err() {
            bail!("studio-busy: another session holds the lock on place {pid} - rerun after it finishes")
        }
        if let Ok(bytes) = fs::read(&path) {
            if let Ok(v) = serde_json::from_slice::<Value>(&bytes) {
                let process = v["pid"].as_i64().unwrap_or(-1);
                let ts = v["timestamp"].as_f64().unwrap_or(0.0);
                let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs_f64();
                let alive = process > 0 && unsafe { libc::kill(process as i32, 0) } == 0;
                if alive && now - ts < 3600.0 {
                    bail!(
                        "studio-busy: {} holds the lock on place {pid} - rerun after it finishes",
                        v["session_id"].as_str().unwrap_or("unknown")
                    )
                }
            }
        }
        let token = uuid::Uuid::new_v4().to_string();
        fs::write(
            &path,
            serde_json::to_vec(
                &json!({"session_id":session,"pid":std::process::id(),"tool":tool,"timestamp":SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs_f64(),"owner":token}),
            )?,
        )?;
        Ok(Self(path, token, guard))
    }
}
impl Drop for PlaceLock {
    fn drop(&mut self) {
        if let Ok(bytes) = fs::read(&self.0) {
            if serde_json::from_slice::<Value>(&bytes)
                .ok()
                .and_then(|v| v["owner"].as_str().map(str::to_string))
                .as_deref()
                == Some(self.1.as_str())
            {
                let _ = fs::remove_file(&self.0);
            }
        }
        let _ = fs2::FileExt::unlock(&self.2);
    }
}
fn env_result(result: Result<i32>) -> Result<i32> {
    match result {
        Ok(n) => Ok(n),
        Err(e) => {
            let s = e.to_string();
            if let Some((cause, remedy)) = s.split_once(": ") {
                if [
                    "studiomcp",
                    "no-studio",
                    "no-place",
                    "wrong-place",
                    "ambiguous-studio",
                    "unpublished-place",
                    "studio-busy",
                    "scan-",
                    "census-",
                    "universe-",
                ]
                .iter()
                .any(|p| cause.starts_with(p))
                {
                    println!("ENV|{cause}|{remedy}");
                    return Ok(3);
                }
            }
            Err(e)
        }
    }
}
fn clean(args: &[OsString]) -> Result<i32> {
    env_result((|| {
        let root = PathBuf::from(opts(args, "--root", "."));
        let cmd = opts(args, "--mcp-cmd", "");
        let session = opts(args, "--session", "local");
        let delete = args.iter().any(|x| x == "--delete");
        let wanted = read_places_block(&root.join("AGENTS.md"))?
            .values()
            .copied()
            .collect();
        let mut rpc = StudioRpc::new(if cmd.is_empty() { None } else { Some(&cmd) }, 30)?;
        let (_, pid) = rpc.select(&wanted)?;
        let _lock = PlaceLock::new(pid, &session, "rig_clean")?;
        let code = if delete { DELETE_LUAU } else { SCAN_LUAU };
        let text = rpc.call("execute_luau", json!({"code":code}), None)?;
        let rows = records(&text, "RIGS", "scan")?;
        if rows.is_empty() {
            return Ok(0);
        }
        let failed = delete && rows.iter().any(|r| r.ends_with("|fail"));
        println!(
            "rig_clean: {}\n",
            if failed {
                "FAILED"
            } else if delete {
                "CLEANED"
            } else {
                "FOUND"
            }
        );
        for row in rows {
            if delete {
                println!("{row}")
            } else {
                println!("{row}|found")
            }
        }
        Ok(if failed { 2 } else { 0 })
    })())
}
fn map(args: &[OsString]) -> Result<i32> {
    env_result((|| {
        let root = PathBuf::from(opts(args, "--root", "."));
        let cmd = opts(args, "--mcp-cmd", "");
        let agents = root.join("AGENTS.md");
        let mapping = read_places_block(&agents)?;
        let wanted = mapping.values().copied().filter(|v| *v > 0).collect();
        let mut children = Vec::new();
        if let Ok(dir) = fs::read_dir(root.join("places")) {
            for entry in dir {
                let e = entry?;
                if e.path().is_dir() {
                    children.push(e.file_name().to_string_lossy().into_owned())
                }
            }
        }
        children.sort();
        let mut rpc = StudioRpc::new(if cmd.is_empty() { None } else { Some(&cmd) }, 30)?;
        let (id, _) = rpc.select(&wanted)?;
        let universe = parse_universe(&rpc.call(
            "execute_luau",
            json!({"code":UNIVERSE_LUAU,"datamodel_type":"Edit"}),
            Some(&id),
        )?)?;
        let mut new = BTreeMap::new();
        let mut owners = BTreeMap::new();
        let mut problems = Vec::new();
        let mut mapped = Vec::new();
        for name in children {
            let pid = mapping.get(&name).copied().unwrap_or(0);
            if pid > 0 {
                if !universe.contains_key(&pid) {
                    problems.push(format!("ENV|stale-mapping|Open the right project experience, update places/{name} PlaceId, then retry."));
                    continue;
                }
                if let Some(owner) = owners.get(&pid) {
                    problems.push(format!("ENV|duplicate-mapping|Give places/{owner} and places/{name} unique PlaceIds, then retry."));
                    continue;
                }
                new.insert(name.clone(), pid);
                owners.insert(pid, name);
                continue;
            }
            let matches = universe
                .iter()
                .filter(|(id, n)| *n == &name && !owners.contains_key(*id))
                .map(|(id, _)| *id)
                .collect::<Vec<_>>();
            if matches.len() == 1 {
                let id = matches[0];
                new.insert(name.clone(), id);
                owners.insert(id, name.clone());
                mapped.push((name, id));
            } else {
                problems.push(format!(
                    "ENV|unmapped-child|Link places/{name} to its Roblox PlaceId, then retry."
                ));
            }
        }
        for (id, name) in &universe {
            if !owners.contains_key(id) {
                problems.push(format!(
                    "ENV|unmapped-place|Add places/{name} for PlaceId {id}, then retry."
                ));
            }
        }
        for (name, id) in mapped {
            println!("mapped|{name}|{id}")
        }
        if !problems.is_empty() {
            for p in problems {
                println!("{p}")
            }
            return Ok(3);
        }
        write_places_block(&agents, &new)?;
        for (name, id) in new {
            println!("place|{name}|{id}")
        }
        Ok(0)
    })())
}

fn census(args: &[OsString]) -> Result<i32> {
    env_result((|| {
        let root = PathBuf::from(opts(args, "--root", "."));
        let cmd = opts(args, "--mcp-cmd", "");
        let session = opts(args, "--session", "local");
        let wanted = read_places_block(&root.join("AGENTS.md"))?
            .values()
            .copied()
            .collect();
        let mut rpc = StudioRpc::new(if cmd.is_empty() { None } else { Some(&cmd) }, 30)?;
        let (_, pid) = rpc.select(&wanted)?;
        let _lock = PlaceLock::new(pid, &session, "map_census")?;
        let text = rpc.call("execute_luau", json!({"code":CENSUS_LUAU}), None)?;
        let rows = records(&text, "CENSUS", "census")?;
        let mut data = BTreeMap::new();
        for row in rows {
            let p = row.split('|').collect::<Vec<_>>();
            if p.len() == 8 {
                let nums = p[1..]
                    .iter()
                    .map(|n| n.parse::<i64>())
                    .collect::<std::result::Result<Vec<_>, _>>()?;
                data.insert(p[0].to_string(), nums);
            }
        }
        let mut notes = Vec::new();
        for (path, n) in &data {
            let mut opts = Vec::new();
            for (name, i) in [
                ("CastShadow", 1),
                ("CanQuery", 2),
                ("CanCollide", 3),
                ("CanTouch", 6),
            ] {
                if n[i] > 0 {
                    opts.push(format!("{name} on {}/{}", n[i], n[0]))
                }
            }
            if n[0] > n[4] {
                opts.push(format!("unanchored {}/{}", n[0] - n[4], n[0]))
            }
            if !opts.is_empty() {
                notes.push(format!("census|{path}|{} parts|{}", n[0], opts.join(", ")))
            }
        }
        let mut files = Vec::new();
        let mut i = 0;
        while i < args.len() {
            let a = args[i].to_string_lossy();
            if ["--root", "--mcp-cmd", "--session"].contains(&a.as_ref()) {
                i += 2;
            } else {
                files.push(PathBuf::from(args[i].clone()));
                i += 1;
            }
        }
        if files.is_empty() {
            for entry in walkdir::WalkDir::new(root.join("shared"))
                .follow_links(false)
                .into_iter()
                .filter_map(|e| e.ok())
            {
                if entry.file_type().is_file() {
                    files.push(entry.path().to_path_buf())
                }
            }
        }
        let re = Regex::new(r#"([%\w_.\[\]"']+):(Destroy|Clone)\s*\("#).unwrap();
        let mut skipped = Vec::new();
        let mut findings = Vec::new();
        for path in files {
            if !matches!(
                path.extension().and_then(|s| s.to_str()),
                Some("lua" | "luau")
            ) || path
                .symlink_metadata()
                .map(|m| m.file_type().is_symlink())
                .unwrap_or(true)
            {
                continue;
            }
            let text = fs::read_to_string(&path)?;
            for (line_no, line) in text.lines().enumerate() {
                for m in re.captures_iter(line) {
                    let chain = &m[1];
                    let method = &m[2];
                    let leaf = chain
                        .rsplit('.')
                        .next()
                        .unwrap()
                        .trim_matches(&['\"', '\'', '[', ']'][..]);
                    let hit = data
                        .iter()
                        .find(|(p, _)| *p == leaf || p.ends_with(&format!(".{leaf}")));
                    if let Some((target, n)) = hit {
                        if n[0] > 1000 {
                            findings.push((
                                path.clone(),
                                line_no + 1,
                                m.get(1).unwrap().start() + 1,
                                format!("{chain}:{method} on {target} ({} parts)", n[0]),
                            ));
                        }
                    } else {
                        skipped.push(format!(
                            "{}:{} {}:{}",
                            elide(&path, &root),
                            line_no + 1,
                            chain,
                            method
                        ));
                    }
                }
            }
        }
        if findings.is_empty() {
            println!("map_census: MEASURED")
        } else {
            println!("map_census: NOTED\n");
            let mut previous = None;
            for (path, line, col, subject) in findings {
                if previous.as_ref() != Some(&path) {
                    if previous.is_some() {
                        println!()
                    }
                    println!("{}:\n", elide(&path, &root));
                    previous = Some(path);
                }
                println!("{line}|{col}|OPT23|{subject}|frame-stagger - >1000 parts in one frame");
            }
        }
        println!();
        for n in notes.iter().take(30) {
            println!("{n}")
        }
        for s in skipped.iter().take(10) {
            println!("SKIPPED OPT23 {s} - census does not resolve the target")
        }
        Ok(0)
    })())
}

fn boot(args: &[OsString]) -> Result<i32> {
    let root = fs::canonicalize(opts(args, "--root", "."))?;
    let project = opts(args, "--project", "default.project.json");
    let seconds = opts(args, "--play-seconds", "12.0").parse::<f64>()?;
    let cmd = opts(args, "--mcp-cmd", "");
    let log = opts(args, "--console-log", "");
    let session = opts(args, "--session", "local");
    let mut verdict = json!({"sourcemap":null,"analyze":null,"play":null,"pass":false});
    let result = (|| -> Result<i32> {
        let project_path = root.join(&project);
        if !project_path.is_file() {
            bail!("no-project: no {project} under {}", root.display())
        }
        let tmp = tempfile::tempdir()?;
        let smap = tmp.path().join("sourcemap.json");
        let generated = Command::new("argon")
            .args(["sourcemap"])
            .arg(&project_path)
            .arg("-o")
            .arg(&smap)
            .current_dir(&root)
            .output()?;
        if !generated.status.success() || !smap.is_file() {
            let detail = String::from_utf8_lossy(&[generated.stdout, generated.stderr].concat())
                .trim()
                .to_string();
            let tail = detail
                .chars()
                .rev()
                .take(400)
                .collect::<String>()
                .chars()
                .rev()
                .collect::<String>();
            verdict["sourcemap"] = json!({"pass":false,"detail":tail});
            return Ok(2);
        }
        verdict["sourcemap"] = json!({"pass":true});
        let harness = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let definitions = harness.join("tools/globalTypes.d.luau");
        if !definitions.is_file() {
            bail!("definitions-absent: vendored globalTypes.d.luau missing")
        }
        let bundled = harness.join("tools/bin/luau-lsp");
        let lsp = if bundled.exists() {
            bundled
        } else {
            PathBuf::from("luau-lsp")
        };
        let mut command = Command::new(lsp);
        command
            .current_dir(&root)
            .args([
                "analyze",
                "--flag:LuauSolverV2=true",
                "--no-strict-dm-types",
                "--platform",
                "roblox",
                "--sourcemap",
            ])
            .arg(&smap)
            .arg("--definitions")
            .arg(format!("@roblox={}", definitions.display()))
            .arg("--base-luaurc")
            .arg(harness.join("tools/base.luaurc"))
            .args([
                "--ignore",
                "**/_Index/**",
                "--ignore",
                "**/Packages/**",
                "--ignore",
                "**/Modules/**",
                "--ignore",
                "**/tests/**",
            ]);
        let mut found = false;
        for name in ["shared", "places"] {
            if root.join(name).is_dir() {
                command.arg(name);
                found = true
            }
        }
        if !found {
            command.arg(".");
        }
        let analyzed = command.output()?;
        let all = String::from_utf8_lossy(&[analyzed.stdout, analyzed.stderr].concat()).to_string();
        if !matches!(analyzed.status.code(), Some(0 | 1)) {
            let detail = all
                .trim()
                .chars()
                .rev()
                .take(300)
                .collect::<String>()
                .chars()
                .rev()
                .collect::<String>();
            bail!("analyze-crashed: {detail}")
        }
        let re = Regex::new(r"^.+\(\d+,\d+\): \w+").unwrap();
        let findings = all.lines().filter(|l| re.is_match(l)).collect::<Vec<_>>();
        verdict["analyze"] = json!({"pass":findings.is_empty(),"findings":findings.len(),"lines":findings.iter().take(20).collect::<Vec<_>>()});
        let (lines, place) = if !log.is_empty() {
            if !Path::new(&log).is_file() {
                bail!("console-log-absent: {log}")
            }
            (
                fs::read_to_string(log)?
                    .lines()
                    .map(str::to_string)
                    .collect::<Vec<_>>(),
                None,
            )
        } else {
            let wanted = read_places_block(&root.join("AGENTS.md"))?
                .values()
                .copied()
                .collect();
            let mut rpc = StudioRpc::new(if cmd.is_empty() { None } else { Some(&cmd) }, 30)?;
            let (_, pid) = rpc.select(&wanted)?;
            let _lock = PlaceLock::new(pid, &session, "boot_smoke")?;
            let before = rpc.call("get_console_output", json!({}), None)?;
            rpc.call("start_stop_play", json!({"is_start":true}), None)?;
            if seconds > 0.0 {
                std::thread::sleep(Duration::from_secs_f64(seconds))
            }
            let after = rpc.call("get_console_output", json!({}), None);
            let stopped = rpc.call("start_stop_play", json!({"is_start":false}), None);
            let after = after?;
            stopped?;
            let base = before.lines().collect::<Vec<_>>();
            let post = after.lines().collect::<Vec<_>>();
            let lines = if post.starts_with(&base) {
                &post[base.len()..]
            } else {
                &post
            };
            (lines.iter().map(|s| s.to_string()).collect(), Some(pid))
        };
        let errors=Regex::new(r"(?i)\berrors?\b|\bexception\b|stack begin|attempt to (index|call|perform|compare)|failed to load|cannot resume|is not a valid member|infinite loop").unwrap();
        let warnings=Regex::new(r"(?i)\bwarn\b|infinite yield|\bfailed\b|services? unavailable|attempted to call require").unwrap();
        let err = lines
            .iter()
            .filter(|s| errors.is_match(s))
            .take(20)
            .collect::<Vec<_>>();
        let warn = lines
            .iter()
            .filter(|s| !errors.is_match(s) && warnings.is_match(s))
            .take(20)
            .collect::<Vec<_>>();
        let mut play = json!({"pass":err.is_empty(),"seconds":if place.is_some(){json!(seconds)}else{Value::Null},"new_lines":lines.len(),"errors":err,"warnings":warn});
        if let Some(pid) = place {
            play["place_id"] = json!(pid)
        }
        verdict["play"] = play;
        let pass = verdict["analyze"]["pass"] == true && verdict["play"]["pass"] == true;
        verdict["pass"] = json!(pass);
        Ok(if pass { 0 } else { 2 })
    })();
    let status = match result {
        Ok(s) => s,
        Err(e) => {
            let text = e.to_string();
            if let Some((cause, remedy)) = text.split_once(": ") {
                if [
                    "no-project",
                    "definitions-absent",
                    "analyze-crashed",
                    "console-log-absent",
                    "studiomcp",
                    "no-studio",
                    "wrong-place",
                    "unpublished-place",
                    "ambiguous-studio",
                    "studio-busy",
                ]
                .iter()
                .any(|s| cause.starts_with(s))
                {
                    verdict["environment"] = json!({"cause":cause,"remedy":remedy});
                    println!("{}", verdict);
                    return Ok(3);
                }
            }
            eprintln!("boot_smoke: CRASH {text} - nothing was verified");
            return Ok(2);
        }
    };
    println!("{}", verdict);
    Ok(status)
}

#[derive(Parser)]
struct OutputArgs {
    #[arg(long, conflicts_with = "input")]
    studio_id: Option<String>,
    #[arg(long)]
    input: Option<PathBuf>,
    #[arg(long)]
    scope: Option<String>,
    #[arg(long)]
    since: Option<PathBuf>,
    #[arg(long)]
    contains: Vec<String>,
    #[arg(long, default_value_t = 40)]
    tail: usize,
    #[arg(long, default_value_t = 8000)]
    max_chars: usize,
    #[arg(long)]
    mcp_cmd: Option<String>,
    #[arg(long)]
    side: Option<String>,
    #[arg(long)]
    script: Option<String>,
    #[arg(long)]
    run: Option<String>,
    #[arg(long, default_value_t = 0.0)]
    wait: f64,
}
fn canonical_json(v: &Value) -> String {
    match v {
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(canonical_json).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(o) => {
            let mut keys = o.keys().collect::<Vec<_>>();
            keys.sort();
            format!(
                "{{{}}}",
                keys.iter()
                    .map(|k| format!(
                        "{}: {}",
                        serde_json::to_string(k).unwrap(),
                        canonical_json(&o[*k])
                    ))
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        }
        _ => serde_json::to_string(v).unwrap(),
    }
}
fn unique_push(v: &mut Vec<String>, value: String) {
    if !v.contains(&value) {
        v.push(value)
    }
}
fn output(args: &[OsString]) -> Result<i32> {
    let mut argv = vec![OsString::from("studio output")];
    argv.extend_from_slice(args);
    let a = match OutputArgs::try_parse_from(argv) {
        Ok(v) => v,
        Err(e) => {
            e.print()?;
            return Ok(2);
        }
    };
    let result = (|| -> Result<i32> {
        if a.input.is_none() && a.studio_id.is_none() {
            bail!("one of --studio-id or --input is required")
        }
        if !(1..=1000).contains(&a.tail) || !(1..=100000).contains(&a.max_chars) {
            bail!("tail must be 1..1000; max-chars must be 1..100000")
        }
        if !(0.0..=300.0).contains(&a.wait) {
            bail!("wait must be 0..300")
        }
        let fields = [a.side.as_ref(), a.script.as_ref(), a.run.as_ref()];
        let decode = fields.iter().any(|x| x.is_some());
        if decode && fields.iter().any(|x| x.is_none()) {
            bail!("side, script and run required together")
        }
        if let Some(side) = &a.side {
            if side != "SERVER" && side != "CLIENT" {
                bail!("invalid side")
            }
        }
        let expected = if decode {
            Some((
                a.side.clone().unwrap(),
                a.script.clone().unwrap(),
                a.run.clone().unwrap(),
            ))
        } else {
            None
        };
        let scope = if let Some(p) = &a.input {
            format!(
                "file:{}",
                a.scope
                    .clone()
                    .unwrap_or(fs::canonicalize(p)?.to_string_lossy().into_owned())
            )
        } else {
            format!("studio:{}", a.studio_id.as_ref().unwrap())
        };
        let deadline = Instant::now() + Duration::from_secs_f64(a.wait);
        let mut since = a.since.clone();
        let mut retained = Vec::new();
        let mut shown = BTreeSet::new();
        loop {
            let console = if let Some(p) = &a.input {
                fs::read_to_string(p)?
            } else {
                let id = a.studio_id.as_deref().unwrap();
                let mut rpc = StudioRpc::new(a.mcp_cmd.as_deref(), 30)?;
                if !rpc.list_studios()?.iter().any(|v| v["id"] == id) {
                    bail!("studio_id is not in the current Studio list")
                }
                rpc.call("get_console_output", json!({"studio_id":id}), Some(id))?
            };
            let mut before = String::new();
            let mut transport = Vec::<String>::new();
            let mut errors = Vec::<String>::new();
            if let Some(path) = &since {
                use sha2::{Digest, Sha256};
                let bytes = fs::read(path)?;
                let hash = hex::encode(Sha256::digest(&bytes));
                if path.file_stem().and_then(|s| s.to_str()) != Some(&hash) {
                    bail!("snapshot hash mismatch")
                }
                let v: Value = serde_json::from_slice(&bytes)?;
                if v["schema"] != "harness-console-v1" || v["scope"] != scope {
                    bail!("snapshot scope mismatch")
                }
                before = v["console"].as_str().unwrap_or("").to_string();
                transport = v["transport"]
                    .as_array()
                    .map(|a| {
                        a.iter()
                            .filter_map(|x| x.as_str().map(str::to_string))
                            .collect()
                    })
                    .unwrap_or_default();
                errors = v["errors"]
                    .as_array()
                    .map(|a| {
                        a.iter()
                            .filter_map(|x| x.as_str().map(str::to_string))
                            .collect()
                    })
                    .unwrap_or_default();
            }
            let old = before.lines().collect::<Vec<_>>();
            let new = console.lines().collect::<Vec<_>>();
            let (lines, continuity) = if old.is_empty() {
                (&new[..], "baseline")
            } else if new.starts_with(&old) {
                (&new[old.len()..], "append")
            } else {
                (&new[..], "reset-or-rotation")
            };
            let selected = lines
                .iter()
                .filter(|line| a.contains.iter().all(|t| line.contains(t)))
                .copied()
                .collect::<Vec<_>>();
            let displayed = &selected[selected.len().saturating_sub(a.tail)..];
            let text = displayed.join("\n");
            let error_re = Regex::new(r"(?i)error|exception|stack begin|stack end|FAIL\|").unwrap();
            let mut controls = Vec::new();
            for line in lines {
                for side in ["SERVER|", "CLIENT|"] {
                    if line.contains("|BUF|") {
                        if let Some(i) = line.find(side) {
                            if let Some(record) = line[i..].split_whitespace().next() {
                                unique_push(&mut transport, record.to_string())
                            }
                        }
                    }
                }
                if error_re.is_match(line) {
                    unique_push(&mut errors, (*line).to_string())
                }
                if line.contains("|CTRL|") {
                    controls.push((*line).to_string())
                }
            }
            if transport.len() > 8192 {
                bail!("transport retention limit; collect each run separately")
            }
            let payload = json!({"schema":"harness-console-v1","scope":scope,"console":console,"transport":transport,"errors":errors});
            let raw = format!("{}\n", canonical_json(&payload));
            use sha2::{Digest, Sha256};
            let cache = cache_dir()?.join("console");
            fs::create_dir_all(&cache)?;
            let artifact = cache.join(format!(
                "{}.json",
                hex::encode(Sha256::digest(raw.as_bytes()))
            ));
            let mut temp = tempfile::NamedTempFile::new_in(&cache)?;
            temp.write_all(raw.as_bytes())?;
            temp.persist(&artifact)?;
            since = Some(artifact.clone());
            for err in &errors {
                unique_push(&mut retained, err.clone())
            }
            for notice in controls {
                if shown.insert(notice.clone()) {
                    println!("{notice}")
                }
            }
            let shortened = text
                .chars()
                .rev()
                .take(a.max_chars)
                .collect::<String>()
                .chars()
                .rev()
                .collect::<String>();
            if !decode {
                if !transport.is_empty() {
                    let mut c = crate::buffer::Collector::new(None);
                    c.feed(&transport.join("\n"));
                    println!("{}", crate::buffer::summary(&c.finish()?));
                } else {
                    println!(
                        "{}",
                        shortened
                            .lines()
                            .filter(|line| !line.contains("|CTRL|") && !line.contains("|BUF|"))
                            .collect::<Vec<_>>()
                            .join("\n")
                    );
                }
                for error in &errors {
                    if !shortened.contains(error) {
                        println!("{error}")
                    }
                }
                println!("OUTPUT|{continuity}|artifact={}", artifact.display());
                return Ok(0);
            }
            let mut collector = crate::buffer::Collector::new(expected.clone());
            collector.feed(&transport.join("\n"));
            match collector.finish() {
                Ok(records) => {
                    println!("{}", crate::buffer::summary(&records));
                    for err in &retained {
                        println!("{err}")
                    }
                    println!("OUTPUT|artifact={}", artifact.display());
                    return Ok(if records.iter().all(|r| r.result.status == "pass") {
                        0
                    } else {
                        2
                    });
                }
                Err(e) => {
                    let msg = e.to_string();
                    if (msg == "missing output" || msg == "incomplete buffer")
                        && Instant::now() < deadline
                    {
                        std::thread::sleep(
                            Duration::from_millis(250)
                                .min(deadline.saturating_duration_since(Instant::now())),
                        );
                        continue;
                    }
                    for err in &retained {
                        println!("{err}")
                    }
                    println!("OUTPUT|artifact={}", artifact.display());
                    return Err(e);
                }
            }
        }
    })();
    match result {
        Ok(v) => Ok(v),
        Err(e) => {
            println!("OUTPUT|rejected|{e}");
            Ok(2)
        }
    }
}

fn elide(path: &Path, root: &Path) -> String {
    let path = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    let root = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let rel = path.strip_prefix(root).unwrap_or(&path);
    let mut parts = rel
        .components()
        .map(|c| c.as_os_str().to_string_lossy().into_owned())
        .filter(|s| !s.is_empty() && s != ".")
        .collect::<Vec<_>>();
    if parts.first().map(String::as_str) == Some("places") && parts.len() >= 2 {
        parts.remove(0);
    }
    if parts.len() > 4 {
        let removed = parts.len() - 4;
        let mut result = vec![parts[0].clone(), ".".repeat(removed)];
        result.extend_from_slice(&parts[parts.len() - 3..]);
        result.join("/")
    } else {
        parts.join("/")
    }
}
