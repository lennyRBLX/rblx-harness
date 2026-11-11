use anyhow::{anyhow, bail, Result};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    process::Command,
};
use walkdir::WalkDir;

const SCAFFOLD: &str = "scaffold";
const BOILER: &str = "boiler";
const MODULE_HELP: &str = r#"create_boilerplate — the one emitter [R BC4, BC5]. Deterministic
generation, not analysis: same kind and name produce the same bytes, and the
output is a fixed point of the formatter.

  create_boilerplate <kind> <Name> [--root DIR] [--place P] [--side server|client]
  create_boilerplate --test <Mode>.<Name> --place <Place> [--side server|client] [--root DIR]
  create_boilerplate --expand <Name> [--place P] [--root DIR]

With --place, a kind emits under places/<P>/src/ instead of shared/src/ —
for service, controller and tool-handler the same subtree, mounted per-place
by the Argon project (PlaceServices / PlaceControllers). gui is the
exception: the shared tree nests it under Controllers/Gui/, a place mounts
Gui/ directly under StarterPlayerScripts, so gui carries its own per-place
destination rather than the prefix swap. Without --place, shared/src/ as
before. The place must already exist under places/; data-module and update
are shared-tree only — nothing mounts a place Data/ and the Updates runner
scans only the shared folder.

Kinds: service · controller · gui · update · data-module · tool-handler.
The destination is derived from kind and whether --place is given — a path
is never passed [R GATE2]. A new service or controller is a single file
until it needs children; --expand converts the flat file to the folder form
in one deterministic, reversible step.

A Service or Controller suffix produces a naming advisory [R WRIT10] but does
not deny emission. Unsafe path-shaped names remain refused [R GATE2]. An
existing target exits 2 — test sources are also preserved [R
DEBUG2]."#;
const SERVER_ENTRY: &str = r#"const ServerScriptService = game:GetService("ServerScriptService")
const ReplicatedStorage = game:GetService("ReplicatedStorage")
const Players = game:GetService("Players")

const packages = ReplicatedStorage:FindFirstChild("Packages")
const cleanupModule = packages and packages:FindFirstChild("EntityCleanup")
if cleanupModule then
	const EntityCleanup = require(cleanupModule)
	Players.PlayerRemoving:Connect(function(player)
		EntityCleanup:Cleanup(player)
	end)
end

local roots = { ServerScriptService.Services }
local placeServices = ServerScriptService:FindFirstChild("PlaceServices")
if placeServices then
	table.insert(roots, placeServices)
end

for _, root in roots do
	for _, child in root:GetChildren() do
		if child:IsA("ModuleScript") then
			local service = require(child)
			if type(service) == "table" and type(service.Start) == "function" then
				task.spawn(function()
					service:Start()
				end)
			end
		end
	end
end
"#;
const CLIENT_ENTRY: &str = r#"local Players = game:GetService("Players")

local playerScripts = Players.LocalPlayer:WaitForChild("PlayerScripts")
local roots = { playerScripts.Controllers }
local placeControllers = playerScripts:FindFirstChild("PlaceControllers")
if placeControllers then
	table.insert(roots, placeControllers)
end

for _, root in roots do
	for _, child in root:GetChildren() do
		if child:IsA("ModuleScript") then
			local controller = require(child)
			if type(controller) == "table" and type(controller.Start) == "function" then
				task.spawn(function()
					controller:Start()
				end)
			end
		end
	end
end
"#;
const GUI_FRAME: &str = r#"const Players = game:GetService("Players")

const Player = Players.LocalPlayer

const m = {}

-- privates

-- functions
function m:Start()
	local gui = Player:WaitForChild("PlayerGui", 10)
	if not gui then
		warn(script.Name .. " | no PlayerGui after 10s | the GUI does not start")
		return
	end
end

return m
"#;
const TOOL_FRAME:&str = "const m = {}\n\n-- privates\n\n-- functions\nfunction m:Start()\nend\n\nfunction m:Equipped(player, tool)\nend\n\nfunction m:Activated(player, tool)\nend\n\n-- events\n\nreturn m\n";
const UPDATE_FRAME:&str = "const RELEASE_DATE = \"{date}\"\n\nconst m = {{\n\tReleaseDate = \"{date}\"\n}}\n\n-- privates\n\n-- functions\nfunction m:Start()\n\tif m.notLatestUpdate then\n\t\treturn\n\tend\nend\n\nfunction m:Destroy()\nend\n\n-- events\n\nreturn m\n";
const DATA_FRAME: &str = "export type Entry = {\n\tName: string,\n}\n\nreturn {}\n";
const TEST_FRAME: &str = r#"-- {what}
-- {how}
local ENABLED = false
local RunService = game:GetService("RunService")

if not ENABLED or not RunService:IsStudio() then
    return
end

