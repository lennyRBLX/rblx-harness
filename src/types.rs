use anyhow::{anyhow, Context, Result};
use regex::Regex;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant, SystemTime};
use walkdir::WalkDir;

fn hash(bytes: impl AsRef<[u8]>) -> String {
    hex::encode(Sha256::digest(bytes.as_ref()))
}
fn re(s: &str) -> Regex {
    Regex::new(s).expect("valid regular expression")
}
fn canonical(path: &Path) -> PathBuf {
    if let Ok(p) = fs::canonicalize(path) {
        return p;
    }
    let abs = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_default().join(path)
    };
    let mut suffix = Vec::new();
    let mut p = abs.as_path();
    while !p.exists() {
        if let Some(n) = p.file_name() {
            suffix.push(n.to_os_string());
        } else {
            break;
        }
        match p.parent() {
            Some(v) => p = v,
            None => break,
        }
    }
    let mut out = fs::canonicalize(p).unwrap_or_else(|_| p.to_path_buf());
    for part in suffix.into_iter().rev() {
        if part == ".." {
            out.pop();
        } else if part != "." {
            out.push(part);
        }
    }
    out
}
fn relative(path: &Path, root: &Path) -> String {
    let p = canonical(path);
    let r = canonical(root);
    let a: Vec<_> = p.components().collect();
    let b: Vec<_> = r.components().collect();
    let common = a.iter().zip(&b).take_while(|(x, y)| x == y).count();
    let mut out = PathBuf::new();
    for _ in common..b.len() {
        out.push("..");
    }
    for c in &a[common..] {
        out.push(c.as_os_str());
    }
    out.to_string_lossy().replace('\\', "/")
}
fn s<'a>(v: &'a Value, k: &str) -> &'a str {
    v.get(k).and_then(Value::as_str).unwrap_or("")
}
fn json_sorted(v: &Value) -> String {
    fn sort(v: &Value) -> Value {
        match v {
            Value::Object(o) => {
                let mut keys: Vec<_> = o.keys().collect();
                keys.sort();
                let mut m = serde_json::Map::new();
                for k in keys {
                    m.insert(k.clone(), sort(&o[k]));
                }
                Value::Object(m)
            }
            Value::Array(a) => Value::Array(a.iter().map(sort).collect()),
            _ => v.clone(),
        }
    }
    let text = serde_json::to_string(&sort(v)).unwrap();
    let mut out = String::with_capacity(text.len());
    for ch in text.chars() {
        if ch.is_ascii() {
            out.push(ch);
        } else {
            let mut buf = [0u16; 2];
            for unit in ch.encode_utf16(&mut buf).iter() {
                use std::fmt::Write as _;
                let _ = write!(out, "\\u{unit:04x}");
            }
        }
    }
    out
}
fn cache_json(v: &Value) -> String {
    format!("{}\n", json_sorted(v))
}
fn atomic(path: &Path, data: &[u8]) -> Result<()> {
    let dir = path.parent().context("missing parent")?;
    fs::create_dir_all(dir)?;
    let mut file = tempfile::Builder::new()
        .prefix(".type_cache_")
        .tempfile_in(dir)?;
    file.write_all(data)?;
    file.as_file().sync_all()?;
    file.persist(path).map_err(|e| e.error)?;
    Ok(())
}

