use crate::gates;
use anyhow::{Context, Result};
use serde_json::Value;
use std::{
    collections::{HashMap, HashSet},
    ffi::OsString,
    path::{Path, PathBuf},
    process::Command,
};

#[derive(Clone)]
struct Finding {
    path: String,
    line: i64,
    col: i64,
    id: String,
    subject: String,
    remedy: String,
}
fn disposition(id: &str) -> u8 {
    let id = id.trim_end_matches('!');
    if id == "TYPE10" {
        3
    } else if ["BC3", "TYPE3", "WRIT12", "WRIT14", "WRIT15", "WRIT22"].contains(&id) {
        1
    } else if [
        "BC1", "BC7", "DATA1", "DATA5", "DATA8", "DATA17", "DATA21", "DATA23", "DATA29", "DATA30",
        "DATA31", "DATA32", "DATA33", "DATA35", "DATA36", "DATA37", "DEBUG2", "DEBUG11", "DES2",
        "GATE1", "GATE2", "GATE3", "GATE4", "GATE5", "GATE6", "GATE7", "OPT8", "OPT12", "OPT15",
        "OPT20", "OPT16", "OPT17", "OUT1", "REV4", "REV10", "TYPE1", "TYPE7", "TYPE8", "TYPE9",
        "WRIT8", "WRIT18", "WRIT23", "WRIT25", "WRIT29", "WRIT30", "WRIT31", "WRIT33",
    ]
    .contains(&id)
    {
        0
    } else {
        2
    }
}
fn relative(path: &Path, root: &Path) -> PathBuf {
    let p = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_default().join(path)
    };
    let r = if root.is_absolute() {
        root.to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_default().join(root)
    };
    let a: Vec<_> = p.components().collect();
    let b: Vec<_> = r.components().collect();
    let mut n = 0;
    while n < a.len() && n < b.len() && a[n] == b[n] {
        n += 1;
    }
    let mut out = PathBuf::new();
    for _ in n..b.len() {
        out.push("..");
    }
    for c in &a[n..] {
        out.push(c.as_os_str());
    }
    out
}
fn elide(path: &Path, root: &Path) -> String {
    let rel = relative(path, root).to_string_lossy().replace('\\', "/");
    let mut p: Vec<_> = rel
        .split('/')
        .filter(|s| !s.is_empty() && *s != ".")
        .collect();
    if p.first() == Some(&"places") && p.len() >= 2 {
        p.remove(0);
    }
    if p.len() <= 4 {
        return p.join("/");
    }
    format!(
        "{}/{}/{}/{}/{}",
        p[0],
        ".".repeat(p.len() - 4),
        p[p.len() - 3],
        p[p.len() - 2],
        p[p.len() - 1]
    )
}
fn render(tool: &str, findings: &[Finding], root: &Path, blocked: bool) -> String {
    if findings.is_empty() {
        return String::new();
    }
    let mut out = if blocked {
        format!("{tool}: BLOCKED\n\n")
    } else {
        String::new()
    };
    let mut paths = Vec::new();
    for f in findings {
        if !paths.contains(&f.path) {
            paths.push(f.path.clone());
        }
    }
    for path in paths {
        out.push_str(&format!("{}:\n\n", elide(Path::new(&path), root)));
        let mut rows: Vec<_> = findings.iter().filter(|f| f.path == path).collect();
        rows.sort_by(|a, b| (a.line, a.col, &a.id).cmp(&(b.line, b.col, &b.id)));
        for f in rows {
            out.push_str(&format!(
                "{}|{}|{}|{}|{}\n",
                f.line, f.col, f.id, f.subject, f.remedy
            ));
        }
        out.push('\n');
    }
    out.pop();
    out
}
fn source_suffix(p: &Path) -> bool {
    matches!(p.extension().and_then(|x| x.to_str()), Some("lua" | "luau"))
}
fn collect(path: &Path) -> Vec<PathBuf> {
    if path.is_symlink() {
        return vec![];
    }
    if path.is_file() {
        return if source_suffix(path) {
            vec![path.to_path_buf()]
        } else {
            vec![]
        };
    }
    if !path.is_dir() {
        return vec![];
    }
    walkdir::WalkDir::new(path)
        .follow_links(false)
        .sort_by_file_name()
        .into_iter()
        .filter_map(Result::ok)
        .filter(|e| e.file_type().is_file() && source_suffix(e.path()))
        .map(|e| e.into_path())
        .collect()
}
fn config(tool: &str, now: Option<&str>) -> Result<PathBuf> {
    let cache = gates::cache();
    std::fs::create_dir_all(&cache)?;
    let globals = if cache.join("api_globals.luau").exists() {
        "require(\"./api_globals\")"
    } else {
        "{}"
    };
    let extra = if tool == "style_assess" {
        format!("\t\t\truleconfigs = {{\n\t\t\t\tWRIT29 = {{ options = {{ except = {{ \"GetService\", \"FindFirstChild\", \"FindFirstChildOfClass\", \"FindFirstChildWhichIsA\", \"FindFirstAncestor\", \"FindFirstDescendant\" }} }} }},\n{}\t\t\t}},\n", now.map(|n| format!("\t\t\t\tDES5 = {{ options = {{ now = {} }} }},\n",n)).unwrap_or_default())
    } else if tool == "deny_scan" {
        [
            "BC3", "WRIT18", "DATA29", "OPT11", "WRIT11", "BC1", "OPT12", "BC7", "OPT15", "OPT20",
            "DATA38",
        ]
        .iter()
        .map(|id| format!("\t\t\t\t{id} = {{ options = deny.{id} }},\n"))
        .collect::<String>()
        .pipe(|s| format!("\t\t\truleconfigs = {{\n{s}\t\t\t}},\n"))
    } else {
        String::new()
    };
    let prefix = if tool == "deny_scan" {
        let mut p = relative(
            &gates::harness_root().join("tools/deny_scan/deny_table"),
            &cache,
        )
        .to_string_lossy()
        .replace('\\', "/");
        if !p.starts_with('.') {
            p = format!("./{p}");
        }
        format!("local deny = require(\"{p}\")\n")
    } else {
        String::new()
    };
    let path = cache.join(format!("{tool}.config.luau"));
    std::fs::write(&path, format!("{prefix}return {{\n\tlute = {{\n\t\tlint = {{\n\t\t\tglobals = {globals},\n{extra}\t\t}},\n\t}},\n}}\n"))?;
    Ok(path)
}
trait Pipe: Sized {
    fn pipe<T>(self, f: impl FnOnce(Self) -> T) -> T {
        f(self)
    }
}
impl<T> Pipe for T {}
fn lint(
    tool: &str,
    rules: &Path,
    cfg: &Path,
    files: &[PathBuf],
    autofix: bool,
) -> Result<std::result::Result<Vec<Finding>, String>> {
    let mut cmd = Command::new(gates::bundled_tool("lute"));
    cmd.args(["lint", "--no-default-lints", "-r"])
        .arg(rules)
        .arg("-c")
        .arg(cfg)
        .arg("-j");
    if autofix {
        cmd.arg("--auto-fix");
    }
    let o = cmd.args(files).output()?;
    let stdout = String::from_utf8_lossy(&o.stdout);
    let stderr = String::from_utf8_lossy(&o.stderr);
    let brace = stdout.find('{');
    if !o.status.success() || !stdout[..brace.unwrap_or(0)].trim().is_empty() {
        return Ok(Err(if stderr.is_empty() {
            stdout.to_string()
        } else {
            stderr.to_string()
        }));
    }
    let v: Value = match serde_json::from_str(&stdout[brace.unwrap_or(0)..]) {
        Ok(v) => v,
        Err(_) => return Ok(Err(format!("{stdout}{stderr}"))),
    };
    let known: HashSet<String> = std::fs::read_dir(rules)?
        .filter_map(Result::ok)
        .filter_map(|e| {
            let p = e.path();
            if p.extension()?.to_str()? == "luau" {
                Some(p.file_stem()?.to_string_lossy().into_owned())
            } else {
                None
            }
        })
        .collect();
    let mut findings = Vec::new();
    for doc in v["items"].as_array().into_iter().flatten() {
        for item in doc["items"].as_array().into_iter().flatten() {
            let mut id = item["code"].as_str().unwrap_or("void").to_string();
            let msg = item["message"].as_str().unwrap_or("");
            let (subject, remedy) = msg.split_once('|').unwrap_or((msg, ""));
            let mut subject = if subject.is_empty() { "void" } else { subject }.to_string();
            let mut remedy = if remedy.is_empty() { "void" } else { remedy }.to_string();
            if !known.contains(&id) {
                subject = format!(
                    "{id}: {}",
                    if subject == "void" {
                        "source diagnostic"
                    } else {
                        &subject
                    }
                );
                remedy = "fix the source syntax or required checker".into();
                id = "GATE4".into();
            }
            findings.push(Finding {
                path: doc["uri"].as_str().unwrap_or("").into(),
                line: item["range"]["start"]["line"].as_i64().unwrap_or(0) + 1,
                col: item["range"]["start"]["character"].as_i64().unwrap_or(0) + 1,
                id,
                subject,
                remedy,
            });
        }
    }
    let _ = tool;
    Ok(Ok(findings))
}
fn report(tool: &str, root: &Path, findings: Vec<Finding>, open: bool) -> i32 {
    let mut grouped: [Vec<Finding>; 4] = Default::default();
    for f in findings {
        grouped[disposition(&f.id) as usize].push(f);
    }
    if tool == "replication_audit" || open {
        let infra: Vec<_> = grouped[..3]
            .iter()
            .flatten()
            .filter(|f| f.id == "GATE4")
            .cloned()
            .collect();
        if !infra.is_empty() {
            eprint!("{}", render(tool, &infra, root, true));
            return 2;
        }
    }
    if open {
        let all: Vec<_> = grouped[..3].iter().flatten().cloned().collect();
        if !all.is_empty() {
            print!("{tool}: NOTED\n\n{}", render(tool, &all, root, false));
        }
        return 0;
    }
    if !grouped[2].is_empty() {
        print!(
            "{tool}: NOTED\n\n{}",
            render(tool, &grouped[2], root, false)
        );
    }
    let blocking: Vec<_> = grouped[..2].iter().flatten().cloned().collect();
    if !blocking.is_empty() {
        eprint!("{}", render(tool, &blocking, root, true));
        2
    } else {
        0
    }
}
fn scan(name: &str, root: &Path, files: &[PathBuf]) -> Result<i32> {
    let tool = match name {
        "correctness" => "deny_scan",
        "replication" => "replication_audit",
        "style" => "style_assess",
        _ => "perf_audit",
    };
    let lute = gates::bundled_tool("lute");
    if !lute.exists() {
        if name == "correctness" {
            println!("Install the harness toolchain, verify it, and retry");
        } else {
            println!("{tool}: BLOCKED (ENV)\n\nENV|lute-absent|install the harness toolchain");
        }
        return Ok(3);
    }
    let base = gates::harness_root().join("tools").join(tool);
    if name == "correctness" {
        let o = Command::new(&lute)
            .arg("run")
            .arg(base.join("check_table.luau"))
            .output()?;
        if !o.status.success() || !o.stdout.starts_with(b"ok ") {
            eprintln!("Fix {} → retry.", base.join("deny_table.luau").display());
            return Ok(2);
        }
    }
    let filtered: Vec<_> = files
        .iter()
        .filter(|p| name != "style" || !p.components().any(|c| c.as_os_str() == "tests"))
        .cloned()
        .collect();
    if filtered.is_empty() {
        return Ok(0);
    }
    if name == "style" && !gates::cache().join("api_globals.luau").exists() {
        eprintln!("style_assess: BLOCKED\n\n0|0|GATE4|required API globals unavailable for WRIT25 WRIT29 WRIT30 WRIT23 WRIT31|run harness api --emit-globals, then retry");
        return Ok(3);
    }
    let cfg = config(tool, None)?;
    let findings = match lint(tool, &base.join("rules"), &cfg, &filtered, false)? {
        Ok(f) => f,
        Err(e) => {
            if name == "correctness" {
                eprintln!(
                    "deny_scan: BLOCKED\n\n0|0|GATE4|required checker failed|{}",
                    e.trim()
                        .replace('|', "/")
                        .chars()
                        .take(500)
                        .collect::<String>()
                );
            } else {
                eprintln!(
                    "{tool}: BLOCKED\n\nlint output unparseable: {}",
                    e.chars().take(200).collect::<String>()
                );
            }
            return Ok(2);
        }
    };
    if name == "correctness" && !gates::cache().join("api_globals.luau").exists() {
        eprintln!("Generate API globals, verify them, and retry: harness api --emit-globals");
        return Ok(3);
    }
    let mut findings = findings;
    if name == "style" {
        match reuse(root, &filtered) {
            Ok(f) => findings.extend(f),
            Err(e) => {
                eprintln!(
                    "style_assess: BLOCKED\n\nGATE4|required reuse check failed|{}",
                    e.to_string().chars().take(200).collect::<String>()
                );
                return Ok(2);
            }
        }
    }
    Ok(report(tool, root, findings, name == "performance"))
}
fn scope(path: &Path, root: &Path) -> Option<(String, String)> {
    let p = relative(path, root);
    let x: Vec<_> = p.iter().map(|x| x.to_string_lossy().into_owned()).collect();
    let (place, parts) = if x.len() > 2 && x[0] == "shared" && x[1] == "src" {
        ("shared".to_string(), &x[2..])
    } else if x.len() > 3 && x[0] == "places" && x[2] == "src" {
        (x[1].clone(), &x[3..])
    } else {
        return None;
    };
    let side = match parts.first()?.as_str() {
        "ServerScriptService" | "ServerStorage" => "server",
        "StarterPlayer" | "StarterGui" | "ReplicatedFirst" => "client",
        "ReplicatedStorage" if parts.get(1).map(String::as_str) == Some("Packages") => "package",
        _ => return None,
    };
    Some((place, side.into()))
}
fn reuse(root: &Path, selected: &[PathBuf]) -> Result<Vec<Finding>> {
    reuse_filtered(root, selected, &[])
}
fn reuse_filtered(
    root: &Path,
    selected: &[PathBuf],
    ignores: &[globset::GlobMatcher],
) -> Result<Vec<Finding>> {
    let scopes: Vec<_> = selected.iter().filter_map(|p| scope(p, root)).collect();
    if scopes.is_empty() {
        return Ok(vec![]);
    }
    let mut candidates = collect(&root.join("shared/src"));
    candidates.extend(collect(&root.join("places")));
    candidates.extend_from_slice(selected);
    candidates.sort();
    candidates.dedup();
    candidates.retain(|p| {
        !is_ignored(p, root, ignores)
            && !p.components().any(|c| c.as_os_str() == "tests")
            && scope(p, root).is_some_and(|s| {
                scopes.iter().any(|(place, side)| {
                    (s.0 == *place || s.0 == "shared")
                        && (s.1 == *side
                            || (side == "server" || side == "client") && s.1 == "package")
                })
            })
    });
    candidates.sort_by_key(|p| {
        let s = scope(p, root).unwrap();
        (
            s.1 != "package",
            s.0 != "shared",
            selected.contains(p),
            p.clone(),
        )
    });
    let o = Command::new(gates::bundled_tool("lute"))
        .arg("run")
        .arg(gates::harness_root().join("tools/style_assess/reuse.luau"))
        .args(&candidates)
        .output()?;
    if !o.status.success() {
        anyhow::bail!(
            "{}",
            String::from_utf8_lossy(if o.stderr.is_empty() {
                &o.stdout
            } else {
                &o.stderr
            })
        );
    }
    let mut groups: HashMap<String, Vec<(PathBuf, i64, String, String)>> = HashMap::new();
    let mut findings = Vec::new();
    let output = String::from_utf8_lossy(&o.stdout);
    for row in output.lines() {
        let parts: Vec<_> = row.split('\t').collect();
        if parts.len() != 4 {
            anyhow::bail!("invalid reuse output: {row}");
        }
        let idx: usize = parts[0].parse()?;
        let line: i64 = parts[1].parse()?;
        let col: i64 = parts[2].parse()?;
        let path = candidates
            .get(idx.checked_sub(1).context("invalid index")?)
            .context("invalid index")?;
        let (place, side) = scope(path, root).context("invalid scope")?;
        let owners = groups.entry(parts[3].into()).or_default();
        if let Some(owner) = owners.iter().find(|(_, _, p, s)| {
            (p == "shared" || *p == place)
                && (*s == side || (side == "server" || side == "client") && s == "package")
        }) {
            if selected.contains(path) && side != "package" {
                findings.push(Finding {
                    path: path.to_string_lossy().into_owned(),
                    line,
                    col,
                    id: "WRIT20".into(),
                    subject: "duplicate function".into(),
                    remedy: format!(
                        "reuse {}:{}; check state and API ownership",
                        relative(&owner.0, root).display(),
                        owner.1
                    ),
                });
            }
        }
        owners.push((path.clone(), line, place, side));
    }
    Ok(findings)
}
fn is_ignored(path: &Path, root: &Path, ignores: &[globset::GlobMatcher]) -> bool {
    let rel = relative(path, root).to_string_lossy().replace('\\', "/");
    ignores
        .iter()
        .any(|g| g.is_match(&rel) || g.is_match(format!("/{rel}")))
}
pub fn run(args: &[OsString]) -> Result<i32> {
    let Some(action) = args.first().and_then(|s| s.to_str()) else {
        anyhow::bail!("missing check action")
    };
    if action == "project" {
        return crate::project_gate::run(&args[1..]);
    }
    if action != "source" {
        anyhow::bail!("unknown check action: {action}");
    }
    let root = std::env::current_dir()?.canonicalize()?;
    let mut only = "correctness,replication,style".to_string();
    let mut paths = Vec::new();
    let mut i = 1;
    while i < args.len() {
        let a = &args[i];
        if a == "--only" {
            i += 1;
            only = args
                .get(i)
                .context("--only needs a value")?
                .to_string_lossy()
                .into_owned();
        } else if let Some(v) = a.to_str().and_then(|s| s.strip_prefix("--only=")) {
            only = v.into();
        } else {
            paths.push(PathBuf::from(a));
        }
        i += 1;
    }
    if paths.is_empty() {
        anyhow::bail!("the following arguments are required: paths");
    }
    let mut selected = Vec::new();
    for n in only.split(',') {
        if !["correctness", "replication", "style", "performance"].contains(&n) {
            anyhow::bail!("--only accepts: correctness,replication,style,performance");
        }
        if !selected.contains(&n) {
            selected.push(n);
        }
    }
    let mut files = Vec::new();
    for p in paths {
        let p = if p.is_absolute() { p } else { root.join(p) };
        let mut normalized = PathBuf::new();
        for c in p.components() {
            use std::path::Component;
            match c {
                Component::ParentDir => {
                    normalized.pop();
                }
                Component::CurDir => {}
                _ => normalized.push(c.as_os_str()),
            }
        }
        if !normalized.exists() {
            anyhow::bail!("source path is absent: {}", p.display());
        }
        let resolved = normalized.canonicalize()?;
        if !resolved.starts_with(&root) {
            anyhow::bail!("source path is outside --root: {}", p.display());
        }
        if normalized
            .ancestors()
            .take_while(|path| {
                std::fs::canonicalize(path).is_ok_and(|resolved| resolved.starts_with(&root))
            })
            .any(Path::is_symlink)
        {
            continue;
        }
        files.extend(collect(&normalized));
    }
    files.sort();
    files.dedup();
    if files.is_empty() {
        anyhow::bail!("no owned Luau source files in the selected paths");
    }
    let mut status = 0;
    for n in selected {
        let code = scan(n, &root, &files)?;
        println!("check|{n}|exit={code}");
        if code == 3 {
            status = 3;
        } else if code != 0 && status != 3 {
            status = 2;
        }
    }
    Ok(status)
}