local Runner = require(script.Parent.TestSupport.Runner)
Runner.run(script, {{
    id = "{id}", -- One question; new question needs a new ID.
    timeout = 30,
    setup = function(context)
        -- Own fixtures through context. Declare metrics and spike thresholds here.
    end,
    warmup = function(context)
        -- Warm the representative workload outside measurement.
    end,
    workload = function(context)
        -- Stop on the declared acceptance condition. Missing assertions cannot pass.
        context:check(false, "test question and stopping condition required")
    end,
}})
"#;
const FIELDS: &[&str] = &[
    "gameplay",
    "places",
    "services",
    "controllers",
    "assets",
    "harness",
];
const IGNORE: &str = "# BEGIN rblx-new-game\n/.agents/\n/.claude/\n/.codex/\n/.serena/\n/.roblox\n.DS_Store\n# END rblx-new-game";
const URL: &str = "https://github.com/lennyRBLX/rblx-harness.git";
fn frame(src: &str, name: &str) -> String {
    match (src,name) {
    (SCAFFOLD,"SERVER_ENTRY")=>SERVER_ENTRY.into(),
    (SCAFFOLD,"CLIENT_ENTRY")=>CLIENT_ENTRY.into(),
    (SCAFFOLD,"SERVICE_FRAME")=>"local m = {}\n\n-- privates\n\n-- functions\nfunction m:Start()\nend\n\n-- events\n\nreturn m\n".into(),
    (SCAFFOLD,"CONTROLLER_FRAME")=>"local m = {}\n\n-- privates\n\n-- functions\nfunction m:Start()\nend\n\nreturn m\n".into(),
    (BOILER,"FRAME")=>"const m = {}\n\n-- privates\n\n-- functions\nfunction m:Start()\nend\n\n-- events\n\nreturn m\n".into(),
    (BOILER,"CONTROLLER_FRAME")=>"const m = {}\n\n-- privates\n\n-- functions\nfunction m:Start()\nend\n\nreturn m\n".into(),
    (BOILER,"GUI_FRAME")=>GUI_FRAME.into(),
    (BOILER,"TOOL_FRAME")=>TOOL_FRAME.into(),
    (BOILER,"UPDATE_FRAME")=>UPDATE_FRAME.into(),
    (BOILER,"DATA_FRAME")=>DATA_FRAME.into(),
    (BOILER,"TEST_FRAME")=>TEST_FRAME.into(),
    _=>unreachable!()
}
}
fn safe(s: &str) -> bool {
    let mut b = s.bytes();
    b.next().map_or(false, |c| c.is_ascii_alphabetic()) && b.all(|c| c.is_ascii_alphanumeric())
}
fn root() -> Result<PathBuf> {
    Ok(std::env::current_dir()?)
}
fn put(p: &Path, s: &str, overwrite: bool) -> Result<()> {
    if !overwrite && p.exists() {
        return Ok(());
    }
    fs::create_dir_all(p.parent().unwrap())?;
    fs::write(p, s)?;
    Ok(())
}
fn json_put(p: &Path, v: &Value) -> Result<()> {
    put(p, &format!("{}\n", serde_json::to_string_pretty(v)?), true)
}
fn canonical(p: &Path) -> Result<PathBuf> {
    fs::canonicalize(p).map_err(|_| anyhow!("project root is absent"))
}
fn ignore(root: &Path) -> Result<()> {
    let p = root.join(".gitignore");
    let current = fs::read_to_string(&p).unwrap_or_default();
    let re = regex::Regex::new(r"(?s)# BEGIN rblx-new-game.*?# END rblx-new-game\s*")?;
    let retained = re.replace_all(&current, "");
    let retained = retained.trim();
    put(
        &p,
        &format!(
            "{}{}{}\n",
            retained,
            if retained.is_empty() { "" } else { "\n\n" },
            IGNORE
        ),
        true,
    )
}
fn load(root: &Path) -> Value {
    let mut v: Value = fs::read(root.join("manifest.json"))
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .filter(Value::is_object)
        .unwrap_or(json!({}));
    for k in ["places", "assets"] {
        if let Some(a) = v[k].as_array() {
            let s = a
                .iter()
                .filter_map(Value::as_str)
                .collect::<Vec<_>>()
                .join(", ");
            v[k] = json!(if s.is_empty() && k == "assets" {
                "none".to_string()
            } else {
                s
            });
        }
    }
    if let Some(b) = v["harness"].as_bool() {
        v["harness"] = json!(if b { "yes" } else { "no" });
    }
    v
}
fn places(s: &str) -> Result<Vec<String>> {
    let v: Vec<String> = s
        .split([',', ';', '\n'])
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .collect();
    if v.is_empty() || v.iter().any(|x| !safe(x)) {
        bail!("places must be comma-separated safe names")
    }
    let set: BTreeSet<_> = v.iter().map(|x| x.to_lowercase()).collect();
    if set.len() != v.len() {
        bail!("each place must be named once")
    }
    Ok(v)
}
fn components(s: &str, places: &[String]) -> Result<Vec<(String, String)>> {
    if s.trim().eq_ignore_ascii_case("none") {
        return Ok(vec![]);
    }
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    for clause in s
        .split([';', '\n'])
        .map(str::trim)
        .filter(|s| !s.is_empty())
    {
        let (scope, raw) = clause
            .split_once(':')
            .ok_or_else(|| anyhow!("use 'shared: Name; Place: Name' or none"))?;
        let scope = scope.trim();
        let scope = if scope.eq_ignore_ascii_case("shared") {
            "shared".to_string()
        } else if !places.is_empty() {
            places
                .iter()
                .find(|p| p.eq_ignore_ascii_case(scope))
                .cloned()
                .ok_or_else(|| anyhow!("unknown place scope: {}", scope))?
        } else if safe(scope) {
            scope.to_string()
        } else {
            bail!("invalid scope: {}", scope)
        };
        let names: Vec<_> = raw
            .split(',')
            .map(str::trim)
            .filter(|x| !x.is_empty())
            .collect();
        if names.is_empty() {
            bail!("{} must name at least one module", scope)
        }
        for name in names {
            if !safe(name) {
                bail!("invalid module name: {}", name)
            }
            for suffix in ["service", "controller"] {
                if name.to_lowercase().ends_with(suffix) {
                    let bare = &name[..name.len() - suffix.len()];
                    if bare.is_empty() {
                        bail!(
                            "module names must omit Service and Controller suffixes: {}",
                            name
                        )
                    }
                    bail!("module names must omit Service and Controller suffixes: use {} instead of {}",bare,name)
                }
            }
            if !seen.insert((scope.to_lowercase(), name.to_lowercase())) {
                bail!("module is repeated: {}:{}", scope, name)
            }
            out.push((scope.clone(), name.to_string()));
        }
    }
    Ok(out)
}
fn assets(s: &str) -> Result<Vec<String>> {
    let normalized = s
        .to_lowercase()
        .replace([',', ';'], " ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    if ["all", "accept all", "yes all", "yes to all"].contains(&normalized.as_str()) {
        return Ok(["packages", "services", "controllers", "plugins"]
            .iter()
            .map(|s| s.to_string())
            .collect());
    }
    if ["none", "no"].contains(&normalized.as_str()) {
        return Ok(vec![]);
    }
    let mut v = Vec::new();
    for t in normalized.split_whitespace() {
        let a = match t {
            "package" | "packages" => "packages",
            "service" | "services" => "services",
            "controller" | "controllers" => "controllers",
            "plugin" | "plugins" => "plugins",
            "support" | "and" => continue,
            _ => bail!("unknown asset choice: {}", t),
        };
        if !v.iter().any(|x| x == a) {
            v.push(a.to_string())
        }
    }
    Ok(v)
}
fn yes(s: &str) -> Result<bool> {
    match s.trim().to_lowercase().as_str() {
        "yes" | "y" | "true" | "use" | "accept" => Ok(true),
        "no" | "n" | "false" | "decline" => Ok(false),
        _ => bail!("harness answer must be Yes or No"),
    }
}
fn module_dest(root: &Path, category: &str, scope: &str, name: &str) -> PathBuf {
    let base = if scope == "shared" {
        root.join("shared")
    } else {
        root.join("places").join(scope)
    };
    base.join(if category == "services" {
        "src/ServerScriptService/Services"
    } else {
        "src/StarterPlayer/StarterPlayerScripts/Controllers"
    })
    .join(format!("{}.luau", name))
}
fn clean_name(s: &str) -> &str {
    for suffix in [
        ".server.luau",
        ".client.luau",
        ".server.lua",
        ".client.lua",
        ".luau",
        ".lua",
    ] {
        if let Some(n) = s.strip_suffix(suffix) {
            return n;
        }
    }
    s.rsplit_once('.').map_or(s, |(n, _)| n)
}
fn inspect(root: &Path) -> Result<Value> {
    let root = canonical(root)?;
    let mut ps = BTreeSet::new();
    let pd = root.join("places");
    if let Ok(entries) = fs::read_dir(pd) {
        for e in entries.flatten() {
            let n = e.file_name().to_string_lossy().to_string();
            if safe(&n) && e.path().is_dir() {
                ps.insert(n);
            }
        }
    }
    let mut project_files = false;
    for e in fs::read_dir(&root)?.flatten() {
        let n = e.file_name().to_string_lossy().to_string();
        if let Some(p) = n.strip_suffix(".project.json") {
            project_files = true;
            if n != "default.project.json" && safe(p) {
                ps.insert(p.to_string());
            }
        }
    }
    let mut found: BTreeMap<String, BTreeMap<(String, String, String), Value>> = BTreeMap::new();
    let mut count = 0;
    let skip = [
        ".git",
        "rblx-harness",
        ".agents",
        ".claude",
        ".codex",
        ".serena",
        "plugin",
        "plugins",
        "__pycache__",
    ];
    for e in WalkDir::new(&root)
        .follow_links(false)
        .sort_by_file_name()
        .into_iter()
        .filter_entry(|e| {
            e.depth() == 0
                || !e.file_type().is_dir()
                || !skip.contains(&e.file_name().to_string_lossy().as_ref())
        })
    {
        let e = e?;
        if !e.file_type().is_file() {
            continue;
        }
        let filename = e.file_name().to_string_lossy();
        if !(filename.ends_with(".lua") || filename.ends_with(".luau")) {
            continue;
        }
        count += 1;
        let rel = e.path().strip_prefix(&root)?;
        let parts: Vec<String> = rel
            .iter()
            .map(|x| x.to_string_lossy().to_string())
            .collect();
        let cat = if parts.iter().any(|p| p.eq_ignore_ascii_case("services")) {
            "services"
        } else if parts.iter().any(|p| p.eq_ignore_ascii_case("controllers")) {
            "controllers"
        } else {
            continue;
        };
        let idx = parts
            .iter()
            .rposition(|p| p.eq_ignore_ascii_case(cat))
            .unwrap();
        if idx + 1 >= parts.len() {
            continue;
        }
        let name = clean_name(&parts[idx + 1]);
        if !safe(name)
            || ["tests", "placeservices", "placecontrollers"]
                .iter()
                .any(|x| name.eq_ignore_ascii_case(x))
        {
            continue;
        }
        let scope = parts
            .iter()
            .position(|p| p.eq_ignore_ascii_case("places"))
            .and_then(|i| parts.get(i + 1))
            .cloned()
            .unwrap_or("shared".into());
        let path = parts[..=idx + 1].join("/");
        let kind = if root.join(&path).is_dir() {
            "directory"
        } else {
            "file"
        };
        let rec = json!({"name":name,"scope":scope,"path":path,"kind":kind,"category":cat});
        if scope != "shared" {
            ps.insert(scope.clone());
        }
        found
            .entry(cat.into())
            .or_default()
            .insert((scope.to_lowercase(), name.to_lowercase(), path), rec);
    }
    let mut harness = json!({});
    for (cat, dir) in [
        ("services", "packages/ServerScriptService/Services"),
        (
            "controllers",
            "packages/StarterPlayer/StarterPlayerScripts/Controllers",
        ),
    ] {
        let mut names = BTreeSet::new();
        if let Ok(es) = fs::read_dir(Path::new(env!("CARGO_MANIFEST_DIR")).join(dir)) {
            for e in es.flatten() {
                let n = e.file_name().to_string_lossy().to_string();
                let name = if e.path().is_dir() {
                    n.clone()
                } else if n.ends_with(".lua") || n.ends_with(".luau") {
                    clean_name(&n).to_string()
                } else {
                    continue;
                };
                if safe(&name) {
                    names.insert(name);
                }
            }
        }
        let mut names: Vec<_> = names.into_iter().collect();
        names.sort_by_key(|s| s.to_lowercase());
        harness[cat] = json!(names);
    }
    let mut p: Vec<_> = ps.into_iter().collect();
    p.sort_by_key(|s| s.to_lowercase());
    let plugins = root.join("plugin").is_dir() || root.join("plugins").is_dir();
    let existing = count > 0 || !p.is_empty() || project_files || plugins;
    Ok(
        json!({"root":root,"project":if existing{"existing"}else{"new"},"git":root.join(".git").exists(),"harness":root.join("rblx-harness").exists(),"plugins":plugins,"places":p,"services":found.remove("services").unwrap_or_default().into_values().collect::<Vec<_>>(),"controllers":found.remove("controllers").unwrap_or_default().into_values().collect::<Vec<_>>(),"harness_assets":harness}),
    )
}
fn project(root: &Path, args: &[String]) -> Result<i32> {
    let cmd = args.first().map(String::as_str).unwrap_or("");
    match cmd {
        "inspect" => {
            println!("{}", serde_json::to_string_pretty(&inspect(root)?)?);
            Ok(0)
        }
        "status" => {
            let state = load(root);
            let missing: Vec<_> = FIELDS
                .iter()
                .filter(|k| state[**k].is_null() || state[**k] == "" || state[**k] == false)
                .copied()
                .collect();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({"answers":state,"missing":missing}))?
            );
            Ok(if missing.is_empty() { 0 } else { 2 })
        }
        "answer" => {
            let root = canonical(root)?;
            let field = args
                .get(1)
                .ok_or_else(|| anyhow!("answer requires <field> <text>"))?;
            if args.len() < 3 {
                bail!("answer requires <field> <text>")
            }
            if !FIELDS.contains(&field.as_str()) {
                bail!("field must be one of: {}", FIELDS.join(", "))
            }
            let text = args[2..].join(" ").trim().to_string();
            if text.is_empty() {
                bail!("{} answer is empty", field)
            }
            let mut state = load(&root);
            let normalized = match field.as_str() {
                "places" => places(&text)?.join(", "),
                "services" | "controllers" => {
                    let ps = state["places"]
                        .as_str()
                        .filter(|s| !s.is_empty())
                        .map(places)
                        .transpose()?
                        .unwrap_or_default();
                    components(&text, &ps)?;
                    text
                }
                "assets" => {
                    let a = assets(&text)?;
                    if a.is_empty() {
                        "none".into()
                    } else {
                        a.join(", ")
                    }
                }
                "harness" => {
                    if yes(&text)? {
                        "yes".into()
                    } else {
                        "no".into()
                    }
                }
                _ => text,
            };
            state[field] = json!(normalized);
            ignore(&root)?;
            json_put(&root.join("manifest.json"), &state)?;
            println!("ANSWERED|{}|{}", field, normalized);
            Ok(0)
        }
        "emit" => emit(root),
        _ => bail!("unknown project command: {}", cmd),
    }
}