// Mask in bytes rather than characters: every slice boundary remains a UTF-8 boundary
// while offsets continue to refer to the original source, including non-ASCII text.
fn mask(src: &str) -> String {
    let b = src.as_bytes();
    let mut o = b.to_vec();
    let mut i = 0;
    while i < b.len() {
        let start = i;
        let mut end = i;
        let long = |pos: usize| -> Option<(usize, usize)> {
            if b.get(pos) != Some(&b'[') {
                return None;
            }
            let mut n = pos + 1;
            while b.get(n) == Some(&b'=') {
                n += 1;
            }
            if b.get(n) == Some(&b'[') {
                Some((n + 1, n - pos - 1))
            } else {
                None
            }
        };
        let long_at = if b.get(i..i + 2) == Some(b"--") {
            long(i + 2)
        } else {
            long(i)
        };
        if let Some((p, n)) = long_at {
            let close = format!("]{}]", "=".repeat(n));
            end = src[p..]
                .find(&close)
                .map(|x| p + x + close.len())
                .unwrap_or(b.len());
        } else if b.get(i..i + 2) == Some(b"--") {
            end = src[i..].find('\n').map(|x| i + x).unwrap_or(b.len());
        } else if matches!(b[i], b'\'' | b'"' | b'`') {
            let q = b[i];
            end = i + 1;
            while end < b.len() {
                if b[end] == b'\\' {
                    end = (end + 2).min(b.len());
                } else if b[end] == q {
                    end += 1;
                    break;
                } else {
                    end += 1;
                }
            }
        }
        if end > start {
            for x in &mut o[start..end] {
                if *x != b'\n' && *x != b'\r' {
                    *x = b' ';
                }
            }
            i = end;
        } else {
            i += 1;
        }
    }
    String::from_utf8(o).expect("mask is UTF-8")
}
#[derive(Clone)]
struct Decl {
    name: String,
    exported: bool,
    start: usize,
    end: usize,
    text: String,
    members: BTreeMap<String, String>,
}
fn format_decl(text: &str) -> String {
    text.trim()
        .lines()
        .map(|l| {
            let l = l.trim_end();
            let n = l.bytes().take_while(|b| *b == b' ').count();
            format!("{}{}{}", "\t".repeat(n / 4), " ".repeat(n % 4), &l[n..])
        })
        .collect::<Vec<_>>()
        .join("\n")
}
fn parse(src: &str) -> Vec<Decl> {
    let m = mask(src);
    let start_re = re(r"(?m)^(export[ \t]+)?type[ \t]+([A-Za-z_][A-Za-z0-9_]*)\b");
    let mut out = Vec::new();
    for cap in start_re.captures_iter(&m) {
        let mt = cap.get(0).unwrap();
        let eq = m[mt.end()..].find('=').map(|x| x + mt.end());
        let end = if let Some(eq) = eq {
            let b = m.as_bytes();
            let mut depths = [0i32; 3];
            let mut seen = false;
            let mut end = b.len();
            let mut i = eq + 1;
            while i < b.len() {
                match b[i] {
                    b'{' => {
                        depths[0] += 1;
                        seen = true
                    }
                    b'(' => {
                        depths[1] += 1;
                        seen = true
                    }
                    b'[' => {
                        depths[2] += 1;
                        seen = true
                    }
                    b'}' => {
                        depths[0] = (depths[0] - 1).max(0);
                        seen = true
                    }
                    b')' => {
                        depths[1] = (depths[1] - 1).max(0);
                        seen = true
                    }
                    b']' => {
                        depths[2] = (depths[2] - 1).max(0);
                        seen = true
                    }
                    b'\n' if depths == [0, 0, 0] => {
                        if !m[eq + 1..i].trim().is_empty() {
                            seen = true;
                        }
                        let next = m[i + 1..]
                            .trim_start_matches(|c| matches!(c, ' ' | '\t' | '\r' | '\n'))
                            .lines()
                            .next()
                            .unwrap_or("")
                            .trim();
                        if seen && !["|", "&", ",", "->"].iter().any(|p| next.starts_with(p)) {
                            end = i;
                            break;
                        }
                    }
                    c if !c.is_ascii_whitespace() => seen = true,
                    _ => {}
                }
                i += 1;
            }
            end
        } else {
            m[mt.end()..]
                .find('\n')
                .map(|x| x + mt.end())
                .unwrap_or(m.len())
        };
        let text = format_decl(&src[mt.start()..end]);
        if !text.contains('=') {
            continue;
        }
        let members = members(&text);
        out.push(Decl {
            name: cap[2].to_string(),
            exported: cap.get(1).is_some(),
            start: mt.start(),
            end,
            text,
            members,
        });
    }
    out
}
fn members(src: &str) -> BTreeMap<String, String> {
    let m = mask(src);
    let Some(eq) = m.find('=') else {
        return BTreeMap::new();
    };
    let Some(br) = m[eq + 1..].find('{').map(|x| x + eq + 1) else {
        return BTreeMap::new();
    };
    let mut d = [1i32, 0, 0];
    let mut begin = br + 1;
    let mut seg = Vec::new();
    for (i, c) in m.bytes().enumerate().skip(br + 1) {
        match c {
            b'{' => d[0] += 1,
            b'(' => d[1] += 1,
            b'[' => d[2] += 1,
            b'}' => {
                d[0] = (d[0] - 1).max(0);
                if d[0] == 0 {
                    seg.push(&src[begin..i]);
                    break;
                }
            }
            b')' => d[1] = (d[1] - 1).max(0),
            b']' => d[2] = (d[2] - 1).max(0),
            b',' if d == [1, 0, 0] => {
                seg.push(&src[begin..i]);
                begin = i + 1;
            }
            _ => {}
        }
    }
    let r = re(r#"^(?:\[\s*["']([^"']+)["']\s*\]|([A-Za-z_][A-Za-z0-9_]*))\s*:\s*(.+)$"#);
    let mut result = BTreeMap::new();
    for part in seg {
        let t = part
            .trim()
            .lines()
            .map(str::trim)
            .collect::<Vec<_>>()
            .join(" ");
        if let Some(c) = r.captures(t.trim()) {
            let name = c.get(1).or_else(|| c.get(2)).unwrap().as_str();
            result.insert(name.to_string(), format!("{}: {}", name, c[3].trim()));
        }
    }
    result
}
fn metadata(root: &Path, path: &Path) -> Option<Value> {
    let rel = relative(path, root);
    let logical_rel = path
        .strip_prefix(root)
        .ok()
        .map(|p| p.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|| rel.clone());
    let plugin = re(r"^plugins/([^/]+)/src/(.+)\.(?:luau|lua)$");
    if let Some(c) = plugin.captures(&logical_rel) {
        return Some(
            json!({"kind":"plugin","module":if &c[2]=="init" {""} else {&c[2]},"owner":&c[1],"path":rel,"place":"shared"}),
        );
    }
    let p = re(r"^(?:shared|places/([^/]+))/src/(.+)$");
    let c = p.captures(&logical_rel)?;
    let place = c.get(1).map(|x| x.as_str()).unwrap_or("shared");
    let logical = &c[2];
    let t = re(r"^ReplicatedStorage/Types/([^/]+)(?:/(.*))?\.(?:luau|lua)$");
    if let Some(c) = t.captures(logical) {
        let owner = &c[1];
        let module = match c.get(2) {
            Some(x) => format!("{}/{}", owner, x.as_str()),
            None => owner.to_string(),
        };
        return Some(
            json!({"kind":"feature","module":module,"owner":owner,"path":rel,"place":place}),
        );
    }
    for (mut kind, prefix) in [
        ("service", "ServerScriptService/Services/"),
        (
            "controller",
            "StarterPlayer/StarterPlayerScripts/Controllers/",
        ),
    ] {
        if let Some(tail) = logical.strip_prefix(prefix) {
            let parts: Vec<_> = tail.split('/').collect();
            let owner = if parts.len() == 1 {
                parts[0].rsplit_once('.').map(|x| x.0).unwrap_or(parts[0])
            } else {
                parts[0]
            };
            let mut module = parts[1..].join("/");
            for ext in [".luau", ".lua"] {
                if let Some(v) = module.strip_suffix(ext) {
                    module = v.to_string();
                    break;
                }
            }
            if module == "init" {
                module.clear();
            }
            let dir = path.parent()?;
            if (owner == "PlayerData"
                || (dir.join("Default.luau").exists() && dir.join("Development.luau").exists()))
                && matches!(
                    path.file_name()?.to_str()?,
                    "Default.luau" | "Development.luau" | "Typed.luau"
                )
            {
                kind = "data";
            }
            return Some(
                json!({"kind":kind,"module":module,"owner":owner,"path":rel,"place":place}),
            );
        }
    }
    None
}
fn qualify(meta: &Value, name: &str) -> String {
    let owner = s(meta, "owner");
    let module = s(meta, "module");
    if s(meta, "kind") == "data" {
        format!("PlayerData.{name}")
    } else if s(meta, "kind") == "feature" || module.is_empty() {
        format!("{owner}.{name}")
    } else {
        format!(
            "{owner}/{}.{name}",
            module.strip_suffix("/init").unwrap_or(module)
        )
    }
}
fn source_files(root: &Path) -> Vec<PathBuf> {
    let mut dirs = vec![
        root.join("shared/src"),
        root.join("places"),
        root.join("plugins"),
    ];
    let mut out = Vec::new();
    for base in dirs.drain(..) {
        if !base.is_dir() {
            continue;
        }
        for e in WalkDir::new(base)
            .follow_links(false)
            .into_iter()
            .filter_entry(|e| {
                !e.file_type().is_dir() || !e.file_name().to_string_lossy().starts_with('.')
            })
            .flatten()
        {
            if (e.file_type().is_file() || e.file_type().is_symlink() && e.path().is_file())
                && matches!(
                    e.path().extension().and_then(|x| x.to_str()),
                    Some("luau" | "lua")
                )
            {
                out.push(e.into_path());
            }
        }
    }
    out.sort();
    out
}
fn project_fingerprint(root: &Path) -> String {
    let mut h = Sha256::new();
    let mut files = fs::read_dir(root)
        .into_iter()
        .flatten()
        .flatten()
        .filter(|e| e.file_name().to_string_lossy().ends_with(".project.json"))
        .collect::<Vec<_>>();
    files.sort_by_key(|e| e.file_name());
    for f in files {
        h.update(f.file_name().to_string_lossy().as_bytes());
        h.update([0]);
        h.update(fs::read(f.path()).unwrap_or_else(|_| b"missing".to_vec()));
        h.update([0]);
    }
    hex::encode(h.finalize())
}
fn build_index(root: &Path, overlay: &BTreeMap<PathBuf, Option<String>>) -> Value {
    let mut parsed = read_parsed(root);
    build_index_cached(root, overlay, &mut parsed)
}
fn build_index_cached(
    root: &Path,
    overlay: &BTreeMap<PathBuf, Option<String>>,
    parsed: &mut Value,
) -> Value {
    let mut discovered = BTreeMap::new();
    for p in source_files(root) {
        if let Some(mut m) = metadata(root, &p) {
            if s(&m, "kind") == "data"
                && p.parent().is_some_and(|d| {
                    !d.join("Default.luau").exists() || !d.join("Development.luau").exists()
                })
            {
                m["kind"] = json!(if p.to_string_lossy().contains("/Controllers/") {
                    "controller"
                } else {
                    "service"
                });
            }
            discovered.insert(canonical(&p), m);
        }
    }
    for (p, c) in overlay {
        if c.is_none() {
            discovered.remove(p);
        } else if !discovered.contains_key(p) {
            if let Some(m) = metadata(root, p) {
                discovered.insert(p.clone(), m);
            }
        }
    }
    let mut defs = Vec::new();
    let mut access = Vec::new();
    let mut sources = serde_json::Map::new();
    let mut refreshed = serde_json::Map::new();
    let accessor = re(
        r"(?m)^[ \t]*function[ \t]+m\.([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(([^\n)]*)\)(?:[ \t]*:[ \t]*([^\n]+))?",
    );
    for (path, meta) in discovered {
        let text = match overlay.get(&path) {
            Some(Some(x)) => x.clone(),
            Some(None) => continue,
            None => match fs::read_to_string(&path) {
                Ok(x) => x,
                Err(_) => continue,
            },
        };
        let key = hash(format!("{}\0{}", json_sorted(&meta), text));
        let saved = parsed.get(s(&meta, "path")).filter(|x| s(x, "key") == key);
        let mut entries = Vec::new();
        let mut acc = Vec::new();
        if let Some(saved) = saved {
            entries = saved["definitions"].as_array().cloned().unwrap_or_default();
            acc = saved["accessors"].as_array().cloned().unwrap_or_default();
        } else {
            for d in parse(&text) {
                entries.push(json!({"declaration":d.text,"exported":d.exported,"fingerprint":hash(d.text.as_bytes()),"kind":meta["kind"],"members":d.members,"module":meta["module"],"name":d.name,"owner":meta["owner"],"path":meta["path"],"place":meta["place"],"qualified":qualify(&meta,&d.name)}));
            }
            if s(&meta, "kind") == "data" && path.file_name().is_some_and(|x| x == "Typed.luau") {
                for c in accessor.captures_iter(&mask(&text)) {
                    let sig = format!(
                        "{}({}){}",
                        &c[1],
                        c[2].trim(),
                        c.get(3)
                            .map(|x| format!(": {}", x.as_str().trim()))
                            .unwrap_or_default()
                    );
                    acc.push(json!({"fingerprint":hash(&sig),"name":&c[1],"path":meta["path"],"place":meta["place"],"signature":sig}));
                }
            }
        }
        refreshed.insert(
            s(&meta, "path").into(),
            json!({"key":key,"definitions":entries,"accessors":acc}),
        );
        let pairs: Vec<Value> = entries
            .iter()
            .map(|x| json!([x["qualified"], x["fingerprint"]]))
            .collect();
        sources.insert(
            s(&meta, "path").into(),
            json!(hash(json_sorted(
                &json!({"accessors":acc,"definitions":pairs})
            ))),
        );
        defs.extend(entries);
        access.extend(acc);
    }
    let mut paths: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for d in &defs {
        paths
            .entry(s(d, "qualified").to_string())
            .or_default()
            .insert(s(d, "path").to_string());
    }
    for d in &mut defs {
        if paths.get(s(d, "qualified")).is_some_and(|p| p.len() > 1) {
            d["qualified"] = json!(format!("{}:{}", s(d, "place"), s(d, "qualified")));
        }
    }
    defs.sort_by_key(|d| {
        ["place", "kind", "owner", "module", "name", "path"].map(|k| s(d, k).to_string())
    });
    access.sort_by_key(|d| ["place", "name", "path"].map(|k| s(d, k).to_string()));
    *parsed = Value::Object(refreshed);
    json!({"accessors":access,"definitions":defs,"project_root":root.to_string_lossy(),"source_map_fingerprint":project_fingerprint(root),"sources":sources})
}

fn cache_path(root: &Path) -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".cache/harness/type_cache")
        .join(format!(
            "{}.json",
            hash(canonical(root).to_string_lossy().as_bytes())
        ))
}
fn extra(path: &Path, suffix: &str) -> PathBuf {
    let mut n = path.as_os_str().to_os_string();
    n.push(suffix);
    PathBuf::from(n)
}
fn read_parsed(root: &Path) -> Value {
    let empty = json!({});
    let path = extra(&cache_path(root), ".parsed");
    let Some(saved) = fs::read(path)
        .ok()
        .and_then(|v| serde_json::from_slice::<Value>(&v).ok())
    else {
        return empty;
    };
    let entries = &saved["entries"];
    if saved["schema"] != 1
        || s(&saved, "parser") != hash(include_bytes!("types.rs"))
        || !entries.is_object()
        || s(&saved, "sha256") != hash(cache_json(entries))
    {
        return empty;
    }
    if entries.as_object().unwrap().values().any(|x| {
        x.as_object().map_or(true, |o| o.len() != 3)
            || !x["key"].is_string()
            || ["definitions", "accessors"].iter().any(|k| {
                x[*k]
                    .as_array()
                    .map_or(true, |a| a.iter().any(|v| !v.is_object()))
            })
    }) {
        return empty;
    }
    entries.clone()
}
fn write_parsed(root: &Path, entries: &Value) -> Result<()> {
    let saved = json!({"schema":1,"parser":hash(include_bytes!("types.rs")),"entries":entries,"sha256":hash(cache_json(entries))});
    atomic(
        &extra(&cache_path(root), ".parsed"),
        cache_json(&saved).as_bytes(),
    )
}
struct Lock(PathBuf);
impl Drop for Lock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}
fn lock(root: &Path) -> Result<Lock> {
    let path = extra(&cache_path(root), ".lock");
    fs::create_dir_all(path.parent().unwrap())?;
    let until = Instant::now() + Duration::from_secs(5);
    loop {
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut f) => {
                write!(f, "{}", std::process::id())?;
                return Ok(Lock(path));
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                if fs::metadata(&path)
                    .and_then(|m| m.modified())
                    .ok()
                    .and_then(|t| SystemTime::now().duration_since(t).ok())
                    .is_some_and(|d| d > Duration::from_secs(300))
                {
                    let _ = fs::remove_file(&path);
                    continue;
                }
                if Instant::now() >= until {
                    return Err(anyhow!("type cache transaction lock timed out"));
                }
                std::thread::sleep(Duration::from_millis(20));
            }
            Err(e) => return Err(e.into()),
        }
    }
}
fn journal_path(root: &Path) -> PathBuf {
    extra(&cache_path(root), ".journal")
}
fn clear_journal(root: &Path) {
    let p = journal_path(root);
    let dir = fs::read(&p)
        .ok()
        .and_then(|x| serde_json::from_slice::<Value>(&x).ok())
        .and_then(|v| {
            v.get("directory")
                .and_then(Value::as_str)
                .map(PathBuf::from)
        });
    let _ = fs::remove_file(p);
    if let Some(d) = dir {
        let _ = fs::remove_dir_all(d);
    }
}
fn recover(root: &Path) -> Result<bool> {
    let path = journal_path(root);
    if !path.exists() {
        return Ok(false);
    }
    let r: Value = serde_json::from_slice(&fs::read(&path)?).context("recovery failed")?;
    for item in r["files"]
        .as_array()
        .context("recovery failed: missing files")?
    {
        let target = Path::new(
            item["path"]
                .as_str()
                .context("recovery failed: missing path")?,
        );
        if item["present"].as_bool().unwrap_or(false) {
            let backup = item["backup"]
                .as_str()
                .context("recovery failed: missing backup")?;
            atomic(target, &fs::read(backup)?)?;
        } else if target.exists() {
            fs::remove_file(target)?;
        }
    }
    if let Some(p) = r["cache_backup"].as_str() {
        fs::copy(p, cache_path(root))?;
    } else if cache_path(root).exists() {
        fs::remove_file(cache_path(root))?;
    }
    clear_journal(root);
    Ok(true)
}
fn write_journal(root: &Path, files: &BTreeMap<PathBuf, Option<Vec<u8>>>) -> Result<()> {
    let cp = cache_path(root);
    fs::create_dir_all(cp.parent().unwrap())?;
    let dir = tempfile::Builder::new()
        .prefix("type_write_recovery_")
        .tempdir_in(cp.parent().unwrap())?
        .keep();
    let mut entries = Vec::new();
    for (i, (path, content)) in files.iter().enumerate() {
        let backup = if let Some(bytes) = content {
            let p = dir.join(format!("{i}.source"));
            fs::write(&p, bytes)?;
            Some(p)
        } else {
            None
        };
        entries.push(json!({"backup":backup,"path":path,"present":content.is_some()}));
    }
    let backup = if cp.exists() {
        let p = dir.join("cache.json");
        fs::copy(&cp, &p)?;
        Some(p)
    } else {
        None
    };
    atomic(
        &journal_path(root),
        format!(
            "{}\n",
            json_sorted(&json!({"cache_backup":backup,"directory":dir,"files":entries}))
        )
        .as_bytes(),
    )
}
fn verify(root: &Path) -> (String, Value) {
    let mut parsed = read_parsed(root);
    verify_parsed(root, &mut parsed)
}
fn verify_parsed(root: &Path, parsed: &mut Value) -> (String, Value) {
    let current = build_index_cached(root, &BTreeMap::new(), parsed);
    let path = cache_path(root);
    let status = match fs::read(&path) {
        Err(_) => "missing",
        Ok(b) => match serde_json::from_slice::<Value>(&b) {
            Err(_) => "unreadable",
            Ok(c)
                if !c.is_object()
                    || c.as_object().unwrap().len() != 5
                    || !c["definitions"].is_array()
                    || !c["sources"].is_object()
                    || canonical(Path::new(s(&c, "project_root"))) != canonical(root) =>
            {
                "unreadable"
            }
            Ok(c) if json_sorted(&c) != json_sorted(&current) => "stale",
            Ok(_) => "current",
        },
    };
    (status.into(), current)
}
fn ensure(root: &Path) -> Result<(String, Value)> {
    let _guard = lock(root)?;
    recover(root)?;
    let mut parsed = read_parsed(root);
    let before = cache_json(&parsed);
    let (status, index) = verify_parsed(root, &mut parsed);
    if cache_json(&parsed) != before {
        write_parsed(root, &parsed)?;
    }
    if status == "current" {
        Ok(("current".into(), index))
    } else {
        atomic(&cache_path(root), cache_json(&index).as_bytes())?;
        Ok(("rebuilt".into(), index))
    }
}

