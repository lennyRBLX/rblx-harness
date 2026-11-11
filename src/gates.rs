use std::path::{Path, PathBuf};
use std::process::Command;

pub const AGENTS: [&str; 5] = [
    "researcher",
    "optimizer",
    "reviewer",
    "debugger",
    "implementer",
];
pub const SKILLS: [&str; 5] = [
    "rblx-writer",
    "rblx-gui",
    "rblx-debug",
    "rblx-optimize",
    "rblx-plan",
];
pub fn harness_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}
pub fn bundled_tool(name: &str) -> PathBuf {
    let bundled =
        harness_root()
            .join("tools/bin")
            .join(format!("{}{}", name, std::env::consts::EXE_SUFFIX));
    if bundled.is_file() {
        return bundled;
    }
    if let Some(path) = std::env::var_os("PATH") {
        for dir in std::env::split_paths(&path) {
            let candidate = dir.join(format!("{}{}", name, std::env::consts::EXE_SUFFIX));
            if candidate.is_file() {
                return candidate;
            }
        }
    }
    bundled
}
pub fn cache() -> PathBuf {
    dirs::home_dir().unwrap_or_default().join(".cache/harness")
}
pub fn git(root: &Path, args: &[&str]) -> (i32, String, String) {
    match Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .env("GIT_OPTIONAL_LOCKS", "0")
        .output()
    {
        Ok(o) => (
            o.status.code().unwrap_or(1),
            String::from_utf8_lossy(&o.stdout).trim().to_string(),
            String::from_utf8_lossy(&o.stderr).trim().to_string(),
        ),
        Err(e) => (1, String::new(), e.to_string()),
    }
}
pub fn project_harness_root(root: &Path) -> Option<PathBuf> {
    let valid = |args: &[&str], expected: &str| {
        let (rc, out, _) = git(root, args);
        rc == 0 && out == expected
    };
    if !valid(
        &[
            "config",
            "-f",
            ".gitmodules",
            "--get",
            "submodule.rblx-harness.path",
        ],
        "rblx-harness",
    ) || !valid(
        &[
            "config",
            "-f",
            ".gitmodules",
            "--get",
            "submodule.rblx-harness.url",
        ],
        "https://github.com/lennyRBLX/rblx-harness.git",
    ) {
        return None;
    }
    for (name, mode) in [("rblx-harness", "160000 "), (".gitmodules", "100644 ")] {
        let (rc, out, _) = git(root, &["ls-files", "--stage", "--", name]);
        if rc != 0 || !out.lines().any(|l| l.starts_with(mode)) {
            return None;
        }
    }
    if git(root, &["diff", "--quiet", "--", ".gitmodules"]).0 != 0 {
        return None;
    }
    let p = root.join("rblx-harness");
    if p.is_symlink()
        || !["shared/CORE.md", "Cargo.toml", "openai/config/project.toml"]
            .iter()
            .all(|s| p.join(s).is_file())
    {
        return None;
    }
    p.canonicalize().ok()
}
pub fn codex_agents(root: &Path) -> Result<(), String> {
    let dir = root.join(".codex/agents");
    if AGENTS
        .iter()
        .any(|n| !dir.join(format!("{n}.toml")).is_file())
    {
        return Err(format!("Codex agents must include: {}", AGENTS.join(", ")));
    }
    for name in AGENTS {
        let p = dir.join(format!("{name}.toml"));
        let s =
            std::fs::read_to_string(&p).map_err(|e| format!("{} is invalid: {e}", p.display()))?;
        let v: toml::Value = s
            .parse()
            .map_err(|e| format!("{} is invalid: {e}", p.display()))?;
        if v.get("name").and_then(|x| x.as_str()) != Some(name)
            || ["description", "developer_instructions"]
                .iter()
                .any(|k| v.get(k).and_then(|x| x.as_str()).unwrap_or("").is_empty())
        {
            return Err(format!("{} has an invalid agent definition", p.display()));
        }
        if v.get("agents")
            .and_then(|x| x.get("enabled"))
            .and_then(|x| x.as_bool())
            != Some(false)
        {
            return Err(format!("{} must disable nested delegation", p.display()));
        }
    }
    Ok(())
}
pub fn claude_agents(root: &Path) -> Result<(), String> {
    let dir = root.join(".claude/agents");
    for name in AGENTS {
        let p = dir.join(format!("{name}.md"));
        let s = std::fs::read_to_string(&p)
            .map_err(|_| format!("Claude agents must include: {}", AGENTS.join(", ")))?;
        let (fields, body) = s
            .strip_prefix("---\n")
            .and_then(|s| s.split_once("\n---\n"))
            .unwrap_or(("", ""));
        let map: std::collections::HashMap<_, _> = fields
            .lines()
            .filter_map(|s| s.split_once(':'))
            .map(|(a, b)| (a.trim(), b.trim()))
            .collect();
        let (model, effort) = match name {
            "researcher" => ("haiku", None),
            "implementer" => ("inherit", None),
            "debugger" => ("claude-opus-5-5", Some("xhigh")),
            _ => ("claude-opus-5-5", Some("high")),
        };
        if map.get("name") != Some(&name)
            || map.get("model") != Some(&model)
            || map.get("effort").copied() != effort
            || map.get("description").copied().unwrap_or("").is_empty()
            || body.trim().is_empty()
        {
            return Err(format!("{} has an invalid agent definition", p.display()));
        }
        if !map
            .get("disallowedTools")
            .unwrap_or(&"")
            .split(',')
            .any(|s| s.trim() == "Agent")
        {
            return Err(format!("{} must disable nested delegation", p.display()));
        }
    }
    Ok(())
}