fn replace_data(replacements: &[(PathBuf, PathBuf)]) -> Result<()> {
    let parent = replacements[0]
        .1
        .parent()
        .context("missing destination directory")?;
    let stage = tempfile::Builder::new()
        .prefix(".data_write_")
        .tempdir_in(parent)?;
    let mut prepared = Vec::new();
    for (i, (src, dst)) in replacements.iter().enumerate() {
        let new = stage.path().join(format!("{i}.new"));
        std::fs::copy(src, &new)?;
        let backup = if let Ok(meta) = std::fs::symlink_metadata(dst) {
            let backup = stage.path().join(format!("{i}.original"));
            if meta.file_type().is_symlink() {
                #[cfg(unix)]
                std::os::unix::fs::symlink(std::fs::read_link(dst)?, &backup)?;
                #[cfg(not(unix))]
                anyhow::bail!("cannot safely back up a symlink");
            } else {
                std::fs::copy(dst, &backup)?;
            }
            Some(backup)
        } else {
            None
        };
        prepared.push((new, dst.clone(), backup));
    }
    let mut changed: Vec<(PathBuf, Option<PathBuf>)> = Vec::new();
    for (new, dst, backup) in prepared {
        if let Err(error) = std::fs::rename(&new, &dst) {
            let mut failed = Vec::new();
            for (dest, original) in changed.iter().rev() {
                let r = if let Some(original) = original {
                    std::fs::rename(original, dest)
                } else {
                    std::fs::remove_file(dest)
                };
                if r.is_err() {
                    failed.push(dest.display().to_string());
                }
            }
            if !failed.is_empty() {
                let retained = stage.keep();
                anyhow::bail!(
                    "recovery failed for {}; retained backups: {}",
                    failed.join(", "),
                    retained.display()
                );
            }
            anyhow::bail!("replacement failed; original files restored: {error}");
        }
        changed.push((dst, backup));
    }
    Ok(())
}

