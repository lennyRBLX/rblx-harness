use anyhow::{anyhow, bail, Context, Result};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    process::Command,
};
use walkdir::WalkDir;

const AGENTS: &[&str] = &[
    "researcher",
    "optimizer",
    "reviewer",
    "debugger",
    "implementer",
];
const SKILLS: &[&str] = &[
    "rblx-writer",
    "rblx-gui",
    "rblx-debug",
    "rblx-optimize",
    "rblx-plan",
    "rblx-test",
];
const ORDER: &[&str] = &["packages", "services", "controllers", "plugins"];
const GB: &str = "<!-- BEGIN rblx-harness project guidance -->";
const GE: &str = "<!-- END rblx-harness project guidance -->";
const CB: &str = "<!-- BEGIN rblx-harness Claude Code import -->";
const CE: &str = "<!-- END rblx-harness Claude Code import -->";
fn harness() -> PathBuf {
    if let Ok(exe) = std::env::current_exe() {
        for ancestor in exe.ancestors() {
            if ancestor.join("shared/CORE.md").is_file()
                && ancestor.join("openai/config/project.toml").is_file()
            {
                return ancestor.to_path_buf();
            }
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        for candidate in [cwd.join("rblx-harness"), cwd] {
            if candidate.join("shared/CORE.md").is_file()
                && candidate.join("openai/config/project.toml").is_file()
            {
                return candidate;
            }
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}
fn text(p: &Path) -> String {
    fs::read_to_string(p).unwrap_or_default()
}
fn put(p: &Path, s: &str) -> Result<()> {
    if fs::read_to_string(p).ok().as_deref() == Some(s) {
        return Ok(());
    }
    if let Some(d) = p.parent() {
        fs::create_dir_all(d)?
    }
    fs::write(p, s).with_context(|| format!("cannot write {}", p.display()))
}
fn json_text(v: &Value) -> Result<String> {
    Ok(format!("{}\n", serde_json::to_string_pretty(v)?))
}
fn sorted(v: &Value) -> Value {
    match v {
        Value::Object(m) => {
            let mut pairs: Vec<_> = m.iter().collect();
            pairs.sort_by_key(|(k, _)| *k);
            Value::Object(
                pairs
                    .into_iter()
                    .map(|(k, v)| (k.clone(), sorted(v)))
                    .collect(),
            )
        }
        Value::Array(a) => Value::Array(a.iter().map(sorted).collect()),
        _ => v.clone(),
    }
}
fn put_json(p: &Path, v: &Value) -> Result<()> {
    put(p, &json_text(&sorted(v))?)
}
fn remove(p: &Path) -> Result<()> {
    if let Ok(m) = fs::symlink_metadata(p) {
        if m.is_dir() && !m.file_type().is_symlink() {
            fs::remove_dir_all(p)?
        } else {
            fs::remove_file(p)?
        }
    }
    Ok(())
}
fn rel(from: &Path, to: &Path) -> PathBuf {
    let a: Vec<_> = from.components().collect();
    let b: Vec<_> = to.components().collect();
    let n = a.iter().zip(&b).take_while(|(x, y)| x == y).count();
    let mut r = PathBuf::new();
    for _ in n..a.len() {
        r.push("..")
    }
    for c in &b[n..] {
        r.push(c.as_os_str())
    }
    r
}
fn link(src: &Path, dst: &Path, dir: bool, replace: bool) -> Result<&'static str> {
    if !src.exists() {
        bail!("harness asset is absent: {}", src.display())
    }
    fs::create_dir_all(dst.parent().unwrap())?;
    if let Ok(m) = fs::symlink_metadata(dst) {
        if m.file_type().is_symlink() {
            if fs::canonicalize(dst).ok() == fs::canonicalize(src).ok() {
                return Ok("exact");
            }
            remove(dst)?
        } else if replace {
            remove(dst)?
        } else {
            return Ok("preserved");
        }
    }
    let target = rel(dst.parent().unwrap(), src);
    #[cfg(unix)]
    {
        let _ = dir;
        std::os::unix::fs::symlink(&target, dst)?;
    }
    #[cfg(windows)]
    {
        if dir {
            std::os::windows::fs::symlink_dir(&target, dst)?
        } else {
            std::os::windows::fs::symlink_file(&target, dst)?
        }
    }
    Ok("linked")
}
fn managed(p: &Path, begin: &str, end: &str, lines: &[String]) -> Result<()> {
    let mut s = text(p);
    if let (Some(a), Some(b)) = (s.find(begin), s.find(end)) {
        if b >= a {
            s = format!("{}{}", &s[..a], &s[b + end.len()..])
                .trim()
                .to_string()
        }
    }
    let block = format!("{}\n{}\n{}", begin, lines.join("\n"), end);
    put(
        p,
        &format!(
            "{}{}{}\n",
            s.trim(),
            if s.trim().is_empty() { "" } else { "\n\n" },
            block
        ),
    )
}
fn tree(src: &Path, dst: &Path, replace: bool) -> Result<BTreeMap<String, usize>> {
    if !src.is_dir() {
        bail!("harness asset root is absent: {}", src.display())
    }
    fs::create_dir_all(dst)?;
    let mut count = BTreeMap::from([
        ("linked".into(), 0),
        ("exact".into(), 0),
        ("preserved".into(), 0),
    ]);
    let mut ignored = BTreeSet::new();
    for item in WalkDir::new(src)
        .sort_by_file_name()
        .into_iter()
        .filter_entry(|e| e.file_name() != "__pycache__")
    {
        let e = item?;
        let r = e.path().strip_prefix(src)?;
        let target = dst.join(r);
        if e.file_type().is_dir() {
            fs::create_dir_all(&target)?;
            continue;
        }
        let n = e.file_name().to_string_lossy();
        if [".DS_Store", ".gitignore", ".luaurc"].contains(&n.as_ref()) || n.ends_with(".pyc") {
            continue;
        }
        let state = link(e.path(), &target, false, replace)?;
        *count.get_mut(state).unwrap() += 1;
        if state != "preserved" {
            if let Some(c) = r.components().next() {
                ignored.insert(c.as_os_str().to_string_lossy().into_owned());
            }
        }
    }
    managed(
        &dst.join(".gitignore"),
        "# BEGIN rblx-harness links",
        "# END rblx-harness links",
        &ignored.into_iter().collect::<Vec<_>>(),
    )?;
    Ok(count)
}
fn copy(src: &Path, dst: &Path) -> Result<()> {
    fs::create_dir_all(dst.parent().unwrap())?;
    fs::copy(src, dst)?;
    let m = fs::metadata(src)?;
    fs::set_permissions(dst, m.permissions())?;
    filetime::set_file_times(
        dst,
        filetime::FileTime::from_last_access_time(&m),
        filetime::FileTime::from_last_modification_time(&m),
    )?;
    Ok(())
}
fn merge_claude(existing: &str, canonical: &str) -> Result<String> {
    let mut current: Value = if existing.trim().is_empty() {
        json!({})
    } else {
        serde_json::from_str(existing).context("project Claude settings are malformed")?
    };
    let defaults: Value = serde_json::from_str(canonical)?;
    let obj = current
        .as_object_mut()
        .ok_or_else(|| anyhow!("Claude settings must contain an object"))?;
    let mut changed = false;
    for (key, value) in defaults
        .as_object()
        .ok_or_else(|| anyhow!("Claude settings must contain an object"))?
    {
        if let Some(def) = value.as_object() {
            let cur = obj.entry(key.clone()).or_insert_with(|| json!({}));
            let cm = cur
                .as_object_mut()
                .ok_or_else(|| anyhow!("project Claude settings {} must contain an object", key))?;
            for (name, item) in def {
                if !cm.contains_key(name) {
                    cm.insert(name.clone(), item.clone());
                    changed = true
                } else if let Some(items) = item.as_array() {
                    let a = cm.get_mut(name).unwrap().as_array_mut().ok_or_else(|| {
                        anyhow!(
                            "project Claude settings {}.{} must contain an array",
                            key,
                            name
                        )
                    })?;
                    for v in items {
                        if !a.contains(v) {
                            a.push(v.clone());
                            changed = true
                        }
                    }
                }
            }
        } else if !obj.contains_key(key) {
            obj.insert(key.clone(), value.clone());
            changed = true
        }
    }
    if changed {
        json_text(&current)
    } else {
        Ok(existing.to_owned())
    }
}
fn merge_codex(existing: &str, canonical: &str) -> Result<String> {
    let cur: toml::Table = toml::from_str(existing).context("project Codex config is malformed")?;
    let defs: toml::Table = toml::from_str(canonical)?;
    let mut add = Vec::new();
    for (k, v) in defs {
        if !k
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
            || !matches!(
                v,
                toml::Value::String(_) | toml::Value::Integer(_) | toml::Value::Boolean(_)
            )
        {
            bail!("harness defaults must use scalar top-level TOML keys")
        }
        if !cur.contains_key(&k) {
            add.push(format!("{} = {}", k, v))
        }
    }
    if add.is_empty() {
        Ok(existing.into())
    } else {
        Ok(format!("{}\n\n{}", add.join("\n"), existing))
    }
}
fn retired(handler: &Value, event: &str, claude: bool) -> bool {
    if handler["type"] != "command" {
        return false;
    }
    if claude {
        if handler["command"] != "python3" {
            return false;
        }
        let a = &handler["args"];
        return *a
            == json!([
                "-B",
                "${CLAUDE_PROJECT_DIR}/.roblox-harness/claude/hooks/adapter.py",
                "--host",
                "claude",
                "--event",
                event,
                "--hook-scope",
                "project"
            ])
            || *a
                == json!([
                    "-B",
                    "${CLAUDE_PROJECT_DIR}/shared/gates/harness_gate.py",
                    "--host",
                    "claude",
                    "--event",
                    event
                ]);
    }
    let suffix = format!("--host codex --event {} --hook-scope project", event);
    let mut known = Vec::new();
    for prefix in ["", "rblx-harness/"] {
        known.push(format!("PYTHONDONTWRITEBYTECODE=1 python3 \"$(git rev-parse --show-toplevel)/{}openai/hooks/adapter.py\" {}",prefix,suffix));
        known.push(format!("powershell.exe -NoProfile -Command \"$root = git rev-parse --show-toplevel; & py -3 -B (Join-Path $root '{}') {}\"",format!("{}openai/hooks/adapter.py",prefix).replace('/',"\\"),suffix));
    }
    let commands: Vec<_> = ["command", "commandWindows", "command_windows"]
        .iter()
        .filter_map(|k| handler.get(*k))
        .collect();
    !commands.is_empty()
        && commands
            .iter()
            .all(|v| v.as_str().map_or(false, |s| known.iter().any(|x| x == s)))
}
fn policy(entry: &Value) -> bool {
    let cmd = entry["hooks"][0]["command"].as_str().unwrap_or("");
    let Ok(args) = shell_words::split(cmd) else {
        return false;
    };
    if args.len() != 3
        || args[0] != "python3"
        || args[1] != "-B"
        || !args[2]
            .replace('\\', "/")
            .ends_with("/openai/hooks/command_policy.py")
    {
        return false;
    }
    let expected = json!({"matcher":"^Bash$","hooks":[{"type":"command","command":format!("python3 -B {}",sh_quote(&args[2])),"commandWindows":format!("py -3 -B \"{}\"",args[2].replace('"',"\\\"")),"timeout":5}]});
    *entry == expected
}
fn migrate_hooks(doc: &mut Value, claude: bool) -> Result<bool> {
    let obj = doc
        .as_object_mut()
        .ok_or_else(|| anyhow!("project hooks must contain an object"))?;
    let Some(hooks) = obj.get_mut("hooks") else {
        return Ok(false);
    };
    let hm = hooks
        .as_object_mut()
        .ok_or_else(|| anyhow!("project hooks must contain a hooks object"))?;
    let mut changed = false;
    let keys: Vec<_> = hm.keys().cloned().collect();
    for event in keys {
        let entries = hm[&event]
            .as_array()
            .ok_or_else(|| anyhow!("project hook entries must be arrays"))?
            .clone();
        let mut out = Vec::new();
        for mut entry in entries {
            if !claude && event == "PreToolUse" && policy(&entry) {
                changed = true;
                continue;
            }
            let hs = entry
                .get_mut("hooks")
                .and_then(Value::as_array_mut)
                .ok_or_else(|| anyhow!("project hook entry must contain a hooks array"))?;
            let before = hs.len();
            hs.retain(|h| !retired(h, &event, claude));
            changed |= before != hs.len();
            if !hs.is_empty() {
                out.push(entry)
            }
        }
        if out.is_empty() {
            hm.remove(&event);
        } else {
            hm.insert(event, Value::Array(out));
        }
    }
    if claude && hm.is_empty() && changed {
        obj.remove("hooks");
    }
    Ok(changed)
}
fn sh_quote(s: &str) -> String {
    if s.is_empty() {
        return "''".into();
    }
    if s.bytes()
        .all(|c| c.is_ascii_alphanumeric() || b"_@%+=:,./-".contains(&c))
    {
        return s.into();
    }
    format!("'{}'", s.replace('\'', "'\"'\"'"))
}
fn hook_command(argv: &[String]) -> String {
    if cfg!(windows) {
        use base64::Engine;
        let expression = format!(
            "& {}",
            argv.iter()
                .map(|s| format!("'{}'", s.replace('\'', "''")))
                .collect::<Vec<_>>()
                .join(" ")
        );
        let bytes: Vec<u8> = expression
            .encode_utf16()
            .flat_map(u16::to_le_bytes)
            .collect();
        format!(
            "powershell.exe -NoProfile -EncodedCommand {}",
            base64::engine::general_purpose::STANDARD.encode(bytes)
        )
    } else {
        argv.iter()
            .map(|s| sh_quote(s))
            .collect::<Vec<_>>()
            .join(" ")
    }
}
fn installed_cleanup(entry: &Value) -> bool {
    let command = match entry["hooks"][0]["command"].as_str() {
        Some(s) => s,
        None => return false,
    };
    let Ok(mut args) = shell_words::split(command) else {
        return false;
    };
    if cfg!(windows)
        && args.len() == 4
        && args[..3] == ["powershell.exe", "-NoProfile", "-EncodedCommand"]
    {
        use base64::Engine;
        let Ok(bytes) = base64::engine::general_purpose::STANDARD.decode(&args[3]) else {
            return false;
        };
        if bytes.len() % 2 != 0 {
            return false;
        }
        let words: Vec<u16> = bytes
            .chunks_exact(2)
            .map(|x| u16::from_le_bytes([x[0], x[1]]))
            .collect();
        let Ok(expr) = String::from_utf16(&words) else {
            return false;
        };
        let re = regex::Regex::new(r"'((?:[^']|'')*)'").unwrap();
        args = re
            .captures_iter(&expr)
            .map(|m| m[1].replace("''", "'"))
            .collect();
    }
    let native = args.len() == 3 && (args[1] == "hook" || args[1] == "hooks") && args[2] == "coord";
    let python = args.len() == 4
        && args[1] == "-B"
        && args[3] == "hook"
        && args[2].replace('\\', "/").ends_with("/tools/coord.py")
        && regex::Regex::new(r"(?i)^python(?:[0-9]+(?:\.[0-9]+)*)?(?:\.exe)?$")
            .unwrap()
            .is_match(args[0].replace('\\', "/").rsplit('/').next().unwrap_or(""));
    (native || python)
        && *entry == json!({"hooks":[{"type":"command","command":hook_command(&args),"timeout":5}]})
}
fn coord_hooks(p: &Path) -> Result<()> {
    let raw = text(p);
    let mut doc: Value = if raw.trim().is_empty() {
        json!({})
    } else {
        serde_json::from_str(&raw)?
    };
    let obj = doc
        .as_object_mut()
        .ok_or_else(|| anyhow!("project hooks must contain an object"))?;
    let hm = obj
        .entry("hooks")
        .or_insert_with(|| json!({}))
        .as_object_mut()
        .ok_or_else(|| anyhow!("project hooks must contain an object"))?;
    let command = hook_command(&[
        std::env::current_exe()?.to_string_lossy().into_owned(),
        "hook".into(),
        "coord".into(),
    ]);
    let entry = json!({"hooks":[{"type":"command","command":command,"timeout":5}]});
    let mut changed = false;
    for event in ["SubagentStop", "SessionEnd"] {
        let arr = hm
            .entry(event)
            .or_insert_with(|| json!([]))
            .as_array_mut()
            .ok_or_else(|| anyhow!("project hook entries must contain hooks arrays"))?;
        if arr.iter().any(|x| !x.is_object() || !x["hooks"].is_array()) {
            bail!("project hook entries must contain hooks arrays");
        }
        let old = arr.clone();
        arr.retain(|x| !installed_cleanup(x));
        arr.push(entry.clone());
        changed |= *arr != old;
    }
    if changed {
        put_json(p, &doc)?;
    }
    Ok(())
}
fn support(project: &Path, checkout: bool) -> Result<()> {
    let h = harness();
    for host in ["codex", "claude"] {
        let root = project.join(if host == "codex" { ".codex" } else { ".claude" });
        for name in AGENTS {
            let ext = if host == "codex" { "toml" } else { "md" };
            let source = h
                .join(if host == "codex" {
                    "openai/agents"
                } else {
                    "anthropic/agents"
                })
                .join(format!("{}.{}", name, ext));
            copy(
                &source,
                &root.join("agents").join(format!("{}.{}", name, ext)),
            )?;
        }
        if host == "codex" {
            let hp = root.join("hooks.json");
            if hp.exists() {
                let mut d: Value = serde_json::from_str(&text(&hp))?;
                if migrate_hooks(&mut d, false)? {
                    if d == json!({"hooks":{}}) {
                        fs::remove_file(&hp)?
                    } else {
                        put_json(&hp, &d)?
                    }
                }
            }
            let p = root.join("config.toml");
            put(
                &p,
                &merge_codex(
                    &text(&p),
                    &fs::read_to_string(h.join("openai/config/project.toml"))?,
                )?,
            )?;
            coord_hooks(&hp)?;
        } else {
            let p = root.join("settings.json");
            let raw = text(&p);
            let mut d: Value = if raw.trim().is_empty() {
                json!({})
            } else {
                serde_json::from_str(&raw).context("project Claude settings are malformed")?
            };
            let migrated = if migrate_hooks(&mut d, true)? {
                json_text(&d)?
            } else {
                raw
            };
            let merged = merge_claude(
                &migrated,
                &fs::read_to_string(h.join("anthropic/config/settings.json"))?,
            )?;
            put(&p, &merged)?;
            coord_hooks(&p)?;
        }
        let skills = if host == "codex" {
            project.join(".agents/skills")
        } else {
            root.join("skills")
        };
        fs::create_dir_all(&skills)?;
        if !checkout {
            remove(&skills.join("rblx-new-game"))?
        }
        for name in SKILLS
            .iter()
            .copied()
            .chain(checkout.then_some("rblx-new-game"))
        {
            link(
                &h.join("shared/skills").join(name),
                &skills.join(name),
                true,
                true,
            )?;
        }
    }
    let rules = project.join(".claude/rules");
    remove(&rules.join("rblx-harness-delegation.md"))?;
    if rules.is_dir() && fs::read_dir(&rules)?.next().is_none() {
        fs::remove_dir(rules)?
    }
    Ok(())
}
fn render(project: &Path, manifest: &Value, places: &[String], assets: &[String]) -> Result<()> {
    let h = harness();
    let skill = h.join("shared/skills/rblx-new-game");
    let path = project.join("AGENTS.md");
    let existing = text(&path);
    let pattern = regex::Regex::new(&format!(
        "(?s){}.*?{}",
        regex::escape(GB),
        regex::escape(GE)
    ))?;
    let previous = pattern
        .find(&existing)
        .map_or(existing.as_str(), |m| m.as_str());
    let ptn = regex::Regex::new(r"(?ms)^## places\s*\n(.*?)(?:^## |<!-- END|\z)")?;
    let mut mapping = BTreeMap::new();
    if let Some(m) = ptn.captures(previous) {
        for line in m[1].lines() {
            if let Some((n, id)) = line.trim().split_once('|') {
                if !id.is_empty()
                    && id.bytes().all(|b| b.is_ascii_digit())
                    && id.bytes().any(|b| b != b'0')
                {
                    mapping.insert(n.to_string(), id.to_string());
                }
            }
        }
    }
    let places = places
        .iter()
        .map(|p| {
            mapping
                .get(p)
                .map_or_else(|| format!("- {}", p), |id| format!("{}|{}", p, id))
        })
        .collect::<Vec<_>>()
        .join("\n");
    let field = |name: &str, default: &str| {
        manifest[name]
            .as_str()
            .filter(|s| !s.is_empty())
            .unwrap_or(default)
            .to_string()
    };
    let gameplay = field("gameplay", "Not recorded.");
    let summary = format!(
        "Gameplay loop: {}\n\nServices: {}\n\nControllers: {}",
        gameplay,
        field("services", "none"),
        field("controllers", "none")
    );
    let template = fs::read_to_string(skill.join("AGENTS.md"))?
        .replace(
            "{{RULES}}",
            fs::read_to_string(h.join("shared/CORE.md"))?.trim(),
        )
        .replace("{{SUMMARY}}", &summary)
        .replace("{{PLACES}}", &places)
        .replace("{{ASSETS}}", if assets.is_empty() { "none" } else { "" });
    let rendered = if assets.is_empty() {
        template
    } else {
        fs::read_to_string(skill.join("AGENTS.md"))?
            .replace(
                "{{RULES}}",
                fs::read_to_string(h.join("shared/CORE.md"))?.trim(),
            )
            .replace("{{SUMMARY}}", &summary)
            .replace("{{PLACES}}", &places)
            .replace("{{ASSETS}}", &assets.join(", "))
    };
    let output = if existing.contains(GB) || existing.contains(GE) {
        if existing.matches(GB).count() != 1
            || existing.matches(GE).count() != 1
            || !pattern.is_match(&existing)
        {
            bail!("AGENTS.md has malformed harness guidance markers")
        }
        pattern
            .replace(&existing, |_: &regex::Captures| rendered.trim().to_string())
            .to_string()
    } else {
        format!(
            "{}{}{}\n",
            rendered.trim(),
            if existing.trim().is_empty() {
                ""
            } else {
                "\n\n"
            },
            existing.trim()
        )
    };
    put(&path, &output)?;
    let readme = project.join("README.md");
    if !readme.exists() {
        put(
            &readme,
            &fs::read_to_string(skill.join("README.md"))?
                .replace(
                    "{{PROJECT}}",
                    &project.file_name().unwrap_or_default().to_string_lossy(),
                )
                .replace("{{GAMEPLAY}}", &gameplay),
        )?
    }
    let path = project.join("CLAUDE.md");
    let existing = text(&path);
    let canonical = fs::read_to_string(h.join("CLAUDE.md"))?;
    let canonical = canonical.trim();
    let block = format!("{}\n{}\n{}", CB, canonical, CE);
    let out = if existing.contains(CB) || existing.contains(CE) {
        if existing.matches(CB).count() != 1
            || existing.matches(CE).count() != 1
            || existing.find(CB) > existing.find(CE)
        {
            bail!("CLAUDE.md has malformed harness import markers")
        }
        let a = existing.find(CB).unwrap();
        let b = existing.find(CE).unwrap() + CE.len();
        format!("{}{}{}", &existing[..a], block, &existing[b..])
    } else if existing.contains(canonical) {
        existing
    } else if let Some(m) = regex::Regex::new(r"(?m)^[ \t]*@AGENTS\.md[ \t]*$")?.find(&existing) {
        format!(
            "{}{}{}",
            &existing[..m.start()],
            block,
            &existing[m.end()..]
        )
    } else {
        format!(
            "{}{}{}\n",
            block,
            if existing.trim().is_empty() {
                ""
            } else {
                "\n\n"
            },
            existing.trim()
        )
    };
    put(&path, &out)?;
    Ok(())
}
fn ensure_toolchain(root: &Path) -> Result<()> {
    if std::env::var("RBLX_HARNESS_TESTING").as_deref() != Ok("1") {
        crate::toolchain::install(root)?;
    }
    Ok(())
}
fn install(project: &Path, manifest: &mut Value) -> Result<()> {
    let project = fs::canonicalize(project).context("project directory is absent")?;
    if !project.join("rblx-harness").exists() {
        bail!("project has no rblx-harness submodule")
    }
    let places: Vec<String> = manifest["places"]
        .as_array()
        .filter(|a| !a.is_empty())
        .ok_or_else(|| anyhow!("manifest has no places"))?
        .iter()
        .map(|v| {
            v.as_str()
                .map(str::to_owned)
                .ok_or_else(|| anyhow!("invalid place name"))
        })
        .collect::<Result<_>>()?;
    ensure_toolchain(&harness())?;
    let legacy = project.join("plugin");
    let plugins = project.join("plugins");
    if fs::symlink_metadata(&legacy).is_ok() {
        if fs::symlink_metadata(&plugins).is_ok() {
            bail!("both legacy plugin/ and plugins/ exist; merge them before setup")
        }
        if fs::symlink_metadata(&legacy)?.file_type().is_symlink() || !legacy.is_dir() {
            bail!("legacy plugin/ must be a regular directory")
        }
        fs::rename(legacy, &plugins)?
    }
    let raw = manifest
        .get("assets")
        .filter(|v| !v.is_null())
        .cloned()
        .unwrap_or(json!([]));
    let mut selected = BTreeSet::new();
    for v in raw
        .as_array()
        .ok_or_else(|| anyhow!("manifest assets must be a list of names"))?
    {
        let s = v
            .as_str()
            .ok_or_else(|| anyhow!("manifest assets must be a list of names"))?;
        let n = if s == "plugin" { "plugins" } else { s };
        if !ORDER.contains(&n) {
            bail!("unknown harness asset: {}", s)
        }
        selected.insert(n.to_string());
    }
    if plugins.is_dir() {
        selected.insert("plugins".into());
    }
    let assets: Vec<String> = ORDER
        .iter()
        .filter(|x| selected.contains(**x))
        .map(|x| x.to_string())
        .collect();
    manifest["assets"] = json!(assets);
    managed(
        &project.join(".gitignore"),
        "# BEGIN rblx-new-game",
        "# END rblx-new-game",
        &[
            "/.agents/",
            "/.claude/",
            "/.codex/",
            "/.serena/",
            "/.roblox",
            ".DS_Store",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect::<Vec<_>>(),
    )?;
    let marker = project.join(".roblox");
    if let Ok(m) = fs::symlink_metadata(&marker) {
        if m.file_type().is_symlink() || !m.is_file() {
            bail!(".roblox must be a regular file")
        }
    } else {
        put(&marker, "")?
    }
    for p in &places {
        fs::create_dir_all(
            project
                .join("places")
                .join(p)
                .join("src/ServerScriptService/Services"),
        )?;
        fs::create_dir_all(
            project
                .join("places")
                .join(p)
                .join("src/StarterPlayer/StarterPlayerScripts/Controllers"),
        )?;
    }
    let base = project.join("rblx-harness/packages");
    let dest = project.join("shared/src");
    let mut linked = BTreeMap::new();
    for (asset, name, sub, replace) in [
        ("packages", "packages", "ReplicatedStorage/Packages", true),
        ("packages", "modules", "ServerScriptService/Modules", true),
        ("services", "types", "ReplicatedStorage/Types", false),
        (
            "services",
            "services",
            "ServerScriptService/Services",
            false,
        ),
        (
            "controllers",
            "controllers",
            "StarterPlayer/StarterPlayerScripts/Controllers",
            false,
        ),
    ] {
        if selected.contains(asset) {
            linked.insert(name, tree(&base.join(sub), &dest.join(sub), replace)?);
        }
    }
    if selected.contains("plugins") {
        if let Ok(m) = fs::symlink_metadata(&plugins) {
            if m.file_type().is_symlink() || !m.is_dir() {
                bail!("plugins/ must be a regular directory")
            }
        }
        fs::create_dir_all(&plugins)?;
        if fs::read_dir(&plugins)?.next().is_none() {
            put(&plugins.join(".gitkeep"), "")?
        }
    }
    support(&project, false)?;
    render(&project, manifest, &places, &assets)?;
    println!(
        "setup-project|READY|places={}|assets={}",
        places.join(","),
        if assets.is_empty() {
            "none".into()
        } else {
            assets.join(",")
        }
    );
    for (name, c) in linked {
        println!(
            "links|{}|linked={}|exact={}|preserved={}",
            name, c["linked"], c["exact"], c["preserved"]
        )
    }
    Ok(())
}
fn add_missing(cur: &mut Value, defaults: &Value, label: &str) -> Result<bool> {
    let m = cur
        .as_object_mut()
        .ok_or_else(|| anyhow!("{} must contain an object", label))?;
    let mut changed = false;
    for (k, v) in defaults.as_object().unwrap() {
        let name = format!("{}.{}", label, k);
        if !m.contains_key(k) {
            m.insert(k.clone(), v.clone());
            changed = true
        } else if v.is_object() {
            changed |= add_missing(m.get_mut(k).unwrap(), v, &name)?
        } else if let Some(values) = v.as_array() {
            let a = m
                .get_mut(k)
                .unwrap()
                .as_array_mut()
                .ok_or_else(|| anyhow!("{} must contain an array", name))?;
            for x in values {
                if !a.contains(x) {
                    a.push(x.clone());
                    changed = true
                }
            }
        }
    }
    Ok(changed)
}
fn permissions(args: &[OsString]) -> Result<i32> {
    let mut install_profile = false;
    let mut relink = false;
    for arg in args {
        match arg.to_str().unwrap_or("") {
            "--install" => install_profile = true,
            "--relink" => relink = true,
            "--help" | "-h" => {
                println!("usage: permissions [--install | --relink]");
                return Ok(0);
            }
            _ => bail!("unrecognized argument: {}", arg.to_string_lossy()),
        }
    }
    if install_profile && relink {
        bail!("--install cannot be combined with --relink");
    }
    if relink {
        return run(&[
            OsString::from("--project"),
            std::env::current_dir()?.into_os_string(),
            OsString::from("--from-state"),
        ]);
    }
    let home = std::env::var_os("CLAUDE_CONFIG_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join(".claude"));
    let home = if home.starts_with("~") {
        dirs::home_dir()
            .unwrap_or_default()
            .join(home.strip_prefix("~")?)
    } else {
        home
    };
    let p = home.join("rblx-harness-roblox.json");
    if install_profile {
        let exists = p.exists();
        let mut cur: Value = if exists {
            serde_json::from_str(&fs::read_to_string(&p)?)?
        } else {
            json!({})
        };
        let defs = json!({"sandbox":{"enabled":true,"filesystem":{"allowWrite":["~/.cache/harness"]},"network":{"allowedDomains":["raw.githubusercontent.com","github.com","codeload.github.com","objects.githubusercontent.com","release-assets.githubusercontent.com","localhost","127.0.0.1"]}}});
        let changed = add_missing(&mut cur, &defs, "profile")?;
        if changed {
            put(&p, &json_text(&cur)?)?;
        }
        println!(
            "permissions-profile|{}|optional; start Claude Code with --settings {}",
            if !changed {
                "PRESENT"
            } else if exists {
                "UPDATED"
            } else {
                "INSTALLED"
            },
            p.display()
        );
    } else {
        println!(
            "permissions-profile|{}|optional; default permissions supported",
            if p.is_file() { "PRESENT" } else { "ABSENT" }
        );
    }
    Ok(0)
}
fn argon_ensure(project: &Path) -> Result<Option<std::process::Output>> {
    use std::io::Read;
    use std::process::Stdio;
    use std::time::{Duration, Instant};
    let mut child = Command::new(std::env::current_exe()?)
        .arg("--root")
        .arg(project)
        .args(["argon", "ensure"])
        .current_dir(project)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let mut stdout = child.stdout.take().unwrap();
    let mut stderr = child.stderr.take().unwrap();
    let out = std::thread::spawn(move || {
        let mut v = Vec::new();
        let _ = stdout.read_to_end(&mut v);
        v
    });
    let err = std::thread::spawn(move || {
        let mut v = Vec::new();
        let _ = stderr.read_to_end(&mut v);
        v
    });
    let deadline = Instant::now() + Duration::from_secs(10);
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if Instant::now() >= deadline {
            child.kill()?;
            child.wait()?;
            return Ok(None);
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    Ok(Some(std::process::Output {
        status,
        stdout: out.join().unwrap_or_default(),
        stderr: err.join().unwrap_or_default(),
    }))
}
pub fn run(args: &[OsString]) -> Result<i32> {
    if let Some(first) = args.first().and_then(|a| a.to_str()) {
        match first {
            "permissions" | "claude-permissions" | "anthropic-permissions" => {
                return permissions(&args[1..])
            }
            "codex-permissions" | "openai-permissions" => return codex_permissions(&args[1..]),
            _ => {}
        }
    }
    let mut project = None;
    let mut manifest = None;
    let mut from = false;
    let mut checkout = false;
    let mut it = args.iter();
    while let Some(a) = it.next() {
        match a.to_str().unwrap_or("") {
            "--project" => {
                project = Some(PathBuf::from(
                    it.next()
                        .ok_or_else(|| anyhow!("--project requires a value"))?,
                ))
            }
            "--manifest" => {
                manifest = Some(PathBuf::from(
                    it.next()
                        .ok_or_else(|| anyhow!("--manifest requires a value"))?,
                ))
            }
            "--from-state" => from = true,
            "--harness" => checkout = true,
            "--help" | "-h" => {
                println!("usage: setup (--project PROJECT | --harness) [--manifest MANIFEST] [--from-state]");
                return Ok(0);
            }
            _ => bail!("unrecognized argument: {}", a.to_string_lossy()),
        }
    }
    if checkout {
        if project.is_some() || manifest.is_some() || from {
            bail!("--harness cannot be combined with project manifest options");
        }
        let root = harness();
        ensure_toolchain(&root)?;
        support(&root, true)?;
        println!(
            "setup-harness|READY|hosts=codex,claude|agents={}|skills={},rblx-new-game",
            AGENTS.join(","),
            SKILLS.join(",")
        );
        return Ok(0);
    }
    let project =
        fs::canonicalize(project.ok_or_else(|| anyhow!("--project or --harness is required"))?)?;
    if !from && manifest.is_none() {
        bail!("use --from-state or --manifest");
    }
    let default = project.join("manifest.json");
    let path = manifest.unwrap_or_else(|| default.clone());
    let mut doc: Value = serde_json::from_str(
        &fs::read_to_string(&path).with_context(|| format!("cannot read {}", path.display()))?,
    )?;
    if !doc.is_object() {
        bail!("{} must contain an object", path.display());
    }
    install(&project, &mut doc)?;
    if fs::canonicalize(&path).ok() == fs::canonicalize(&default).ok() {
        put_json(&path, &doc)?;
    }
    if std::env::var("RBLX_HARNESS_TESTING").as_deref() != Ok("1") {
        match argon_ensure(&project) {
            Ok(Some(o)) if o.status.success() => {
                println!("argon|READY|registered project and started supervisor")
            }
            Ok(Some(o)) => {
                let detail = if o.stderr.is_empty() {
                    o.stdout
                } else {
                    o.stderr
                };
                let s = String::from_utf8_lossy(&detail);
                println!(
                    "argon|WAITING|{}",
                    if s.trim().is_empty() {
                        "start `harness argon ensure` to retry"
                    } else {
                        s.trim()
                    }
                );
            }
            Ok(None) => println!("argon|WAITING|command timed out after 10 seconds"),
            Err(e) => println!("argon|WAITING|{}", e),
        }
    }
    Ok(0)
}

/// Install or inspect the optional Codex permission profile.
pub fn codex_permissions(args: &[OsString]) -> Result<i32> {
    const BEGIN: &str = "# BEGIN optional rblx-harness Roblox profile";
    const END: &str = "# END optional rblx-harness Roblox profile";
    const PROFILE: &str = r#"# BEGIN optional rblx-harness Roblox profile
[permissions.Roblox]
extends = ":workspace"

[permissions.Roblox.filesystem]
"~/.cache/harness" = "write"
"~/.cache/harness/creator-docs/.git" = "write"

[permissions.Roblox.filesystem.":workspace_roots"]
".agents" = "write"
".codex" = "write"
".git" = "write"
"rblx-harness/tools/bin" = "write"
"tools/bin" = "write"

[permissions.Roblox.network]
enabled = true

[permissions.Roblox.network.domains]
"raw.githubusercontent.com" = "allow"
"github.com" = "allow"
"codeload.github.com" = "allow"
"objects.githubusercontent.com" = "allow"
"release-assets.githubusercontent.com" = "allow"
"localhost" = "allow"
"127.0.0.1" = "allow"
# END optional rblx-harness Roblox profile"#;
    let mut install = false;
    let mut relink = false;
    for arg in args {
        match arg.to_str().unwrap_or("") {
            "--install" => install = true,
            "--relink" => relink = true,
            "--help" | "-h" => {
                println!("usage: permissions [--install | --relink]");
                return Ok(0);
            }
            _ => bail!("unrecognized argument: {}", arg.to_string_lossy()),
        }
    }
    if install && relink {
        bail!("--install cannot be combined with --relink");
    }
    if args.iter().any(|a| a == "--relink") {
        return run(&[
            OsString::from("--project"),
            std::env::current_dir()?.into_os_string(),
            OsString::from("--from-state"),
        ]);
    }
    let home = std::env::var_os("CODEX_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join(".codex"));
    let home = if home.starts_with("~") {
        dirs::home_dir()
            .unwrap_or_default()
            .join(home.strip_prefix("~")?)
    } else {
        home
    };
    let path = home.join("config.toml");
    let current = text(&path);
    let present = regex::Regex::new(r"(?m)^\s*\[permissions\.Roblox\]\s*$")?;
    if !args.iter().any(|a| a == "--install") {
        println!(
            "permissions-profile|{}|optional; Full Access supported",
            if present.is_match(&current) {
                "PRESENT"
            } else {
                "ABSENT"
            }
        );
        return Ok(0);
    }
    let managed = regex::Regex::new(&format!(
        r"(?s){}.*?{}\s*",
        regex::escape(BEGIN),
        regex::escape(END)
    ))?;
    let unmanaged = managed.replace_all(&current, "").trim().to_string();
    if present.is_match(&unmanaged) {
        let header = regex::Regex::new(
            r#"(?m)^\s*\[permissions\.Roblox\.filesystem\.":workspace_roots"\]\s*$"#,
        )?;
        let mut updated = current.clone();
        let mut changed = false;
        if let Some(h) = header.find(&current) {
            let following = regex::Regex::new(r"(?m)^\s*\[")?;
            let end = following
                .find(&current[h.end()..])
                .map_or(current.len(), |m| h.end() + m.start());
            let section = &current[h.start()..end];
            let mut insertion = String::new();
            for name in [".agents", ".codex"] {
                let p = regex::Regex::new(&format!(r#"(?m)^\s*"{}"\s*="#, regex::escape(name)))?;
                if !p.is_match(section) {
                    insertion.push_str(&format!("\n\"{}\" = \"write\"", name));
                }
            }
            if !insertion.is_empty() {
                updated.insert_str(h.end(), &insertion);
                changed = true;
            }
        }
        if changed {
            put(&path, &updated)?;
            println!("permissions-profile|UPDATED|runtime directories allowed; Full Access remains supported");
        } else {
            println!("permissions-profile|PRESENT|optional; Full Access remains supported");
        }
    } else {
        put(
            &path,
            &format!(
                "{}{}{}\n",
                unmanaged,
                if unmanaged.is_empty() { "" } else { "\n\n" },
                PROFILE
            ),
        )?;
        println!(
            "permissions-profile|INSTALLED|optional; no profile selection or restart required"
        );
    }
    Ok(0)
}