pub fn merge_project_codex_config(existing: &str, canonical: &str) -> anyhow::Result<String> {
    let current: toml::Value = toml::from_str(existing)
        .map_err(|e| anyhow::anyhow!("project Codex config is malformed: {e}"))?;
    let defaults: toml::Value = toml::from_str(canonical)
        .map_err(|e| anyhow::anyhow!("project Codex config is malformed: {e}"))?;
    let current = current
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("project Codex config must be a table"))?;
    let defaults = defaults
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("project Codex defaults must be a table"))?;
    let mut additions = Vec::new();
    for (key, value) in defaults {
        if !key
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
            || !matches!(
                value,
                toml::Value::String(_) | toml::Value::Integer(_) | toml::Value::Boolean(_)
            )
        {
            anyhow::bail!("harness defaults must use scalar top-level TOML keys");
        }
        if !current.contains_key(key) {
            let value = match value {
                toml::Value::String(v) => serde_json::to_string(v)?,
                toml::Value::Integer(v) => v.to_string(),
                toml::Value::Boolean(v) => v.to_string(),
                _ => unreachable!(),
            };
            additions.push(format!("{key} = {value}"));
        }
    }
    if additions.is_empty() {
        return Ok(existing.to_owned());
    }
    let merged = format!("{}\n\n{existing}", additions.join("\n"));
    let _: toml::Value = toml::from_str(&merged)?;
    Ok(merged)
}

pub fn merge_project_claude_settings(existing: &str, canonical: &str) -> anyhow::Result<String> {
    use serde_json::{Map, Value};
    let mut current: Value = if existing.trim().is_empty() {
        Value::Object(Map::new())
    } else {
        serde_json::from_str(existing)
            .map_err(|e| anyhow::anyhow!("project Claude settings are malformed: {e}"))?
    };
    let defaults: Value = serde_json::from_str(canonical)
        .map_err(|e| anyhow::anyhow!("project Claude settings are malformed: {e}"))?;
    let current = current
        .as_object_mut()
        .ok_or_else(|| anyhow::anyhow!("Claude settings must contain an object"))?;
    let defaults = defaults
        .as_object()
        .ok_or_else(|| anyhow::anyhow!("Claude settings must contain an object"))?;
    let scalar = |v: &Value| v.is_string() || v.is_i64() || v.is_u64() || v.is_boolean();
    let mut changed = false;
    for (key, value) in defaults {
        if scalar(value) {
            if !current.contains_key(key) {
                current.insert(key.clone(), value.clone());
                changed = true;
            }
            continue;
        }
        let values = value.as_object().ok_or_else(|| {
            anyhow::anyhow!(
                "harness defaults must be scalars or objects of scalars or string arrays"
            )
        })?;
        if values
            .values()
            .any(|v| !scalar(v) && !v.as_array().is_some_and(|a| a.iter().all(Value::is_string)))
        {
            anyhow::bail!(
                "harness defaults must be scalars or objects of scalars or string arrays"
            );
        }
        let mut object = match current.get(key) {
            None => Map::new(),
            Some(v) => v
                .as_object()
                .ok_or_else(|| {
                    anyhow::anyhow!("project Claude settings {key} must contain an object")
                })?
                .clone(),
        };
        let old = object.clone();
        for (name, item) in values {
            if !object.contains_key(name) {
                object.insert(name.clone(), item.clone());
            } else if let Some(defaults) = item.as_array() {
                let current = object
                    .get_mut(name)
                    .and_then(Value::as_array_mut)
                    .ok_or_else(|| {
                        anyhow::anyhow!(
                            "project Claude settings {key}.{name} must contain an array"
                        )
                    })?;
                let additions: Vec<_> = defaults
                    .iter()
                    .filter(|v| !current.contains(v))
                    .cloned()
                    .collect();
                current.extend(additions);
            }
        }
        if object != old {
            current.insert(key.clone(), Value::Object(object));
            changed = true;
        }
    }
    if !changed {
        return Ok(existing.to_owned());
    }
    Ok(format!("{}\n", serde_json::to_string_pretty(current)?))
}