pub fn run_data(args: &[OsString]) -> Result<i32> {
    let mut root = std::env::current_dir()?;
    let mut key = None;
    let mut default = None;
    let mut dev = None;
    let mut i = 0;
    while i < args.len() {
        if (args[i] == "--root" || args[i] == "--default" || args[i] == "--dev")
            && i + 1 < args.len()
        {
            if args[i] == "--root" {
                root = PathBuf::from(&args[i + 1]);
            } else if args[i] == "--default" {
                default = Some(args[i + 1].clone());
            } else {
                dev = Some(args[i + 1].clone());
            }
            i += 2;
        } else {
            if key.is_none() {
                key = Some(args[i].clone());
            }
            i += 1;
        }
    }
    let (Some(key), Some(default), Some(dev)) = (key, default, dev) else {
        println!("data_write <Key.Path> --default <lit> --dev <lit> [--root DIR]");
        return Ok(2);
    };
    let lute = gates::bundled_tool("lute");
    if !lute.exists() {
        println!(
            "data_write: REFUSED\n\n0|0|GATE4|bundled lute absent|install the harness toolchain"
        );
        return Ok(3);
    }
    let services = root.join("shared/src/ServerScriptService/Services");
    let dir = services.join("PlayerData");
    let dst_default = dir.join("Default.luau");
    let dst_dev = dir.join("Development.luau");
    std::fs::create_dir_all(&dir)?;
    let tmp = tempfile::Builder::new().prefix("data_write_").tempdir()?;
    let out_default = tmp.path().join("Default.luau");
    let out_dev = tmp.path().join("Development.luau");
    let core = gates::harness_root().join("tools/data_write/data_write_core.luau");
    let input_default = if dst_default.exists() {
        dst_default.as_os_str()
    } else {
        std::ffi::OsStr::new("NEW")
    };
    let input_dev = if dst_dev.exists() {
        dst_dev.as_os_str()
    } else {
        std::ffi::OsStr::new("NEW")
    };
    let result = Command::new(&lute)
        .arg("run")
        .arg(core)
        .arg(&key)
        .arg(&default)
        .arg(&dev)
        .arg(input_default)
        .arg(input_dev)
        .arg(&out_default)
        .arg(&out_dev)
        .output()?;
    if !result.status.success() || !result.stdout.starts_with(b"OK") {
        println!("data_write: REFUSED\n\n{}:\n", elide(&dst_default, &root));
        let body = format!(
            "{}{}",
            String::from_utf8_lossy(&result.stdout),
            String::from_utf8_lossy(&result.stderr)
        );
        for line in body.trim().lines() {
            if !line.is_empty() && line != "OK" {
                println!("{line}");
            }
        }
        return Ok(2);
    }
    if dst_default.exists() {
        let shape = gates::harness_root().join("tools/data_shape_diff/data_shape_diff.luau");
        let result = Command::new(&lute)
            .arg("run")
            .arg(shape)
            .arg(&dst_default)
            .arg(&out_default)
            .arg("--migrations")
            .arg(&services)
            .output()?;
        if !result.status.success() || !result.stdout.starts_with(b"ALLOW") {
            println!("data_write: REFUSED\n\n{}:\n", elide(&dst_default, &root));
            let output = String::from_utf8_lossy(&result.stdout);
            let lines: Vec<_> = output.trim().lines().skip(1).collect();
            let lines = if lines.is_empty() {
                vec!["shape diff required checker failed [GATE4]"]
            } else {
                lines
            };
            let re = regex::Regex::new(r"\[(GATE[1-7]|DATA\d+|TYPE\d+)\]")?;
            for line in lines {
                let rule = re
                    .captures(line)
                    .and_then(|c| c.get(1))
                    .map(|m| m.as_str())
                    .unwrap_or("GATE4");
                println!("0|0|{rule}|{}|see data_shape_diff", line.replace('|', "/"));
            }
            return Ok(2);
        }
    }
    let mut replacements = vec![(out_default, dst_default.clone())];
    let typed = tmp.path().join("Typed.luau");
    if typed.exists() {
        replacements.push((typed, dir.join("Typed.luau")));
    }
    replacements.push((out_dev, dst_dev.clone()));
    if let Err(e) = replace_data(&replacements) {
        println!(
            "data_write: FAILED\n\n0|0|GATE3|{}|{e}",
            key.to_string_lossy()
        );
        return Ok(2);
    }
    println!(
        "data_write: WRITTEN\n\n{}:\n\n{}|{}\n\n{}:\n\n{}|{}",
        elide(&dst_default, &root),
        key.to_string_lossy(),
        default.to_string_lossy(),
        elide(&dst_dev, &root),
        key.to_string_lossy(),
        dev.to_string_lossy()
    );
    Ok(0)
}

