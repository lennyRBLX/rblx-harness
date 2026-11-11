use crate::gates;
use serde_json::Value;
use std::{
    ffi::OsString,
    path::{Path, PathBuf},
};

fn json_file(path: &Path) -> Result<Value, String> {
    let s = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    serde_json::from_str(&s).map_err(|e| e.to_string())
}
fn exists_link(p: &Path) -> bool {
    std::fs::symlink_metadata(p).is_ok()
}
fn has_link(root: &Path) -> bool {
    root.is_dir()
        && walkdir::WalkDir::new(root)
            .follow_links(false)
            .into_iter()
            .filter_map(Result::ok)
            .any(|e| e.path_is_symlink())
}
pub fn validate(root: &Path) -> Vec<String> {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let mut errors = Vec::new();
    if !root.join(".roblox").is_file() {
        errors.push("marker: .roblox is absent".into());
    }
    let dep = root.join("rblx-harness");
    if gates::project_harness_root(&root).is_none() {
        errors.push("submodule: rblx-harness is absent, invalid, or not registered from the required GitHub URL".into());
    }
    let manifest = match json_file(&root.join("manifest.json")) {
        Ok(v) if v.is_object() && v["schema"] == 1 => v,
        Ok(_) => {
            errors.push("manifest: schema 1 is required".into());
            Value::Null
        }
        Err(e) => {
            errors.push(format!("manifest: {e}"));
            Value::Null
        }
    };
    let places = manifest
        .get("places")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    if places.is_empty() {
        errors.push("places: at least one place is required".into());
    }
    for place in places {
        let Some(place) = place.as_str() else {
            errors.push("manifest places must be names".into());
            continue;
        };
        match json_file(&root.join(format!("{place}.project.json"))) {
            Ok(v) => {
                if !v.get("tree").is_some_and(Value::is_object) {
                    errors.push(format!("project {place}: tree is absent"));
                }
            }
            Err(e) => {
                errors.push(format!("project {place}: {e}"));
                continue;
            }
        };
        for tail in [
            "ServerScriptService/Services",
            "StarterPlayer/StarterPlayerScripts/Controllers",
        ] {
            let rel = format!("places/{place}/src/{tail}");
            if !root.join(&rel).is_dir() {
                errors.push(format!("place path is absent: {rel}"));
            }
        }
    }
    if !root.join("default.project.json").is_file() {
        errors.push("default.project.json is absent".into());
    }
    for name in ["AGENTS.md", "CLAUDE.md", "README.md"] {
        if !root.join(name).is_file() {
            errors.push(format!("template output is absent: {name}"));
        }
    }
    let names = [".agents", ".claude", ".codex", ".serena", ".roblox"];
    let probes = [
        ".agents/.rblx-harness-probe",
        ".claude/.rblx-harness-probe",
        ".codex/.rblx-harness-probe",
        ".serena/.rblx-harness-probe",
        ".roblox",
    ];
    let mut args = vec!["ls-files", "-z", "--"];
    args.extend(names);
    let (rc, tracked, detail) = gates::git(&root, &args);
    let mut args = vec!["check-ignore", "--no-index", "--"];
    args.extend(probes);
    let (irc, ignored, _) = gates::git(&root, &args);
    for (name, probe) in names.iter().zip(probes) {
        if rc != 0 {
            errors.push(format!("local state: cannot inspect {name}: {detail}"));
        } else if tracked
            .split('\0')
            .any(|p| p == *name || p.starts_with(&format!("{name}/")))
        {
            errors.push(format!("local state must not be tracked: {name}"));
        }
        if irc != 0 || !ignored.lines().any(|p| p == probe) {
            errors.push(format!("local state is not ignored: {name}"));
        }
    }
    match std::fs::read_to_string(root.join(".codex/config.toml")) {
        Ok(s) => {
            if let Err(e) = s.parse::<toml::Value>() {
                errors.push(format!("Codex config: {e}"));
            }
        }
        Err(e) => errors.push(format!("Codex config: {e}")),
    }
    match json_file(&root.join(".claude/settings.json")) {
        Ok(v) => {
            if !v.is_object() {
                errors.push("Claude settings: an object is required".into());
            }
        }
        Err(e) => errors.push(format!("Claude settings: {e}")),
    }
    if let Err(e) = gates::codex_agents(&root) {
        errors.push(format!("agents: {e}"));
    }
    if let Err(e) = gates::claude_agents(&root) {
        errors.push(format!("Claude agents: {e}"));
    }
    for skill in gates::SKILLS {
        for (prefix, label) in [
            (".agents/skills", "skill"),
            (".claude/skills", "Claude skill"),
        ] {
            if !root.join(prefix).join(skill).join("SKILL.md").is_file() {
                errors.push(format!("{label} is absent: {skill}"));
            }
        }
    }
    if exists_link(&root.join(".agents/skills/rblx-new-game")) {
        errors.push("rblx-new-game must not be installed inside a managed project".into());
    }
    if exists_link(&root.join(".claude/skills/rblx-new-game")) {
        errors.push("rblx-new-game must not be installed in project Claude skills".into());
    }
    let assets = manifest
        .get("assets")
        .filter(|v| !v.is_null())
        .cloned()
        .unwrap_or(Value::Array(vec![]));
    let mut asset_names = Vec::new();
    if let Some(a) = assets.as_array().filter(|a| a.iter().all(Value::is_string)) {
        asset_names = a.iter().filter_map(Value::as_str).collect();
        if asset_names.contains(&"plugin") {
            errors.push("manifest uses legacy plugin asset; use plugins".into());
        }
        let mut unknown: Vec<_> = asset_names
            .iter()
            .copied()
            .filter(|n| !["packages", "services", "controllers", "plugins"].contains(n))
            .collect();
        unknown.sort();
        unknown.dedup();
        if !unknown.is_empty() {
            errors.push(format!(
                "manifest has unknown assets: {}",
                unknown.join(", ")
            ));
        }
    } else {
        errors.push("manifest assets must be a list of names".into());
    }
    for (name, path) in [
        ("packages", "shared/src/ReplicatedStorage/Packages"),
        ("services", "shared/src/ServerScriptService/Services"),
        (
            "controllers",
            "shared/src/StarterPlayer/StarterPlayerScripts/Controllers",
        ),
    ] {
        if asset_names.contains(&name) && !has_link(&root.join(path)) {
            errors.push(format!("{name} asset links are absent"));
        }
    }
    if exists_link(&root.join("plugin")) {
        errors.push("legacy plugin/ is present; use plugins/".into());
    }
    if asset_names.contains(&"plugins") && !root.join("plugins").is_dir() {
        errors.push("plugin support is selected but plugins/ is absent".into());
    }
    for base in ["shared", ".agents"] {
        let p = root.join(base);
        if p.is_dir() {
            for e in walkdir::WalkDir::new(p)
                .follow_links(false)
                .into_iter()
                .filter_map(Result::ok)
            {
                if e.path_is_symlink() && !e.path().exists() {
                    errors.push(format!(
                        "dead symlink: {}",
                        e.path().strip_prefix(&root).unwrap_or(e.path()).display()
                    ));
                }
            }
        }
    }
    for p in [
        "Cargo.lock",
        "Cargo.toml",
        "shared/TOOLS.md",
        "src/main.rs",
        "src/lib.rs",
        "src/api.rs",
        "src/argon.rs",
        "src/buffer.rs",
        "src/checks.rs",
        "src/coord.rs",
        "src/gates.rs",
        "src/hooks.rs",
        "src/offline.rs",
        "src/profile.rs",
        "src/project_gate.rs",
        "src/scaffold.rs",
        "src/session.rs",
        "src/setup.rs",
        "src/studio.rs",
        "src/types.rs",
        "src/verify.rs",
    ] {
        if !dep.join(p).is_file() {
            errors.push(format!("harness tool is absent: {p}"));
        }
    }
    errors
}
pub fn run(args: &[OsString]) -> anyhow::Result<i32> {
    let mut root = std::env::current_dir()?;
    let mut i = 0;
    while i < args.len() {
        if args[i] == "--project-root" && i + 1 < args.len() {
            root = PathBuf::from(&args[i + 1]);
            i += 2;
        } else {
            anyhow::bail!("unrecognized argument: {}", args[i].to_string_lossy());
        }
    }
    let errors = validate(&root);
    if errors.is_empty() {
        println!("project-gate|READY");
        Ok(0)
    } else {
        for e in errors {
            eprintln!("project-gate|ERROR|{e}");
        }
        Ok(2)
    }
}