pub fn corpus_assets_error() -> String {
    let cache = cache();
    let docs = cache.join("creator-docs");
    let engine = docs.join("content/en-us/reference/engine");
    for (path, label, directory) in [
        (cache.join("API-Dump.json"), "API-Dump.json", false),
        (docs.join(".git"), "Creator Docs .git", true),
        (engine.clone(), "Creator Docs engine corpus", true),
        (cache.join("docs_index.json"), "docs_index.json", false),
    ] {
        if !(if directory {
            path.is_dir()
        } else {
            path.is_file()
        }) {
            return format!("{label} is missing");
        }
    }
    let read_json = |p: &Path| -> anyhow::Result<serde_json::Value> {
        Ok(serde_json::from_slice(&std::fs::read(p)?)?)
    };
    let dump = match read_json(&cache.join("API-Dump.json")) {
        Ok(v) => v,
        Err(e) => {
            return format!(
                "corpus is unreadable or malformed: {}",
                e.to_string().chars().take(160).collect::<String>()
            )
        }
    };
    let index = match read_json(&cache.join("docs_index.json")) {
        Ok(v) => v,
        Err(e) => {
            return format!(
                "corpus is unreadable or malformed: {}",
                e.to_string().chars().take(160).collect::<String>()
            )
        }
    };
    if !dump.is_object() || !dump["Classes"].is_array() || !dump["Enums"].is_array() {
        return "API-Dump.json has an invalid schema".into();
    }
    if !index.is_array() {
        return "docs_index.json has an invalid schema".into();
    }
    if !walkdir::WalkDir::new(engine)
        .follow_links(false)
        .into_iter()
        .filter_map(Result::ok)
        .any(|e| {
            e.file_type().is_file()
                && matches!(
                    e.path().extension().and_then(|s| s.to_str()),
                    Some("yaml" | "yml")
                )
        })
    {
        return "Creator Docs engine corpus has no YAML records".into();
    }
    String::new()
}
pub fn corpus_status(now: Option<f64>) -> (String, String) {
    let error = corpus_assets_error();
    if !error.is_empty() {
        return (
            if error.contains("missing") {
                "missing"
            } else {
                "malformed"
            }
            .into(),
            error,
        );
    }
    let refresh = std::fs::read(cache().join("corpus-refresh.json"))
        .map_err(anyhow::Error::from)
        .and_then(|s| serde_json::from_slice::<serde_json::Value>(&s).map_err(anyhow::Error::from));
    let refresh = match refresh {
        Ok(v) => v,
        Err(e) => {
            return (
                "stale".into(),
                format!(
                    "successful-refresh timestamp is unavailable: {}",
                    e.to_string().chars().take(120).collect::<String>()
                ),
            )
        }
    };
    let Some(timestamp) = refresh.get("refreshed_at").and_then(|v| v.as_f64()) else {
        return (
            "malformed".into(),
            "successful-refresh timestamp is malformed".into(),
        );
    };
    let age = now.unwrap_or_else(|| {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64()
    }) - timestamp;
    if age < -300.0 {
        (
            "malformed".into(),
            "successful-refresh timestamp is in the future".into(),
        )
    } else if age >= 86400.0 {
        (
            "stale".into(),
            "successful refresh is at least 24 hours old".into(),
        )
    } else {
        ("fresh".into(), String::new())
    }
}