fn style_fix(path: &Path, cfg: &Path) -> Result<Vec<String>> {
    let dir = tempfile::Builder::new().prefix("style_fix_").tempdir()?;
    let tmp = dir
        .path()
        .join(path.file_name().context("invalid source path")?);
    std::fs::copy(path, &tmp)?;
    let meta = std::fs::metadata(path)?;
    filetime::set_file_times(
        &tmp,
        filetime::FileTime::from_last_access_time(&meta),
        filetime::FileTime::from_last_modification_time(&meta),
    )?;
    let base = gates::harness_root().join("tools/style_assess");
    let run_pass = || {
        Command::new(gates::bundled_tool("lute"))
            .arg("run")
            .arg(base.join("fix_pass.luau"))
            .arg(&tmp)
            .arg(&tmp)
            .output()
    };
    let result = run_pass()?;
    if !result.status.success() {
        let detail = if result.stderr.is_empty() {
            &result.stdout
        } else {
            &result.stderr
        };
        anyhow::bail!(
            "{}",
            String::from_utf8_lossy(detail)
                .trim()
                .chars()
                .take(200)
                .collect::<String>()
        );
    }
    let text = String::from_utf8_lossy(&result.stdout);
    let mut fired = std::collections::BTreeSet::new();
    if let Some(ids) = text
        .trim()
        .lines()
        .last()
        .unwrap_or("")
        .strip_prefix("changed|")
    {
        fired.extend(ids.split(',').map(str::to_owned));
    }
    let rules = base.join("autofix");
    let pre = lint("style_assess", &rules, cfg, &[tmp.clone()], false)?
        .map_err(|e| anyhow::anyhow!("{}", e.chars().take(200).collect::<String>()))?;
    let ids: Vec<_> = pre
        .iter()
        .filter(|f| f.id == "WRIT15" || f.id == "WRIT22")
        .map(|f| f.id.clone())
        .collect();
    if !ids.is_empty() {
        lint("style_assess", &rules, cfg, &[tmp.clone()], true)?
            .map_err(|e| anyhow::anyhow!("{}", e.chars().take(200).collect::<String>()))?;
        fired.extend(ids);
        let result = run_pass()?;
        if !result.status.success() {
            anyhow::bail!(
                "auto-fix broke the parse: {}",
                String::from_utf8_lossy(&result.stderr)
                    .trim()
                    .chars()
                    .take(150)
                    .collect::<String>()
            );
        }
        let remaining = lint("style_assess", &rules, cfg, &[tmp.clone()], false)?
            .map_err(|e| anyhow::anyhow!("{}", e.chars().take(200).collect::<String>()))?;
        let ids: std::collections::BTreeSet<_> = remaining
            .iter()
            .filter(|f| f.id == "WRIT15" || f.id == "WRIT22")
            .map(|f| f.id.as_str())
            .collect();
        if !ids.is_empty() {
            anyhow::bail!(
                "required repair remained: {}",
                ids.into_iter().collect::<Vec<_>>().join(", ")
            );
        }
    }
    if std::fs::read(&tmp)? != std::fs::read(path)? {
        let mut name = path.as_os_str().to_os_string();
        name.push(".stylefix");
        let final_path = PathBuf::from(name);
        std::fs::copy(&tmp, &final_path)?;
        let meta = std::fs::metadata(&tmp)?;
        filetime::set_file_times(
            &final_path,
            filetime::FileTime::from_last_access_time(&meta),
            filetime::FileTime::from_last_modification_time(&meta),
        )?;
        std::fs::rename(final_path, path)?;
    } else {
        fired.clear();
    }
    Ok(fired.into_iter().collect())
}