fn sorted(v: Value) -> Value {
    match v {
        Value::Object(m) => {
            let mut entries: Vec<_> = m.into_iter().collect();
            entries.sort_by(|a, b| a.0.cmp(&b.0));
            Value::Object(entries.into_iter().map(|(k, v)| (k, sorted(v))).collect())
        }
        Value::Array(a) => Value::Array(a.into_iter().map(sorted).collect()),
        x => x,
    }
}
fn snapshot(root: &Path, inspection: &Value) -> Result<Vec<(Value, Vec<(PathBuf, Vec<u8>)>)>> {
    let mut out = Vec::new();
    for cat in ["services", "controllers"] {
        for rec in inspection[cat].as_array().unwrap() {
            let p = root.join(rec["path"].as_str().unwrap());
            if fs::symlink_metadata(&p)
                .map(|m| m.file_type().is_symlink())
                .unwrap_or(true)
            {
                continue;
            }
            let mut files = Vec::new();
            if p.is_dir() {
                for e in WalkDir::new(&p).follow_links(false) {
                    let e = e?;
                    if e.file_type().is_file() {
                        files.push((
                            e.path().strip_prefix(&p)?.to_path_buf(),
                            fs::read(e.path())?,
                        ));
                    }
                }
            } else {
                files.push((PathBuf::new(), fs::read(&p)?));
            }
            if !files.is_empty() {
                out.push((rec.clone(), files));
            }
        }
    }
    Ok(out)
}
fn emit(root: &Path) -> Result<i32> {
    let root = canonical(root)?;
    let state = load(&root);
    let missing: Vec<_> = FIELDS
        .iter()
        .filter(|k| state[**k].as_str().map_or(true, |s| s.trim().is_empty()))
        .copied()
        .collect();
    if !missing.is_empty() {
        bail!("missing interview answers: {}", missing.join(", "))
    }
    let ps = places(state["places"].as_str().unwrap())?;
    let services = components(state["services"].as_str().unwrap(), &ps)?;
    let controllers = components(state["controllers"].as_str().unwrap(), &ps)?;
    let mut a = assets(state["assets"].as_str().unwrap())?;
    let harness = yes(state["harness"].as_str().unwrap())?;
    if (root.join("plugin").is_dir() || root.join("plugins").is_dir())
        && !a.iter().any(|x| x == "plugins")
    {
        a.push("plugins".into())
    }
    if !harness
        && a.iter()
            .any(|x| ["packages", "services", "controllers"].contains(&x.as_str()))
    {
        bail!("harness packages, services, and controllers require rblx-harness")
    }
    if harness && !root.join("rblx-harness/Cargo.toml").is_file() {
        bail!("rblx-harness submodule is absent; run harness dependency setup --yes")
    }
    let legacy = root.join("plugin");
    let plugins = root.join("plugins");
    if let Ok(m) = fs::symlink_metadata(&legacy) {
        if fs::symlink_metadata(&plugins).is_ok() {
            bail!("both legacy plugin/ and plugins/ exist; merge them before scaffolding")
        }
        if m.file_type().is_symlink() || !m.is_dir() {
            bail!("legacy plugin/ must be a regular directory")
        }
        fs::rename(&legacy, &plugins)?;
    }
    let ins = inspect(&root)?;
    let snapshots = snapshot(&root, &ins)?;
    ignore(&root)?;
    for d in [
        "shared/src/ReplicatedStorage",
        "shared/src/ServerScriptService/Services",
        "shared/src/ServerScriptService/Modules",
        "shared/src/StarterPlayer/StarterPlayerScripts/Controllers",
    ] {
        fs::create_dir_all(root.join(d))?
    }
    for p in &ps {
        for d in [
            format!("places/{}/src/ServerScriptService/Services", p),
            format!(
                "places/{}/src/StarterPlayer/StarterPlayerScripts/Controllers",
                p
            ),
            format!("tests/{}/server", p),
            format!("tests/{}/client", p),
        ] {
            let d = root.join(d);
            fs::create_dir_all(&d)?;
            if fs::read_dir(&d)?.next().is_none() {
                fs::write(d.join(".gitkeep"), "")?
            }
        }
    }
    put(
        &root.join("shared/src/ServerScriptService/Server.server.luau"),
        &frame(SCAFFOLD, "SERVER_ENTRY"),
        false,
    )?;
    put(
        &root.join("shared/src/StarterPlayer/StarterPlayerScripts/Client.client.luau"),
        &frame(SCAFFOLD, "CLIENT_ENTRY"),
        false,
    )?;
    for (category, records) in [("services", services), ("controllers", controllers)] {
        for (scope, name) in records {
            let dest = module_dest(&root, category, &scope, &name);
            if !dest.exists() && !dest.with_extension("").is_dir() {
                put(
                    &dest,
                    &frame(
                        SCAFFOLD,
                        if category == "services" {
                            "SERVICE_FRAME"
                        } else {
                            "CONTROLLER_FRAME"
                        },
                    ),
                    true,
                )?;
            }
        }
    }
    let mut restored = Vec::new();
    for (rec, files) in snapshots {
        let s = rec["scope"].as_str().unwrap();
        let scope = if s.eq_ignore_ascii_case("shared") {
            Some("shared")
        } else {
            ps.iter()
                .find(|p| p.eq_ignore_ascii_case(s))
                .map(String::as_str)
        };
        let Some(scope) = scope else { continue };
        let cat = rec["category"].as_str().unwrap();
        let name = rec["name"].as_str().unwrap();
        let flat = module_dest(&root, cat, scope, name);
        if rec["kind"] == "directory" {
            if flat.exists() && !fs::symlink_metadata(&flat)?.file_type().is_symlink() {
                fs::remove_file(&flat)?
            }
            let dest = flat.with_extension("");
            for (rel, data) in files {
                let p = dest.join(rel);
                fs::create_dir_all(p.parent().unwrap())?;
                fs::write(p, data)?;
            }
        } else {
            let dir = flat.with_extension("");
            if dir.is_dir() && !fs::symlink_metadata(&dir)?.file_type().is_symlink() {
                fs::remove_dir_all(dir)?
            }
            fs::create_dir_all(flat.parent().unwrap())?;
            fs::write(flat, &files[0].1)?;
        }
        restored.push(format!("{}:{}:{}", cat, scope, name));
    }
    let project = root.file_name().unwrap_or_default().to_string_lossy();
    for (i, p) in ps.iter().enumerate() {
        let doc = json!({"name":format!("{}_{}",project.to_lowercase(),p.to_lowercase()),"tree":{"$className":"DataModel","ReplicatedStorage":{"$path":"shared/src/ReplicatedStorage"},"ServerScriptService":{"$path":"shared/src/ServerScriptService","PlaceServices":{"$path":format!("places/{}/src/ServerScriptService/Services",p)},"Tests":{"$path":format!("tests/{}/server",p)}},"StarterPlayer":{"StarterPlayerScripts":{"$path":"shared/src/StarterPlayer/StarterPlayerScripts","PlaceControllers":{"$path":format!("places/{}/src/StarterPlayer/StarterPlayerScripts/Controllers",p)},"Tests":{"$path":format!("tests/{}/client",p)}}}}});
        json_put(&root.join(format!("{}.project.json", p)), &doc)?;
        if i == 0 {
            json_put(&root.join("default.project.json"), &doc)?
        }
    }
    if a.iter().any(|x| x == "plugins") {
        if let Ok(m) = fs::symlink_metadata(&plugins) {
            if m.file_type().is_symlink() || !m.is_dir() {
                bail!("plugins/ must be a regular directory")
            }
        }
        fs::create_dir_all(&plugins)?;
        if fs::read_dir(&plugins)?.next().is_none() {
            fs::write(plugins.join(".gitkeep"), "")?
        }
    }
    let manifest = sorted(
        json!({"schema":1,"gameplay":state["gameplay"],"places":ps,"services":state["services"],"controllers":state["controllers"],"assets":a,"harness":harness}),
    );
    json_put(&root.join("manifest.json"), &manifest)?;
    if harness {
        let args = [
            OsString::from("--project"),
            root.as_os_str().to_owned(),
            OsString::from("--from-state"),
        ];
        if !matches!(crate::setup::run(&args), Ok(0)) {
            bail!("project integration failed; keep the emitted files and manifest.json; do not rerun scaffold; retry integration with: harness setup --project {} --from-state",root.display())
        }
    } else {
        put(&root.join("AGENTS.md"),&format!("# Project\n\nGameplay loop: {}\n\nServices: {}\n\nControllers: {}\n\n## Places\n\n{}\n\n## Assets\n\n{}\n",state["gameplay"].as_str().unwrap(),state["services"].as_str().unwrap(),state["controllers"].as_str().unwrap(),ps.iter().map(|p|format!("- {}",p)).collect::<Vec<_>>().join("\n"),if a.is_empty(){"none".into()}else{a.join(", ")}),false)?
    }
    println!(
        "EMITTED|{}|places={}|assets={}|preserved={}",
        project,
        ps.join(","),
        if a.is_empty() {
            "none".into()
        } else {
            a.join(",")
        },
        if restored.is_empty() {
            "none".into()
        } else {
            restored.join(",")
        }
    );
    Ok(0)
}