fn git_mutate(root: &Path, args: &[&str], timeout: u64) -> (i32, String, String) {
    use std::{
        process::Stdio,
        time::{Duration, Instant},
    };
    let mut child = match Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => return (1, String::new(), e.to_string()),
    };
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let output_thread = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        if let Some(mut pipe) = stdout {
            let _ = std::io::Read::read_to_end(&mut pipe, &mut bytes);
        }
        bytes
    });
    let error_thread = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        if let Some(mut pipe) = stderr {
            let _ = std::io::Read::read_to_end(&mut pipe, &mut bytes);
        }
        bytes
    });
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if started.elapsed() < Duration::from_secs(timeout) => {
                std::thread::sleep(Duration::from_millis(50))
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                return (
                    1,
                    String::new(),
                    format!("git timed out after {timeout} seconds"),
                );
            }
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return (1, String::new(), e.to_string());
            }
        }
    };
    let output = output_thread.join().unwrap_or_default();
    let error = error_thread.join().unwrap_or_default();
    (
        status.code().unwrap_or(1),
        String::from_utf8_lossy(&output).trim().to_owned(),
        String::from_utf8_lossy(&error).trim().to_owned(),
    )
}
pub fn gate6_state(root: &Path, fetch: bool) -> (String, String) {
    let state = |a: &str, b: String| (a.to_owned(), b);
    if git(root, &["rev-parse", "--git-dir"]).0 != 0 {
        return state(
            "not-repo",
            "working directory is not a git repository".into(),
        );
    }
    let (rc, head, error) = git(root, &["rev-parse", "--verify", "HEAD^{commit}"]);
    if rc != 0 || head.is_empty() {
        return state(
            "head-read-failed",
            if error.is_empty() {
                "HEAD could not be read".into()
            } else {
                error
            },
        );
    }
    let (rc, branch, error) = git(root, &["symbolic-ref", "--quiet", "--short", "HEAD"]);
    if rc != 0 || branch.is_empty() {
        return state(
            "no-upstream",
            if error.is_empty() {
                "detached HEAD".into()
            } else {
                error
            },
        );
    }
    let (rc, remote, _) = git(root, &["remote", "get-url", "origin"]);
    if rc != 0 || remote.is_empty() {
        return state("no-remote", "origin is not configured".into());
    }
    let (rc, output, error) = git_mutate(root, &["ls-remote", "--symref", "origin", "HEAD"], 60);
    if rc != 0 {
        return state(
            "remote-head-read-failed",
            if !error.is_empty() {
                error
            } else if !output.is_empty() {
                output
            } else {
                "origin HEAD could not be read".into()
            }
            .chars()
            .take(200)
            .collect(),
        );
    }
    let canonical = output.lines().find_map(|line| {
        let mut p = line.split_whitespace();
        if p.next() == Some("ref:") {
            let branch = p.next()?.strip_prefix("refs/heads/")?;
            if p.next() == Some("HEAD") && p.next().is_none() {
                return Some(branch);
            }
        }
        None
    });
    let Some(canonical) = canonical else {
        return state(
            "remote-head-read-failed",
            "origin HEAD does not name a branch".into(),
        );
    };
    if branch != canonical {
        return state(
            "wrong-branch",
            format!("{branch} is checked out; origin requires {canonical}"),
        );
    }
    if fetch {
        let refspec = format!("+refs/heads/{canonical}:refs/remotes/origin/{canonical}");
        let (rc, out, err) = git_mutate(
            root,
            &["fetch", "--quiet", "--no-tags", "origin", &refspec],
            90,
        );
        if rc != 0 {
            let detail = if !err.is_empty() {
                err
            } else if !out.is_empty() {
                out
            } else {
                "git fetch failed".into()
            };
            return state("fetch-failed", detail.chars().take(200).collect());
        }
    }
    let range = format!("origin/{canonical}...HEAD");
    let (rc, counts, error) = git(root, &["rev-list", "--left-right", "--count", &range]);
    if rc != 0 {
        return state(
            "ref-read-failed",
            if error.is_empty() {
                "could not compare HEAD".into()
            } else {
                error
            },
        );
    }
    let counts: Vec<_> = counts.split_whitespace().map(str::parse::<u64>).collect();
    if counts.len() != 2 || counts.iter().any(Result::is_err) {
        return state(
            "ref-read-failed",
            "git returned an unreadable comparison".into(),
        );
    }
    let behind = counts[0].as_ref().copied().unwrap_or(0);
    let ahead = counts[1].as_ref().copied().unwrap_or(0);
    if behind > 0 && ahead > 0 {
        state("diverged", format!("{behind} behind, {ahead} ahead"))
    } else if behind > 0 {
        state("behind", format!("{behind} behind"))
    } else {
        state("ok", String::new())
    }
}