fn affected(root: &Path, base: &str) -> Result<String> {
    let r = Command::new("git")
        .args([
            "-C",
            &root.to_string_lossy(),
            "diff",
            "--name-only",
            base,
            "--",
            "*.luau",
            "*.lua",
        ])
        .output()?;
    if !r.status.success() {
        return Err(anyhow!(
            "git diff failed: {}",
            String::from_utf8_lossy(&r.stderr).trim()
        ));
    }
    fn provided(p: &str) -> BTreeSet<String> {
        let mut set = BTreeSet::new();
        let r = re(r"/(?:Services|Controllers|Types)/([^/.]+)");
        let slash = format!("/{p}");
        if let Some(c) = r.captures(&slash) {
            set.insert(c[1].to_string());
        }
        let path = Path::new(p);
        let stem = path
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .split('.')
            .next()
            .unwrap_or("")
            .to_string();
        let name = if stem == "init" {
            path.parent()
                .and_then(Path::file_name)
                .unwrap_or_default()
                .to_string_lossy()
                .to_string()
        } else {
            stem
        };
        if !name.is_empty() && !["Default", "Development", "Typed"].contains(&name.as_str()) {
            set.insert(name);
        }
        set
    }
    let mut consumers: BTreeSet<String> = String::from_utf8_lossy(&r.stdout)
        .lines()
        .filter(|x| !x.is_empty())
        .map(str::to_string)
        .collect();
    let files = source_files(root);
    let patterns = [
        r"\b(?:Services|Controllers|Types)\s*\.\s*([A-Za-z_]\w*)",
        r#"\bget(?:Child|Service|Controller)\s*\(\s*["']([A-Za-z_]\w*)["']\s*\)"#,
        r"\b[A-Za-z_]\w*Typed\s*\.\s*([A-Za-z_]\w*)",
        r"\brequire\s*\(\s*script(?:\s*\.\s*Parent)*\s*\.\s*([A-Za-z_]\w*)\s*\)",
    ]
    .map(re);
    let mut frontier: BTreeSet<String> = consumers.iter().flat_map(|x| provided(x)).collect();
    while !frontier.is_empty() {
        let mut next = BTreeSet::new();
        for f in &files {
            let rel = relative(f, root);
            if consumers.contains(&rel) {
                continue;
            }
            let src = fs::read_to_string(f).unwrap_or_default();
            if patterns
                .iter()
                .any(|p| p.captures_iter(&src).any(|c| frontier.contains(&c[1])))
            {
                consumers.insert(rel.clone());
                next.extend(provided(&rel));
            }
        }
        frontier = next;
    }
    Ok(if consumers.is_empty() {
        "nil".into()
    } else {
        consumers.into_iter().collect::<Vec<_>>().join("\n")
    })
}
fn lookup(root: &Path, query: &Value, index: &Value) -> Result<String> {
    let scope = s(query, "scope");
    if scope == "affected" {
        if s(query, "base").is_empty() {
            return Err(anyhow!("base is required"));
        }
        return affected(root, s(query, "base"));
    }
    let defs = index["definitions"].as_array().context("bad index")?;
    let required = |keys: &[&str]| -> Result<()> {
        if keys.iter().any(|k| s(query, k).is_empty()) {
            Err(anyhow!(
                "{} {} required",
                keys.join(" and "),
                if keys.len() == 1 { "is" } else { "are" }
            ))
        } else {
            Ok(())
        }
    };
    let mut member = None;
    match scope {
        "type" => required(&["type_name"])?,
        "service" | "controller" => required(&[scope])?,
        "service_type" => required(&["service", "type_name"])?,
        "controller_type" => required(&["controller", "type_name"])?,
        "member" => {
            if ["provider", "owner_type", "member"]
                .iter()
                .any(|k| s(query, k).is_empty())
            {
                return Err(anyhow!("provider, owner_type, and member are required"));
            }
            member = Some(s(query, "member"));
        }
        "place" => required(&["place"])?,
        "project" => {}
        _ => {
            return Err(anyhow!(
                "unknown scope {}",
                if scope.is_empty() { "nil" } else { scope }
            ))
        }
    }
    let matches: Vec<&Value> = defs
        .iter()
        .filter(|d| match scope {
            "type" => s(d, "name") == s(query, "type_name"),
            "service" | "controller" => {
                s(d, "owner") == s(query, scope)
                    && [scope, "feature", "data"].contains(&s(d, "kind"))
            }
            "service_type" | "controller_type" => {
                let kind = scope.split('_').next().unwrap();
                s(d, "owner") == s(query, kind)
                    && s(d, "name") == s(query, "type_name")
                    && [kind, "feature", "data"].contains(&s(d, "kind"))
            }
            "member" => {
                let kind = s(query, "provider_kind");
                s(d, "owner") == s(query, "provider")
                    && s(d, "name") == s(query, "owner_type")
                    && (if kind == "service" || kind == "controller" {
                        [kind, "feature"].contains(&s(d, "kind"))
                    } else {
                        ["feature", "service", "controller", "data"].contains(&s(d, "kind"))
                    })
                    && d["members"].get(member.unwrap()).is_some()
            }
            "place" => ["shared", s(query, "place")].contains(&s(d, "place")),
            "project" => true,
            _ => false,
        })
        .collect();
    if matches.is_empty() {
        return Ok("nil".into());
    }
    if let Some(m) = member {
        return Ok(matches
            .iter()
            .map(|d| {
                if matches.len() == 1 {
                    s(&d["members"], m).to_string()
                } else {
                    format!("{}\n{}", s(d, "qualified"), s(&d["members"], m))
                }
            })
            .collect::<Vec<_>>()
            .join("\n\n"));
    }
    let grouped = ["service", "controller", "place", "project"].contains(&scope);
    if matches.len() == 1 && !grouped {
        return Ok(s(matches[0], "declaration").into());
    }
    if grouped {
        let mut paths: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
        for d in matches {
            paths
                .entry(s(d, "path"))
                .or_default()
                .push(s(d, "declaration"));
        }
        return Ok(paths
            .into_iter()
            .map(|(p, d)| format!("@{p}\n{}", d.join("\n\n")))
            .collect::<Vec<_>>()
            .join("\n\n"));
    }
    Ok(matches
        .iter()
        .map(|d| format!("{}\n{}", s(d, "qualified"), s(d, "declaration")))
        .collect::<Vec<_>>()
        .join("\n\n"))
}