fn git(root: &Path, args: &[&str], check: bool) -> Result<std::process::Output> {
    let o = Command::new("git").args(args).current_dir(root).output()?;
    if check && !o.status.success() {
        let s = if o.stderr.is_empty() {
            &o.stdout
        } else {
            &o.stderr
        };
        let s = String::from_utf8_lossy(s);
        bail!("{}", s.trim().chars().take(500).collect::<String>())
    }
    Ok(o)
}
fn git_text(root: &Path, args: &[&str]) -> Result<String> {
    let o = git(root, args, false)?;
    Ok(if o.status.success() {
        String::from_utf8_lossy(&o.stdout).trim().to_string()
    } else {
        String::new()
    })
}
fn configured(root: &Path, key: &str) -> Result<String> {
    git_text(root, &["config", "-f", ".gitmodules", "--get", key])
}
fn indexed(root: &Path) -> Result<bool> {
    Ok(
        git_text(root, &["ls-files", "--stage", "--", "rblx-harness"])?
            .lines()
            .any(|l| l.starts_with("160000 ") && l.ends_with("\trblx-harness")),
    )
}
fn registered(root: &Path) -> Result<bool> {
    Ok(
        configured(root, "submodule.rblx-harness.path")? == "rblx-harness"
            && configured(root, "submodule.rblx-harness.url")? == URL
            && indexed(root)?
            && git_text(root, &["ls-files", "--stage", "--", ".gitmodules"])?
                .lines()
                .any(|l| l.starts_with("100644 "))
            && git(root, &["diff", "--quiet", "--", ".gitmodules"], false)?
                .status
                .success(),
    )
}
fn valid(p: &Path) -> bool {
    [
        "Cargo.toml",
        "shared/CORE.md",
        "shared/skills/rblx-new-game/SKILL.md",
    ]
    .iter()
    .all(|x| p.join(x).is_file())
}
fn symlink(p: &Path) -> bool {
    fs::symlink_metadata(p)
        .map(|m| m.file_type().is_symlink())
        .unwrap_or(false)
}
fn exists(p: &Path) -> bool {
    fs::symlink_metadata(p).is_ok()
}
fn update(root: &Path) -> Result<()> {
    git(root, &["submodule", "sync", "--", "rblx-harness"], true)?;
    git(
        root,
        &[
            "submodule",
            "update",
            "--init",
            "--recursive",
            "--",
            "rblx-harness",
        ],
        true,
    )?;
    Ok(())
}
fn dependency(root: &Path, args: &[String]) -> Result<i32> {
    let command = args.first().map(String::as_str).unwrap_or("");
    let dest = root.join("rblx-harness");
    match command {
        "status" => {
            if registered(root)? && !symlink(&dest) && valid(&dest) {
                println!("dependency-status|READY|submodule");
                return Ok(0);
            }
            if !configured(root, "submodule.rblx-harness.path")?.is_empty()
                || !configured(root, "submodule.rblx-harness.url")?.is_empty()
                || indexed(root)?
                || exists(&dest)
                || exists(&root.join(".rblx-harness"))
            {
                println!("dependency-status|INVALID|submodule")
            } else {
                println!("dependency-status|ABSENT")
            }
            Ok(2)
        }
        "init" => {
            if !registered(root)? {
                bail!("rblx-harness is not registered as the required Git submodule")
            }
            if symlink(&dest) {
                bail!("rblx-harness submodule path must not be a symlink")
            }
            update(root)?;
            if !valid(&dest) {
                bail!("initialized submodule is invalid")
            }
            println!("dependency-init|READY|submodule");
            Ok(0)
        }
        "setup" => {
            if !args.iter().any(|x| x == "--yes") {
                println!("CONSENT_REQUIRED|rblx-harness adds Codex and Claude Code skills, four agents,rules, tools, templates, and selected shared assets.");
                return Ok(3);
            }
            if !root.is_dir() {
                bail!("project directory is absent: {}", root.display())
            }
            let top = git_text(root, &["rev-parse", "--show-toplevel"])?;
            if fs::canonicalize(top).ok() != fs::canonicalize(root).ok() {
                git(root, &["init"], true)?;
            }
            ignore(root)?;
            let marker = root.join(".roblox");
            if exists(&marker) && (symlink(&marker) || !marker.is_file()) {
                bail!(".roblox must be a regular file")
            }
            if !marker.exists() {
                fs::write(marker, "")?
            }
            let configured = !configured(root, "submodule.rblx-harness.path")?.is_empty()
                || !configured(root, "submodule.rblx-harness.url")?.is_empty();
            let mode = if configured || indexed(root)? {
                if !registered(root)? {
                    bail!(
                        "rblx-harness submodule must use path rblx-harness and URL {}",
                        URL
                    )
                }
                if symlink(&dest) {
                    bail!("rblx-harness submodule path must not be a symlink")
                }
                if valid(&dest) {
                    "submodule-ready"
                } else {
                    update(root)?;
                    if !valid(&dest) {
                        bail!("initialized rblx-harness submodule is invalid")
                    }
                    "submodule-initialized"
                }
            } else {
                if exists(&dest) {
                    bail!("rblx-harness exists but is not a registered Git submodule")
                }
                if exists(&root.join(".rblx-harness")) {
                    bail!("legacy hidden harness dependency exists; remove it before setup")
                }
                git(root, &["submodule", "add", "--", URL], true)?;
                if !registered(root)? {
                    bail!("rblx-harness Git submodule registration failed")
                }
                if !valid(&dest) {
                    bail!("installed rblx-harness submodule is invalid")
                }
                "submodule-installed"
            };
            println!("dependency-setup|READY|mode={}|path=rblx-harness", mode);
            Ok(0)
        }
        _ => bail!("unknown dependency command: {}", command),
    }
}
fn existing_places(root: &Path) -> Vec<String> {
    let mut v: Vec<_> = fs::read_dir(root.join("places"))
        .ok()
        .into_iter()
        .flatten()
        .flatten()
        .filter(|e| e.path().is_dir())
        .map(|e| e.file_name().to_string_lossy().to_string())
        .collect();
    v.sort();
    v
}
fn refused_name(n: &str) -> i32 {
    println!("create_boilerplate: REFUSED\n\n{}|GATE2|name is not one safe path component|use letters and digits, beginning with a letter",n);
    2
}
fn refused_place(root: &Path, p: &str) -> i32 {
    let v = existing_places(root);
    println!("create_boilerplate: REFUSED\n\n{}|GATE2|places/{}/ absent|existing: {} - the scaffold creates place trees",p,p,if v.is_empty(){"none".into()}else{v.join(", ")});
    2
}
fn relative(from: &Path, to: &Path) -> PathBuf {
    let a: Vec<_> = from.components().collect();
    let b: Vec<_> = to.components().collect();
    let n = a.iter().zip(&b).take_while(|(a, b)| a == b).count();
    let mut p = PathBuf::new();
    for _ in n..a.len() {
        p.push("..")
    }
    for c in &b[n..] {
        p.push(c.as_os_str())
    }
    p
}
fn display_path(root: &Path, p: &Path) -> String {
    let rel = p
        .strip_prefix(root)
        .unwrap_or(p)
        .to_string_lossy()
        .replace('\\', "/");
    let mut parts: Vec<_> = rel
        .split('/')
        .filter(|s| !s.is_empty() && *s != ".")
        .collect();
    if parts.first() == Some(&"places") && parts.len() >= 2 {
        parts.remove(0);
    }
    if parts.len() < 2 {
        return parts.join("/");
    }
    let dirs = &parts[1..parts.len() - 1];
    let omitted = dirs.len().saturating_sub(2);
    let mut out = vec![parts[0].to_string()];
    if omitted > 0 {
        out.push(".".repeat(omitted));
    }
    out.extend(dirs[omitted..].iter().map(|x| x.to_string()));
    out.push(parts.last().unwrap().to_string());
    out.join("/")
}