pub fn run_style(args: &[OsString]) -> Result<i32> {
    let mut root = std::env::current_dir()?;
    let mut now = None;
    let mut fix = false;
    let mut ignores = Vec::new();
    let mut paths = Vec::new();
    let mut i = 0;
    while i < args.len() {
        if args[i] == "--fix" {
            fix = true;
            i += 1;
        } else if i + 1 < args.len()
            && (args[i] == "--root" || args[i] == "--now" || args[i] == "--ignore")
        {
            if args[i] == "--root" {
                root = PathBuf::from(&args[i + 1]);
            } else if args[i] == "--now" {
                now = Some(args[i + 1].to_string_lossy().parse::<i64>()?.to_string());
            } else {
                ignores.push(globset::Glob::new(&args[i + 1].to_string_lossy())?.compile_matcher());
            }
            i += 2;
        } else {
            paths.push(PathBuf::from(&args[i]));
            i += 1;
        }
    }
    if paths.is_empty() {
        println!("style_assess — the style lint and the formatter.\n\n  style_assess [--root DIR] [--fix] [--now EPOCH] [--ignore GLOB] <file...>");
        return Ok(0);
    }
    if !gates::bundled_tool("lute").exists() {
        println!("style_assess: BLOCKED (ENV)\n\nENV|lute-absent|install the harness toolchain");
        return Ok(3);
    }
    let mut files = Vec::new();
    for path in paths {
        let path = if path.is_absolute() {
            path
        } else {
            root.join(path)
        };
        files.extend(collect(&path));
    }
    files.retain(|p| {
        !is_ignored(p, &root, &ignores) && !p.components().any(|c| c.as_os_str() == "tests")
    });
    if files.is_empty() {
        return Ok(0);
    }
    if !gates::cache().join("api_globals.luau").exists() {
        eprintln!("style_assess: BLOCKED\n\n0|0|GATE4|required API globals unavailable for WRIT25 WRIT29 WRIT30 WRIT23 WRIT31|run harness api --emit-globals, then retry");
        return Ok(3);
    }
    let cfg = config("style_assess", now.as_deref())?;
    let mut errors = Vec::new();
    let mut formatted = 0;
    if fix {
        for file in &files {
            match style_fix(file, &cfg) {
                Ok(ids) if !ids.is_empty() => {
                    formatted += 1;
                    println!("{}: formatted ({})", elide(file, &root), ids.join(", "));
                }
                Ok(_) => (),
                Err(e) => errors.push(format!("{} - {e}", elide(file, &root))),
            }
        }
        if formatted != 0 {
            println!("style_assess: formatted {formatted} files");
        }
    }
    let rules = gates::harness_root().join("tools/style_assess/rules");
    let mut findings = match lint("style_assess", &rules, &cfg, &files, false)? {
        Ok(f) => f,
        Err(e) => {
            eprintln!(
                "style_assess: BLOCKED\n\nlint output unparseable: {}",
                e.chars().take(200).collect::<String>()
            );
            return Ok(2);
        }
    };
    match reuse_filtered(&root, &files, &ignores) {
        Ok(f) => findings.extend(f),
        Err(e) => {
            eprintln!(
                "style_assess: BLOCKED\n\nGATE4|required reuse check failed|{}",
                e.to_string().chars().take(200).collect::<String>()
            );
            return Ok(2);
        }
    }
    let status = report("style_assess", &root, findings, false);
    if status != 0 {
        return Ok(status);
    }
    if !errors.is_empty() {
        eprintln!(
            "style_assess: BLOCKED\n\n0|0|GATE4|required style repair failed|{}",
            errors
                .join(" / ")
                .chars()
                .take(300)
                .collect::<String>()
                .replace('|', "/")
        );
        return Ok(3);
    }
    Ok(0)
}