#[derive(Debug)]
struct WriteFailure {
    rule: String,
    message: String,
    operation: Option<usize>,
}
impl std::fmt::Display for WriteFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}
impl std::error::Error for WriteFailure {}
fn fail(rule: &str, msg: impl Into<String>) -> anyhow::Error {
    WriteFailure {
        rule: rule.into(),
        message: msg.into(),
        operation: None,
    }
    .into()
}
fn identifier(s: &str) -> bool {
    re(r"^[A-Za-z_][A-Za-z0-9_]*$").is_match(s)
}
fn destination(root: &Path, op: &Value, create: bool, parent: Option<&Path>) -> Result<PathBuf> {
    let owner = s(op, "owner");
    let scope = s(op, "scope");
    if !identifier(owner) {
        return Err(fail("TYPE8", "owner is required and must be an identifier"));
    }
    if !["public", "service", "controller", "data"].contains(&scope) {
        return Err(fail(
            "TYPE8",
            "scope must be public, service, controller, or data",
        ));
    }
    let module = s(op, "module").replace('\\', "/");
    let module = module.trim_matches('/');
    if let Some(parent) = parent {
        if scope == "data" {
            return Err(fail("TYPE8", "parent cannot override generated owner data"));
        }
        if !module.is_empty()
            && module
                .split('/')
                .any(|x| x.is_empty() || x == "." || x == "..")
        {
            return Err(fail("TYPE8", "module must stay inside parent"));
        }
        let p = canonical(&parent.join(format!(
            "{}.luau",
            if module.is_empty() { owner } else { module }
        )));
        if !p.starts_with(parent) {
            return Err(fail("TYPE8", "destination must stay inside parent"));
        }
        return Ok(p);
    }
    let mut base = root.to_path_buf();
    if s(op, "place").is_empty() {
        base.push("shared/src");
    } else {
        base.push("places");
        base.push(s(op, "place"));
        base.push("src");
    }
    if scope == "public" {
        return Ok(base
            .join("ReplicatedStorage/Types")
            .join(format!("{owner}.luau")));
    }
    if scope == "data" {
        return Err(fail(
            "TYPE8",
            "scope must be public, service, controller, or data",
        ));
    }
    base.push(if scope == "service" {
        "ServerScriptService/Services"
    } else {
        "StarterPlayer/StarterPlayerScripts/Controllers"
    });
    let folder = base.join(owner);
    if !module.is_empty() {
        if !folder.is_dir() {
            return Err(fail("TYPE8", format!("{scope} {owner} has no folder form")));
        }
        let a = folder.join(format!("{module}.luau"));
        let b = folder.join(module).join("init.luau");
        if a.exists() || create && !b.exists() {
            return Ok(a);
        }
        if b.exists() {
            return Ok(b);
        }
        return Err(fail(
            "TYPE8",
            format!("{owner}/{module} module does not exist"),
        ));
    }
    let flat = base.join(format!("{owner}.luau"));
    if flat.exists() {
        return Ok(flat);
    }
    let init = folder.join("init.luau");
    if init.exists() {
        return Ok(init);
    }
    Err(fail("TYPE8", format!("{scope} {owner} does not exist")))
}
fn find_decl(src: Option<&str>, name: &str) -> Result<Option<Decl>> {
    let mut a: Vec<_> = src
        .map(parse)
        .unwrap_or_default()
        .into_iter()
        .filter(|x| x.name == name)
        .collect();
    if a.len() > 1 {
        return Err(fail("TYPE8", format!("{name} is declared more than once")));
    }
    Ok(a.pop())
}
fn validated(op: &Value, public: bool) -> Result<String> {
    let name = s(op, "type_name");
    if !identifier(name) {
        return Err(fail(
            "TYPE8",
            "type_name is required and must be an identifier",
        ));
    }
    let text = op
        .get("declaration")
        .and_then(Value::as_str)
        .ok_or_else(|| fail("TYPE8", "declaration is required"))?;
    let a = parse(text);
    if a.len() != 1 || a[0].name != name || a[0].text.trim() != text.trim() {
        return Err(fail(
            "TYPE8",
            format!("declaration must contain exactly {name}"),
        ));
    }
    if public && !a[0].exported {
        return Err(fail(
            "TYPE8",
            format!("{name} must be exported in the feature Types module"),
        ));
    }
    if !public && a[0].exported {
        return Err(fail(
            "TYPE8",
            format!("{name} is private and uses a local type declaration"),
        ));
    }
    Ok(a[0].text.clone())
}
fn insert(src: Option<&str>, decl: &str, public: bool) -> String {
    let Some(src) = src else {
        return format!("{decl}{}", if public { "\n\nreturn {}\n" } else { "\n" });
    };
    let p = re(r"(?m)^[ \t]*return\b")
        .find_iter(src)
        .last()
        .map(|x| x.start())
        .unwrap_or(src.len());
    let before = src[..p].trim_end();
    let after = src[p..].trim_start_matches(['\r', '\n']);
    format!(
        "{before}{}{decl}{}",
        if before.is_empty() { "" } else { "\n\n" },
        if after.is_empty() {
            String::from("\n")
        } else {
            format!("\n\n{after}")
        }
    )
}
fn delete(src: &str, d: &Decl) -> String {
    let before = src[..d.start].trim_end();
    let after = src[d.end..].trim_start_matches(['\r', '\n']);
    format!(
        "{before}{}{after}",
        if !before.is_empty() && !after.is_empty() {
            "\n\n"
        } else {
            ""
        }
    )
}
fn overlay_read(path: &Path, overlay: &BTreeMap<PathBuf, Option<String>>) -> Option<String> {
    let p = canonical(path);
    overlay
        .get(&p)
        .cloned()
        .unwrap_or_else(|| fs::read_to_string(p).ok())
}
fn apply_type(
    root: &Path,
    op: &Value,
    overlay: &mut BTreeMap<PathBuf, Option<String>>,
    parent: Option<&Path>,
) -> Result<(String, Option<String>, PathBuf, Option<PathBuf>)> {
    let action = s(op, "action");
    let name = s(op, "type_name");
    if !["create", "update", "move", "delete"].contains(&action) {
        return Err(fail(
            "TYPE8",
            "action must be create, update, move, or delete",
        ));
    }
    if name.is_empty() {
        return Err(fail("TYPE8", "type_name is required"));
    }
    let public = s(op, "scope") == "public";
    if action == "move" {
        let from = op
            .get("from")
            .filter(|x| x.is_object())
            .ok_or_else(|| fail("TYPE8", "move requires from"))?;
        let source = canonical(&destination(root, from, false, None)?);
        let text = overlay_read(&source, overlay);
        let d = find_decl(text.as_deref(), name)?
            .ok_or_else(|| fail("TYPE8", format!("{name} does not exist at the move source")))?;
        let target = canonical(&destination(root, op, true, parent)?);
        let other = overlay_read(&target, overlay);
        if find_decl(other.as_deref(), name)?.is_some() {
            return Err(fail(
                "TYPE8",
                format!("{name} already exists at the move destination"),
            ));
        }
        let mut copy = op.clone();
        if s(op, "declaration").is_empty() {
            copy["declaration"] = json!(d.text);
        }
        let decl = validated(&copy, public)?;
        overlay.insert(source.clone(), Some(delete(text.as_deref().unwrap(), &d)));
        overlay.insert(
            target.clone(),
            Some(insert(other.as_deref(), &decl, public)),
        );
        return Ok(("moved".into(), Some(decl), target, Some(source)));
    }
    let path = canonical(&destination(root, op, action == "create", parent)?);
    let text = overlay_read(&path, overlay);
    let old = find_decl(text.as_deref(), name)?;
    if action == "delete" {
        let d = old.ok_or_else(|| fail("TYPE8", format!("{name} does not exist")))?;
        overlay.insert(path.clone(), Some(delete(text.as_deref().unwrap(), &d)));
        return Ok(("deleted".into(), None, path, None));
    }
    let decl = validated(op, public)?;
    if action == "create" {
        if old.is_some() {
            return Err(fail("TYPE8", format!("{name} already exists")));
        }
        overlay.insert(path.clone(), Some(insert(text.as_deref(), &decl, public)));
        return Ok(("created".into(), Some(decl), path, None));
    }
    let d = old.ok_or_else(|| fail("TYPE8", format!("{name} does not exist")))?;
    if d.text == decl {
        return Ok(("unchanged".into(), Some(decl), path, None));
    }
    let text = text.unwrap();
    overlay.insert(
        path.clone(),
        Some(format!("{}{}{}", &text[..d.start], decl, &text[d.end..])),
    );
    Ok(("updated".into(), Some(decl), path, None))
}