fn test_module(root: &Path, spec: &str, place: Option<&str>, side: Option<&str>) -> Result<i32> {
    let re = regex::Regex::new(r"^(Fix|Diagnose|Measure|LIVE)\.[A-Za-z0-9]+$")?;
    if !re.is_match(spec) {
        println!("create_boilerplate: REFUSED\n\n{}|DEBUG2|test name is <Mode>.<Name>|Fix.Shop, Diagnose.Pets, LIVE.Shop",spec);
        return Ok(2);
    }
    let Some(place) = place else {
        println!("create_boilerplate: REFUSED\n\n{}|DEBUG2|--place required|tests live in tests/<Place>/",spec);
        return Ok(2);
    };
    let pr = regex::Regex::new(r"^[A-Za-z][A-Za-z0-9_-]*$")?;
    if !pr.is_match(place) || !matches!(side, None | Some("server") | Some("client")) {
        return Ok(refused_name(place));
    }
    let side = side.unwrap_or("server");
    let dest = root.join(format!("tests/{}/{}/{}.{}.luau", place, side, spec, side));
    if dest.exists() {
        println!("create_boilerplate: REFUSED|test exists; preserve source and edit explicitly");
        return Ok(2);
    }
    let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("shared/test_support");
    let wanted = json!({"$path":relative(&fs::canonicalize(root)?,&source).to_string_lossy().replace('\\',"/")});
    let mut mappings = Vec::new();
    for name in [
        format!("{}.project.json", place),
        "default.project.json".into(),
    ] {
        let p = root.join(name);
        if !p.is_file() {
            continue;
        }
        let mut doc: Value = serde_json::from_slice(&fs::read(&p)?)?;
        let tests = if side == "server" {
            &mut doc["tree"]["ServerScriptService"]["Tests"]
        } else {
            &mut doc["tree"]["StarterPlayer"]["StarterPlayerScripts"]["Tests"]
        };
        if tests["$path"] != format!("tests/{}/{}", place, side) {
            continue;
        }
        if !tests["TestSupport"].is_null() && tests["TestSupport"] != wanted {
            println!("create_boilerplate: REFUSED|TestSupport mapping belongs to another source");
            return Ok(2);
        }
        tests["TestSupport"] = wanted.clone();
        mappings.push((p, doc));
    }
    if mappings.is_empty() {
        println!(
            "create_boilerplate: REFUSED|map tests/{}/{} through Argon before authoring",
            place, side
        );
        return Ok(2);
    }
    for (p, v) in mappings {
        json_put(&p, &v)?
    }
    let live = spec.starts_with("LIVE.");
    let mut text = frame(BOILER, "TEST_FRAME");
    if live {
        text = text
            .replace(
                "local RunService = game:GetService(\"RunService\")",
                "local STAGING_PLACE_ID = 0",
            )
            .replace(
                "not RunService:IsStudio()",
                "game.PlaceId ~= STAGING_PLACE_ID or STAGING_PLACE_ID == 0",
            );
    }
    text=text.replace("{what}","state one question and its stopping condition").replace("{how}",if live{"Set the staging PlaceId, RunId and confirmed Ready before an authorized staging run."}else{"In stopped Edit set RunId and confirmed Ready, enable, then MCP Play; collect with studio output."}).replace("{id}",spec).replace("{{","{").replace("}}","}");
    put(&dest, &text, true)?;
    println!(
        "create_boilerplate: EMITTED\n\n{}",
        display_path(root, &dest)
    );
    Ok(0)
}
fn module(root: &Path, args: &[String]) -> Result<i32> {
    let mut place = None;
    let mut side = None;
    let mut test = None;
    let mut expand = None;
    let mut pos = Vec::new();
    let mut i = 0;
    while i < args.len() {
        if i + 1 < args.len() {
            let target = match args[i].as_str() {
                "--place" => Some(&mut place),
                "--side" => Some(&mut side),
                "--test" => Some(&mut test),
                "--expand" => Some(&mut expand),
                _ => None,
            };
            if let Some(target) = target {
                *target = Some(args[i + 1].as_str());
                i += 2;
                continue;
            }
        }
        pos.push(args[i].as_str());
        i += 1
    }
    if let Some(t) = test {
        return test_module(root, t, place, side);
    }
    if let Some(name) = expand {
        if !safe(name) {
            return Ok(refused_name(name));
        }
        if let Some(p) = place {
            if !existing_places(root).iter().any(|x| x == p) {
                return Ok(refused_place(root, p));
            }
        }
        let prefix = place
            .map(|p| format!("places/{}/src", p))
            .unwrap_or("shared/src".into());
        for dir in [
            "ServerScriptService/Services",
            "StarterPlayer/StarterPlayerScripts/Controllers",
        ] {
            let flat = root.join(&prefix).join(dir).join(format!("{}.luau", name));
            if flat.exists() {
                let folder = flat.with_extension("");
                if folder.exists() {
                    println!("create_boilerplate: REFUSED\n\n{}|GATE2|folder form already exists|nothing moved",name);
                    return Ok(2);
                }
                fs::create_dir_all(&folder)?;
                let target = folder.join("init.luau");
                fs::rename(&flat, &target)?;
                println!(
                    "create_boilerplate: EXPANDED\n\n{} -> {}",
                    display_path(root, &flat),
                    display_path(root, &target)
                );
                return Ok(0);
            }
        }
        println!(
            "create_boilerplate: REFUSED\n\n{}|GATE2|no flat module found|emit it first",
            name
        );
        return Ok(2);
    }
    if pos.len() != 2 {
        println!("{}", MODULE_HELP);
        return Ok(2);
    }
    let (kind, name) = (pos[0], pos[1]);
    let (path, frame_name) = match kind {
        "service" => ("ServerScriptService/Services", "FRAME"),
        "controller" => (
            "StarterPlayer/StarterPlayerScripts/Controllers",
            "CONTROLLER_FRAME",
        ),
        "gui" => (
            "StarterPlayer/StarterPlayerScripts/Controllers/Gui",
            "GUI_FRAME",
        ),
        "update" => ("ServerScriptService/Services/Updates", "UPDATE_FRAME"),
        "data-module" => ("ReplicatedStorage/Data", "DATA_FRAME"),
        "tool-handler" => ("ServerScriptService/Services", "TOOL_FRAME"),
        _ => {
            println!("create_boilerplate: REFUSED\n\n{}|BC4|unknown kind|service controller gui update data-module tool-handler",kind);
            return Ok(2);
        }
    };
    if !safe(name) {
        return Ok(refused_name(name));
    }
    for suffix in ["service", "controller"] {
        if name.to_lowercase().ends_with(suffix) {
            let original = &name[name.len() - suffix.len()..];
            let bare = &name[..name.len() - suffix.len()];
            println!(
                "create_boilerplate: ADVISORY\n{}|WRIT10|{} suffix|prefer {}",
                name,
                original,
                if bare.is_empty() { "the feature" } else { bare }
            );
            break;
        }
    }
    if !name.as_bytes()[0].is_ascii_uppercase() {
        println!("create_boilerplate: ADVISORY\n{}|WRIT10|not a PascalCase feature noun|prefer a PascalCase feature noun",name)
    }
    let path = if let Some(p) = place {
        if ["data-module", "update"].contains(&kind) {
            println!("create_boilerplate: REFUSED\n\n{}|GATE2|{} has no per-place mount|only Services and Controllers mount per place - emit without --place",name,kind);
            return Ok(2);
        }
        if !existing_places(root).iter().any(|x| x == p) {
            return Ok(refused_place(root, p));
        }
        format!(
            "places/{}/src/{}",
            p,
            if kind == "gui" {
                "StarterPlayer/StarterPlayerScripts/Gui"
            } else {
                path
            }
        )
    } else {
        format!("shared/src/{}", path)
    };
    let dest = root.join(path).join(format!("{}.luau", name));
    if dest.exists() {
        println!("create_boilerplate: REFUSED\n\n{}|BC4|target exists|edit the existing file - the emitter never overwrites",display_path(root,&dest));
        return Ok(2);
    }
    let mut text = frame(BOILER, frame_name);
    if kind == "update" {
        text = text
            .replace(
                "{date}",
                &chrono::Local::now().format("%Y-%m-%d").to_string(),
            )
            .replace("{{", "{")
            .replace("}}", "}");
    }
    put(&dest, &text, true)?;
    println!(
        "create_boilerplate: EMITTED\n\n{}",
        display_path(root, &dest)
    );
    Ok(0)
}
pub fn run(args: &[OsString]) -> Result<i32> {
    let family = args.first().and_then(|s| s.to_str()).unwrap_or("");
    let mut root = root()?;
    let mut rest = Vec::new();
    let mut i = 1;
    while i < args.len() {
        if args[i] == "--root" {
            i += 1;
            root = PathBuf::from(
                args.get(i)
                    .ok_or_else(|| anyhow!("--root requires a value"))?,
            );
        } else {
            rest.push(args[i].to_string_lossy().to_string());
        }
        i += 1
    }
    let result = match family {
        "project" => project(&root, &rest),
        "dependency" => dependency(&root, &rest),
        "module" => module(&root, &rest),
        _ => bail!("unknown scaffold family: {}", family),
    };
    match result {
        Ok(code) => Ok(code),
        Err(e) => {
            eprintln!(
                "{}: ERROR {:#}",
                match family {
                    "project" => "scaffold",
                    "dependency" => "dependency",
                    _ => "create_boilerplate",
                },
                e
            );
            Ok(2)
        }
    }
}