fn tools() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tools")
}
fn tool(name: &str) -> PathBuf {
    let p = tools().join("bin").join(name);
    if p.exists() {
        p
    } else {
        PathBuf::from(name)
    }
}
fn output_text(out: &std::process::Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    )
}
fn data_ops(
    root: &Path,
    ops: &[(usize, Value)],
    overlay: &mut BTreeMap<PathBuf, Option<String>>,
) -> Result<Vec<Value>> {
    if ops.is_empty() {
        return Ok(Vec::new());
    }
    let temp = tempfile::Builder::new()
        .prefix("type_write_data_")
        .tempdir()?;
    let original = root.join("shared/src/ServerScriptService/Services");
    let target = temp.path().join("shared/src/ServerScriptService/Services");
    fs::create_dir_all(&target)?;
    if original.is_dir() {
        for e in WalkDir::new(&original).into_iter().flatten() {
            let dest = target.join(e.path().strip_prefix(&original)?);
            if e.file_type().is_dir() {
                fs::create_dir_all(dest)?;
            } else if e.file_type().is_file() {
                if let Some(p) = dest.parent() {
                    fs::create_dir_all(p)?;
                }
                fs::copy(e.path(), dest)?;
            }
        }
    }
    let pd = target.join("PlayerData");
    fs::create_dir_all(&pd)?;
    let lute = tool("lute");
    let mut outcomes = Vec::new();
    for (number, op) in ops {
        let owner = s(op, "owner");
        let field = s(op, "field_path");
        if owner.is_empty() || field.is_empty() {
            return Err(WriteFailure {
                rule: "DATA37".into(),
                message: "data operation requires owner and field_path".into(),
                operation: Some(*number),
            }
            .into());
        }
        let action = s(op, "action");
        if !["create", "update", "delete"].contains(&action) {
            return Err(fail(
                "TYPE8",
                "data action must be create, update, or delete",
            ));
        }
        let default = if action == "delete" {
            "nil"
        } else {
            s(op, "default_value")
        };
        let dev = if action == "delete" {
            "nil"
        } else {
            s(op, "development_value")
        };
        if default.is_empty() || dev.is_empty() {
            return Err(fail(
                "TYPE8",
                "data operation requires Default and Development values",
            ));
        }
        let key = format!("{}.{}", owner, field.trim_matches('.'));
        let old = pd.join("Default.luau");
        let development = pd.join("Development.luau");
        let before = fs::read_to_string(&old).ok();
        let prior = find_decl(before.as_deref(), owner)?;
        let generated = tempfile::tempdir()?;
        let out = generated.path().join("Default.luau");
        let outdev = generated.path().join("Development.luau");
        let result = Command::new(&lute)
            .arg("run")
            .arg(tools().join("data_write/data_write_core.luau"))
            .arg(&key)
            .arg(default)
            .arg(dev)
            .arg(if old.exists() {
                old.as_os_str()
            } else {
                std::ffi::OsStr::new("NEW")
            })
            .arg(if development.exists() {
                development.as_os_str()
            } else {
                std::ffi::OsStr::new("NEW")
            })
            .arg(&out)
            .arg(&outdev)
            .output()
            .context("bundled lute absent")?;
        if !result.status.success() || !result.stdout.starts_with(b"OK") {
            let detail = output_text(&result);
            let rule = re(r"(?:^|\|)(GATE[1-7]|TYPE\d+|DATA\d+)!?\|")
                .captures(&detail)
                .map(|c| c[1].to_string())
                .unwrap_or_else(|| "GATE4".into());
            return Err(WriteFailure {
                rule,
                message: detail
                    .lines()
                    .collect::<Vec<_>>()
                    .join(" ")
                    .chars()
                    .take(240)
                    .collect(),
                operation: Some(*number),
            }
            .into());
        }
        if old.exists() {
            let diff = Command::new(&lute)
                .arg("run")
                .arg(tools().join("data_shape_diff/data_shape_diff.luau"))
                .arg(&old)
                .arg(&out)
                .arg("--migrations")
                .arg(&target)
                .output()?;
            if !diff.status.success() || !diff.stdout.starts_with(b"ALLOW") {
                let detail = output_text(&diff);
                let rule = re(r"\[(GATE[1-7]|DATA\d+|TYPE\d+)\]")
                    .captures(&detail)
                    .map(|c| c[1].to_string())
                    .unwrap_or_else(|| "GATE4".into());
                return Err(WriteFailure {
                    rule,
                    message: detail.lines().skip(1).collect::<Vec<_>>().join(" "),
                    operation: Some(*number),
                }
                .into());
            }
        }
        let after_src = fs::read_to_string(&out)?;
        let after = find_decl(Some(&after_src), owner)?;
        let unchanged = match (&prior, &after) {
            (None, None) => true,
            (Some(a), Some(b)) => hash(&a.text) == hash(&b.text),
            _ => false,
        };
        if action == "delete" && unchanged {
            return Err(fail("TYPE8", format!("{key} does not exist")));
        }
        let status = if action == "delete" {
            "deleted"
        } else if prior.is_none() {
            "created"
        } else if unchanged {
            "unchanged"
        } else {
            "updated"
        };
        let decl = after.map(|d| d.text);
        fs::copy(&out, &old)?;
        fs::copy(&outdev, &development)?;
        let typed = generated.path().join("Typed.luau");
        if typed.exists() {
            fs::copy(typed, pd.join("Typed.luau"))?;
        }
        outcomes.push(json!({"number":number,"outcome":status,"name":format!("PlayerData.{owner}"),"declaration":decl,"path":canonical(&original.join("PlayerData/Default.luau")),"source":null,"show_declaration":action!="delete","type_name":owner}));
    }
    for name in ["Default.luau", "Development.luau", "Typed.luau"] {
        let p = pd.join(name);
        if p.exists() {
            overlay.insert(
                canonical(&original.join("PlayerData").join(name)),
                Some(fs::read_to_string(p)?),
            );
        }
    }
    Ok(outcomes)
}
fn analyze(root: &Path, paths: &[PathBuf]) -> Result<()> {
    let files: Vec<_> = paths
        .iter()
        .filter(|p| {
            p.exists() && matches!(p.extension().and_then(|x| x.to_str()), Some("lua" | "luau"))
        })
        .collect();
    if files.is_empty() {
        return Ok(());
    }
    let definitions = tools().join("globalTypes.d.luau");
    if !definitions.exists() {
        return Err(anyhow!("luau-lsp analysis is unavailable"));
    }
    let lsp = tool("luau-lsp");
    let tmp = tempfile::tempdir()?;
    let mut cmd = Command::new(lsp);
    cmd.args([
        "analyze",
        "--flag:LuauSolverV2=true",
        "--no-strict-dm-types",
        "--platform",
        "roblox",
        "--definitions",
    ])
    .arg(format!("@roblox={}", definitions.display()))
    .arg("--base-luaurc")
    .arg(tools().join("base.luaurc"))
    .args([
        "--ignore",
        "**/_Index/**",
        "--ignore",
        "**/Packages/**",
        "--ignore",
        "**/Modules/**",
    ]);
    let project = root.join("default.project.json");
    if project.exists() {
        let map = tmp.path().join("sourcemap.json");
        if Command::new("argon")
            .arg("sourcemap")
            .arg(project)
            .arg("-o")
            .arg(&map)
            .output()
            .is_ok_and(|x| x.status.success())
            && map.exists()
        {
            cmd.arg("--sourcemap").arg(map);
        }
    }
    let out = cmd
        .args(files)
        .output()
        .context("luau-lsp analysis is unavailable")?;
    if !matches!(out.status.code(), Some(0 | 1)) {
        return Err(anyhow!(
            "luau-lsp analysis failed: {}",
            output_text(&out)
                .lines()
                .collect::<Vec<_>>()
                .join(" ")
                .chars()
                .take(200)
                .collect::<String>()
        ));
    }
    let text = output_text(&out);
    let diagnostic = re(r"^.+\(\d+,\d+\): (?:SyntaxError|TypeError):");
    if let Some(line) = text.lines().find(|l| diagnostic.is_match(l)) {
        return Err(fail("TYPE1", line.chars().take(240).collect::<String>()));
    }
    Ok(())
}
fn write_types(root: &Path, ops: &[Value], parent: Option<&str>) -> Result<Vec<Value>> {
    if ops.is_empty() || ops.iter().any(|o| !o.is_object()) {
        return Err(fail(
            "TYPE8",
            "operations must be a non-empty list of objects",
        ));
    }
    let parent = match parent {
        Some(p) if p.trim().is_empty() => {
            return Err(fail(
                "TYPE8",
                "parent must be a non-empty directory in the project",
            ))
        }
        Some(p) => {
            let path = canonical(&root.join(p));
            if !path.starts_with(root) || path == root {
                return Err(fail(
                    "TYPE8",
                    "parent must be a directory inside the project",
                ));
            }
            if path.exists() && !path.is_dir() {
                return Err(fail("TYPE8", "parent must be a directory"));
            }
            Some(path)
        }
        None => None,
    };
    let (_, base) = ensure(root)?;
    let mut overlay = BTreeMap::new();
    let mut outcomes = Vec::new();
    let mut data = Vec::new();
    for (i, op) in ops.iter().enumerate() {
        if s(op, "scope") == "data" {
            if parent.is_some() {
                return Err(WriteFailure {
                    rule: "TYPE8".into(),
                    message: "parent cannot override generated owner data".into(),
                    operation: Some(i + 1),
                }
                .into());
            }
            data.push((i + 1, op.clone()));
            continue;
        }
        let (status, decl, path, source) = apply_type(root, op, &mut overlay, parent.as_deref())
            .map_err(|e| match e.downcast::<WriteFailure>() {
                Ok(mut e) => {
                    e.operation = Some(i + 1);
                    e.into()
                }
                Err(e) => e,
            })?;
        let name = s(op, "type_name");
        let qualified = metadata(root, &path)
            .map(|m| qualify(&m, name))
            .unwrap_or_else(|| {
                if s(op, "module").is_empty() {
                    format!("{}.{name}", s(op, "owner"))
                } else {
                    format!("{}/{}.{name}", s(op, "owner"), s(op, "module"))
                }
            });
        outcomes.push(json!({"number":i+1,"outcome":status,"name":qualified,"declaration":decl,"path":path,"source":source,"show_declaration":true,"type_name":name}));
    }
    outcomes.extend(data_ops(root, &data, &mut overlay)?);
    outcomes.sort_by_key(|x| x["number"].as_u64());
    let index = build_index(root, &overlay);
    for out in &mut outcomes {
        let path = Path::new(s(out, "path"));
        let rel = relative(path, root);
        let def = index["definitions"].as_array().unwrap().iter().find(|d| {
            s(d, "path") == rel
                && s(d, "name") == s(out, "type_name")
                && (out["declaration"].is_null() || d["declaration"] == out["declaration"])
        });
        if !out["declaration"].is_null() {
            if let Some(d) = def {
                out["name"] = d["qualified"].clone();
            } else if parent.is_none() || metadata(root, path).is_some() {
                return Err(fail(
                    "TYPE1",
                    format!("{} is not a complete Luau declaration", s(out, "name")),
                ));
            }
        } else if let Some(d) = base["definitions"]
            .as_array()
            .unwrap()
            .iter()
            .find(|d| s(d, "path") == rel && s(d, "name") == s(out, "type_name"))
        {
            out["name"] = d["qualified"].clone();
        }
    }
    let _guard = lock(root)?;
    recover(root)?;
    let (_, current) = verify(root);
    if json_sorted(&current) != json_sorted(&base) {
        return Err(anyhow!("project types changed during type_write"));
    }
    let mut prior = BTreeMap::new();
    for path in overlay.keys() {
        prior.insert(
            path.clone(),
            match fs::read(path) {
                Ok(x) => Some(x),
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
                Err(e) => return Err(e.into()),
            },
        );
    }
    write_journal(root, &prior)?;
    let result = (|| -> Result<()> {
        for (p, content) in &overlay {
            if let Some(text) = content {
                atomic(p, text.as_bytes())?;
            } else if p.exists() {
                fs::remove_file(p)?;
            }
        }
        analyze(root, &overlay.keys().cloned().collect::<Vec<_>>())?;
        atomic(&cache_path(root), cache_json(&index).as_bytes())?;
        Ok(())
    })();
    if let Err(e) = result {
        recover(root)?;
        return Err(e);
    }
    clear_journal(root);
    Ok(outcomes)
}

pub fn run(args: &[OsString]) -> Result<i32> {
    let strings: Vec<String> = args
        .iter()
        .map(|x| x.to_string_lossy().into_owned())
        .collect();
    let action = strings.first().map(String::as_str).unwrap_or("");
    let mut root = std::env::current_dir()?;
    let mut parent = None;
    let mut request = None;
    let mut request_file = None;
    let mut operations = Vec::new();
    let mut queries = Vec::new();
    let mut cache_action = None;
    let mut i = 1;
    while i < strings.len() {
        let token = &strings[i];
        let (key, inline) = token
            .split_once('=')
            .map(|(a, b)| (a, Some(b.to_string())))
            .unwrap_or((token.as_str(), None));
        let needs = matches!(
            key,
            "--root"
                | "--parent"
                | "--session"
                | "--request"
                | "--request-file"
                | "--operation"
                | "--type"
                | "--service"
                | "--controller"
                | "--service-type"
                | "--controller-type"
                | "--place"
                | "--affected"
        );
        let value = if needs {
            if let Some(x) = inline {
                Some(x)
            } else {
                i += 1;
                Some(
                    strings
                        .get(i)
                        .cloned()
                        .ok_or_else(|| anyhow!("{key} requires a value"))?,
                )
            }
        } else {
            None
        };
        match key {
            "--root" => root = PathBuf::from(value.unwrap()),
            "--parent" => parent = value,
            "--session" | "--gate" => {}
            "--request" => request = value,
            "--request-file" => request_file = value,
            "--operation" => operations.push(value.unwrap()),
            "--project" => queries.push(json!({"scope":"project"})),
            "--type" => queries.push(json!({"scope":"type","type_name":value.unwrap()})),
            "--service" => queries.push(json!({"scope":"service","service":value.unwrap()})),
            "--controller" => {
                queries.push(json!({"scope":"controller","controller":value.unwrap()}))
            }
            "--place" => queries.push(json!({"scope":"place","place":value.unwrap()})),
            "--affected" => queries.push(json!({"scope":"affected","base":value.unwrap()})),
            "--service-type" | "--controller-type" => {
                let v = value.unwrap();
                if let Some((owner, name)) = v.split_once(':') {
                    if key == "--service-type" {
                        queries
                            .push(json!({"scope":"service_type","service":owner,"type_name":name}));
                    } else {
                        queries.push(
                            json!({"scope":"controller_type","controller":owner,"type_name":name}),
                        );
                    }
                } else {
                    println!(
                        "BLOCKED|WRIT33|{}-type uses {}:Type",
                        if key == "--service-type" {
                            "service"
                        } else {
                            "controller"
                        },
                        if key == "--service-type" {
                            "Service"
                        } else {
                            "Controller"
                        }
                    );
                    return Ok(2);
                }
            }
            x if action == "cache" && !x.starts_with('-') => cache_action = Some(x.to_string()),
            _ => return Err(anyhow!("unrecognized argument: {token}")),
        }
        i += 1;
    }
    root = canonical(&root);
    match action {
        "cache" => {
            let result: Result<(i32, String)> = (|| match cache_action.as_deref().unwrap_or("") {
                "ensure" => {
                    let (status, _) = ensure(&root)?;
                    Ok((0, format!("OK|{status}")))
                }
                "verify" => {
                    let (status, _) = verify(&root);
                    Ok((
                        if status == "current" { 0 } else { 2 },
                        if status == "current" {
                            "OK|current".into()
                        } else {
                            format!("STALE|{status}")
                        },
                    ))
                }
                "recover" => Ok((
                    0,
                    format!(
                        "OK|{}",
                        if recover(&root)? {
                            "recovered"
                        } else {
                            "current"
                        }
                    ),
                )),
                _ => Err(anyhow!("expected ensure, verify, or recover")),
            })();
            match result {
                Ok((code, msg)) => {
                    println!("{msg}");
                    Ok(code)
                }
                Err(e) => {
                    println!("ENV|{e}");
                    Ok(3)
                }
            }
        }
        "read" => {
            if let Some(text) = request {
                let value: Value = match serde_json::from_str(&text) {
                    Ok(v) => v,
                    Err(e) => {
                        println!("ENV|ValueError: {e}");
                        return Ok(3);
                    }
                };
                let value = value.get("queries").cloned().unwrap_or(value);
                queries = match value.as_array() {
                    Some(v) => v.clone(),
                    None => {
                        println!("BLOCKED|WRIT33|queries must be a non-empty list of objects");
                        return Ok(2);
                    }
                };
            }
            if queries.is_empty() {
                println!("BLOCKED|WRIT33|at least one query is required");
                return Ok(2);
            }
            if queries.iter().any(|x| !x.is_object()) {
                println!("BLOCKED|WRIT33|queries must be a non-empty list of objects");
                return Ok(2);
            }
            let (_, index) = match ensure(&root) {
                Ok(x) => x,
                Err(e) => {
                    println!("ENV|{e}");
                    return Ok(3);
                }
            };
            let mut out = Vec::new();
            for q in &queries {
                match lookup(&root, q, &index) {
                    Ok(x) => out.push(x),
                    Err(e) => {
                        println!("BLOCKED|WRIT33|{e}");
                        return Ok(2);
                    }
                }
            }
            if out.len() == 1 {
                println!("{}", out[0]);
            } else {
                for (i, x) in out.iter().enumerate() {
                    if i > 0 {
                        println!();
                    }
                    println!("@query {}\n{x}", i + 1);
                }
            }
            Ok(0)
        }
        "write" => {
            let parse_request = || -> Result<Value> {
                if let Some(path) = request_file {
                    Ok(serde_json::from_slice(&fs::read(path)?)?)
                } else if let Some(text) = request {
                    if text == "-" {
                        let mut s = String::new();
                        std::io::stdin().read_to_string(&mut s)?;
                        Ok(serde_json::from_str(&s)?)
                    } else {
                        Ok(serde_json::from_str(&text)?)
                    }
                } else {
                    Ok(Value::Array(
                        operations
                            .iter()
                            .map(|x| serde_json::from_str(x))
                            .collect::<std::result::Result<Vec<_>, _>>()?,
                    ))
                }
            };
            let value = match parse_request() {
                Ok(v) => v,
                Err(e) => {
                    println!("BLOCKED|TYPE8|invalid JSON request: {e}");
                    return Ok(2);
                }
            };
            let value = value.get("operations").cloned().unwrap_or(value);
            let ops = match value.as_array() {
                Some(x) if !x.is_empty() => x,
                _ => {
                    println!("BLOCKED|TYPE8|at least one operation is required");
                    return Ok(2);
                }
            };
            match write_types(&root, ops, parent.as_deref()) {
                Ok(out) => {
                    if out.len() == 1 {
                        let x = &out[0];
                        println!(
                            "OK|{}{}",
                            s(x, "outcome"),
                            if s(x, "outcome") == "deleted" {
                                format!("|{}", s(x, "name"))
                            } else {
                                String::new()
                            }
                        );
                        if !x["declaration"].is_null()
                            && x["show_declaration"].as_bool().unwrap_or(true)
                        {
                            println!("{}", s(x, "declaration"));
                        }
                    } else {
                        println!("OK");
                        for (i, x) in out.iter().enumerate() {
                            if i > 0 {
                                println!();
                            }
                            println!("{}|{}|{}", x["number"], s(x, "outcome"), s(x, "name"));
                            if !x["declaration"].is_null()
                                && x["show_declaration"].as_bool().unwrap_or(true)
                            {
                                println!("{}", s(x, "declaration"));
                            }
                        }
                    }
                    Ok(0)
                }
                Err(e) => {
                    if let Some(w) = e.downcast_ref::<WriteFailure>() {
                        println!(
                            "BLOCKED|{}{}|{}",
                            w.rule,
                            w.operation
                                .map(|n| format!("|operation {n}"))
                                .unwrap_or_default(),
                            w.message
                        );
                        Ok(2)
                    } else {
                        println!("ENV|{e}");
                        Ok(3)
                    }
                }
            }
        }
        _ => Err(anyhow!("unknown types action: {action}")),
    }
}
