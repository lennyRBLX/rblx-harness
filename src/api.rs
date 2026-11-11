use anyhow::Result;
use regex::Regex;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

const DUMP_URL: &str =
    "https://raw.githubusercontent.com/MaximumADHD/Roblox-Client-Tracker/roblox/API-Dump.json";
const CLASS_TAGS: &[&str] = &[
    "NotCreatable",
    "Service",
    "Deprecated",
    "NotReplicated",
    "PlayerReplicated",
];
const MEMBER_TAGS: &[&str] = &[
    "Yields",
    "CanYield",
    "NoYield",
    "Hidden",
    "ReadOnly",
    "NotScriptable",
    "Deprecated",
];
fn text(v: &Value) -> &str {
    v.as_str().unwrap_or("")
}
fn s(v: &Value) -> String {
    match v {
        Value::String(x) => x.clone(),
        Value::Null => "None".into(),
        _ => v.to_string(),
    }
}
fn arr(v: &Value) -> &[Value] {
    v.as_array().map(Vec::as_slice).unwrap_or(&[])
}
fn get(v: &Value, k: &str) -> Value {
    v.get(k).cloned().unwrap_or(json!("unknown"))
}
fn nonempty(v: &Value, fallback: &str) -> Value {
    if v.is_null() || v.as_str() == Some("") || v.as_array().is_some_and(|a| a.is_empty()) {
        json!(fallback)
    } else {
        v.clone()
    }
}
fn field(x: &str) -> &str {
    if x.is_empty() {
        "void"
    } else {
        x
    }
}
fn strip_markup(x: &str) -> String {
    let re = Regex::new(
        r"`?(?:Class|Enum|Datatype|Library|Global)\.([A-Za-z0-9_.:()]+?)(?:\|([^`]+?))?`",
    )
    .unwrap();
    re.replace_all(x, |c: &regex::Captures| {
        c.get(2)
            .unwrap_or_else(|| c.get(1).unwrap())
            .as_str()
            .to_owned()
    })
    .replace('`', "")
}
fn sha(path: &Path) -> String {
    fs::read(path)
        .map(|b| format!("{:x}", Sha256::digest(b)))
        .unwrap_or_else(|_| "unknown".into())
}
fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
fn line(v: &Value) -> String {
    let x = text(v);
    let re = Regex::new(
        r"`?(?:Class|Enum|Datatype|Library|Global)\.([A-Za-z0-9_.:()]+?)(?:\|([^`]+?))?`",
    )
    .unwrap();
    let a = re.replace_all(x, |c: &regex::Captures| {
        c.get(2)
            .unwrap_or_else(|| c.get(1).unwrap())
            .as_str()
            .to_owned()
    });
    a.replace('`', "")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .replace('|', "/")
}
fn tags(v: &Value, keep: &[&str]) -> String {
    arr(v)
        .iter()
        .filter_map(Value::as_str)
        .filter(|x| keep.contains(x))
        .collect::<Vec<_>>()
        .join(",")
}
fn contains(v: &Value, t: &str) -> bool {
    arr(v).iter().any(|x| x.as_str() == Some(t))
}
fn yaml(path: &Path) -> Value {
    fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_yaml::from_str::<Value>(&s).ok())
        .unwrap_or(Value::Null)
}
fn json_file(path: &Path) -> Value {
    fs::read(path)
        .ok()
        .and_then(|s| serde_json::from_slice(&s).ok())
        .unwrap_or(Value::Null)
}
fn atomic_json(path: &Path, v: &Value) -> Result<()> {
    let tmp = path.with_extension(format!("{}.tmp", std::process::id()));
    fs::write(&tmp, format!("{}\n", serde_json::to_string(v)?))?;
    if let Err(e) = fs::rename(&tmp, path) {
        let _ = fs::remove_file(tmp);
        return Err(e.into());
    }
    Ok(())
}
struct Corpus {
    cache: PathBuf,
    root: PathBuf,
    content: PathBuf,
    engine: PathBuf,
    dump: Value,
    behavior: Value,
    overlay: HashMap<String, String>,
}
impl Corpus {
    fn new() -> Self {
        let cache = dirs::home_dir().unwrap_or_default().join(".cache/harness");
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let content = cache.join("creator-docs/content/en-us");
        let engine = content.join("reference/engine");
        let dump = json_file(&cache.join("API-Dump.json"));
        let behavior = json_file(&root.join("tools/api_dump/behavior.json"));
        let overlay = fs::read_to_string(root.join("tools/api_dump/house_overlay.txt"))
            .unwrap_or_default()
            .lines()
            .filter_map(|l| {
                let l = l.trim();
                if l.starts_with('#') {
                    None
                } else {
                    l.split_once('|')
                        .map(|(a, b)| (a.trim().to_owned(), b.trim().to_owned()))
                }
            })
            .collect();
        Self {
            cache,
            root,
            content,
            engine,
            dump,
            behavior,
            overlay,
        }
    }
    fn need_dump(&self) -> bool {
        if !self.cache.join("API-Dump.json").exists() {
            println!("ENV|api-dump-absent|api_dump --sync");
            false
        } else {
            true
        }
    }
    fn need_docs(&self) -> bool {
        if !self.engine.is_dir() {
            println!("ENV|creator-docs-absent|api_dump --sync");
            false
        } else {
            true
        }
    }
    fn classes(&self) -> &[Value] {
        arr(&self.dump["Classes"])
    }
    fn class(&self, name: &str) -> Option<&Value> {
        self.classes().iter().find(|c| text(&c["Name"]) == name)
    }
    fn chain(&self, name: &str) -> Vec<String> {
        let mut out = vec![name.to_owned()];
        let mut seen = HashSet::new();
        seen.insert(name.to_owned());
        let mut cur = name;
        while let Some(c) = self.class(cur) {
            let sup = text(&c["Superclass"]);
            if sup.is_empty() || sup == "<<<ROOT>>>" || !seen.insert(sup.to_owned()) {
                break;
            }
            out.push(sup.to_owned());
            cur = text(&c["Superclass"]);
        }
        out
    }
    fn y(&self, kind: &str, name: &str) -> Value {
        yaml(&self.engine.join(kind).join(format!("{name}.yaml")))
    }
    fn members(y: &Value) -> HashMap<String, Value> {
        let mut m = HashMap::new();
        for k in ["properties", "methods", "events", "callbacks"] {
            for v in arr(&y[k]) {
                let name = text(&v["name"]).rsplit(['.', ':']).next().unwrap_or("");
                if !name.is_empty() {
                    m.insert(name.to_owned(), v.clone());
                }
            }
        }
        m
    }
    fn rev(&self) -> String {
        Command::new("git")
            .args([
                "-C",
                self.cache.join("creator-docs").to_string_lossy().as_ref(),
                "rev-parse",
                "HEAD",
            ])
            .output()
            .ok()
            .filter(|o| o.status.success())
            .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_owned())
            .unwrap_or_else(|| "unknown".into())
    }
    fn provenance(&self) -> Value {
        let hash = sha(&self.cache.join("API-Dump.json"));
        let rev = self.rev();
        let m = json_file(&self.cache.join("corpus-refresh.json"));
        let matched =
            if m.get("api_dump_sha256").is_none() || m.get("creator_docs_revision").is_none() {
                "unknown"
            } else if m["api_dump_sha256"] == hash && m["creator_docs_revision"] == rev {
                "match"
            } else {
                "mismatch"
            };
        let age = m["refreshed_at"].as_f64().map(|x| now() - x);
        let freshness = match age {
            Some(a) if a >= 86400.0 => "stale",
            Some(a) if a >= -300.0 => "fresh",
            _ => "unknown",
        };
        let build = fs::read_to_string(self.engine.join("STUDIO_VERSION")).unwrap_or_default();
        json!({"api_dump_sha256":hash,"creator_docs_revision":rev,"api_dump_url":DUMP_URL,"api_dump_schema_version":get(&self.dump,"Version"),"refreshed_at":get(&m,"refreshed_at"),"cache_manifest_match":matched,"engine_build":"unknown","studio_build":"unknown","mcp_version":"unknown","engine_docs_alignment":"unknown","creator_docs_engine_version":if build.trim().is_empty(){"unknown"}else{build.trim()},"freshness":freshness})
    }
    fn description(&self, cls: &str, entry: &Value) -> Value {
        let path = format!("reference/engine/classes/{cls}.yaml");
        let present = entry.as_object().is_some_and(|o| !o.is_empty());
        let mut metadata = serde_json::Map::new();
        for key in ["security", "capabilities", "tags", "thread_safety"] {
            if let Some(x) = entry.get(key) {
                metadata.insert(key.into(), x.clone());
            }
        }
        json!({"status":if present {"available"} else {"missing"},"path":path,"sha256":sha(&self.content.join(&path)),"summary":nonempty(&entry["summary"],"unknown"),"description":nonempty(&entry["description"],"unknown"),"deprecation_message":nonempty(&entry["deprecation_message"],if present {"none"} else {"unknown"}),"source_route":format!("harness api doc {path}"),"metadata":metadata})
    }
    fn behavior_rows(&self, query: &str, p: &Value) -> Vec<Value> {
        arr(&self.behavior["records"])
            .iter()
            .filter(|r| {
                text(&r["id"]) == query
                    || contains(&r["topics"], query)
                    || contains(&r["apis"], query)
            })
            .map(|r| self.behavior_evidence(r, p))
            .collect()
    }
    fn behavior_evidence(&self, row: &Value, p: &Value) -> Value {
        let mut out = row.clone();
        let reviewed = text(&row["creator_docs_revision"]);
        let rev = text(&p["creator_docs_revision"]);
        let mut status = if reviewed.is_empty() || rev == "unknown" {
            "unknown"
        } else if reviewed == rev {
            "reviewed"
        } else {
            "recheck-required"
        };
        let mut checks = Vec::new();
        for (key, root) in [("sources", &self.content), ("project_sources", &self.root)] {
            for source in arr(&row[key]) {
                let path = text(&source["path"]);
                let actual = sha(&root.join(path));
                let expected = text(&source["sha256"]);
                let state = if actual == "unknown" {
                    "missing"
                } else if key == "sources" && (expected.is_empty() || expected == "unknown") {
                    "unknown"
                } else if expected == actual {
                    "match"
                } else {
                    "mismatch"
                };
                if state == "missing" || state == "mismatch" {
                    status = "recheck-required";
                }
                checks.push(json!({"path":path,"status":state}));
            }
        }
        if row
            .get("api_dump_sha256")
            .is_some_and(|v| !text(v).is_empty() && v != &p["api_dump_sha256"])
            || p["freshness"] == "stale"
        {
            status = "recheck-required";
        }
        let evidence = if status == "reviewed"
            && !checks.is_empty()
            && checks.iter().all(|c| c["status"] == "match")
        {
            "current"
        } else if status == "reviewed" {
            "unknown"
        } else {
            status
        };
        out["revision_status"] = json!(status);
        out["source_checks"] = json!(checks);
        out["evidence_status"] = json!(evidence);
        out
    }
    fn access_member(
        &self,
        requested: &str,
        declaring: &str,
        m: &Value,
        p: &Value,
        detailed: bool,
    ) -> Value {
        let name = text(&m["Name"]);
        let kind = text(&m["MemberType"]);
        let key = format!("{declaring}.{name}");
        let behavior = self.behavior_rows(&key, p);
        let mut ops = serde_json::Map::new();
        let operations: &[&str] = match kind {
            "Property" => &["read", "write"],
            "Event" => &["connect"],
            "Callback" => &["assign_callback"],
            _ => &["call"],
        };
        for op in operations {
            let title = match *op {
                "read" => "Read",
                "write" => "Write",
                "connect" => "Connect",
                "assign_callback" => "Assign_Callback",
                _ => "Call",
            };
            let extract = |key: &str| {
                let v = get(m, key);
                if v.is_object() {
                    get(&v, title)
                } else {
                    v
                }
            };
            let sec = extract("Security");
            let caps = extract("Capabilities");
            let mut reasons = Vec::new();
            if contains(&m["Tags"], "NotScriptable") {
                reasons.push("NotScriptable".to_owned());
            }
            if *op == "write" && contains(&m["Tags"], "ReadOnly") {
                reasons.push("ReadOnly".to_owned());
            }
            if !sec.is_null() && sec != "None" && sec != "unknown" {
                reasons.push(format!("requires {}", s(&sec)));
            }
            let denied = !reasons.is_empty();
            let mut contexts = serde_json::Map::new();
            for context in [
                "game-server",
                "game-client",
                "studio-plugin",
                "command-bar",
                "mcp-edit",
                "mcp-server",
                "mcp-client",
            ] {
                contexts.insert(
                    context.into(),
                    json!(if denied && context.starts_with("game-") {
                        "denied"
                    } else {
                        "unknown"
                    }),
                );
            }
            ops.insert((*op).into(),json!({"security":sec,"capabilities":caps,"contexts":contexts,"ordinary_game_denial_basis":reasons}));
        }
        let mut runtime = json!({"edit_configuration":"unknown","runtime_assignment":"unknown","effective_when":"unknown","replication":"unknown","persistence":"unknown"});
        for b in &behavior {
            if b["evidence_status"] == "current" && b["status"] == "documented" {
                if let Some(map) = b["runtime"][&key].as_object() {
                    for (k, v) in map {
                        runtime[k] = v.clone();
                    }
                }
            }
        }
        let routes: Vec<String> = behavior
            .iter()
            .map(|b| format!("harness api behavior {}", text(&b["id"])))
            .collect();
        let mut out = json!({"record":"access","requested_class":requested,"declaring_class":declaring,"member":name,"kind":kind,"operations":ops,"tags":get(m,"Tags"),"thread_safety":get(m,"ThreadSafety"),"serialization":get(m,"Serialization"),"simulation_access":get(m,"SimulationAccess"),"runtime":runtime,"behavior_routes":routes});
        if detailed {
            let docs = self.description(
                declaring,
                Self::members(&self.y("classes", declaring))
                    .get(name)
                    .unwrap_or(&Value::Null),
            );
            let mut differences = Vec::new();
            for (dk, mk) in [
                ("security", "Security"),
                ("capabilities", "Capabilities"),
                ("tags", "Tags"),
                ("thread_safety", "ThreadSafety"),
            ] {
                if let (Some(d), Some(v)) = (docs["metadata"].get(dk), m.get(mk)) {
                    let norm = |v: &Value| -> Value {
                        if let Some(o) = v.as_object() {
                            Value::Object(
                                o.iter()
                                    .map(|(k, v)| (k.to_lowercase(), v.clone()))
                                    .collect(),
                            )
                        } else {
                            v.clone()
                        }
                    };
                    if norm(d) != norm(v) {
                        differences.push(json!({"field":dk,"api_dump":v,"creator_docs":d,"status":if std::mem::discriminant(d)==std::mem::discriminant(v) {"conflict"}else{"different-representation"},"next":"compare source definitions per operation; do not choose permissive evidence"}));
                    }
                }
            }
            out["api_dump_member"] = m.clone();
            out["documentation"] = docs;
            out["behavior"] = json!(behavior);
            out["metadata_differences"] = json!(differences);
        }
        out
    }
    fn evidence(&self, verb: &str, query: &str, p: &Value) -> Vec<Value> {
        if verb == "behavior" {
            let rows = self.behavior_rows(query, p);
            if rows.is_empty() {
                return vec![
                    json!({"record":"miss","query":query,"next":"use docs/find and full descriptions; research the exact context before a probe"}),
                ];
            }
            return rows
                .into_iter()
                .map(|mut r| {
                    r["record"] = json!("behavior");
                    r["provenance"] = p.clone();
                    r
                })
                .collect();
        }
        let re = Regex::new(r"^([A-Za-z0-9_]+)(?:[.:]([A-Za-z0-9_]+))?$").unwrap();
        let Some(cap) = re.captures(query) else {
            return vec![
                json!({"record":"miss","query":query,"next":"use access Class[.Member] or inventory Class"}),
            ];
        };
        let requested = &cap[1];
        let wanted = cap.get(2).map(|m| m.as_str());
        if verb == "inventory" && wanted.is_some() {
            return vec![
                json!({"record":"miss","query":query,"next":"use access Class[.Member] or inventory Class"}),
            ];
        }
        if self.class(requested).is_none() {
            return vec![
                json!({"record":"miss","query":query,"next":"verify class spelling and corpus revision"}),
            ];
        }
        let chain = self.chain(requested);
        let contexts:Vec<Value>=chain.iter().filter_map(|n| self.class(n).map(|c| json!({"name":n,"tags":get(c,"Tags"),"security":get(c,"Security"),"capabilities":get(c,"Capabilities"),"documentation":self.description(n,&self.y("classes",n))}))).collect();
        let mut result = vec![
            json!({"record":"class-context","requested_class":requested,"classes":contexts,"sources":p,"assessment_scope":"game contexts mean ordinary game code without elevated identity; unknown requires caller capabilities, class restrictions, execution phase and behavior evidence"}),
        ];
        if verb == "access" && wanted.is_none() {
            return result;
        }
        let mut seen = HashSet::new();
        for n in chain {
            if let Some(c) = self.class(&n) {
                for m in arr(&c["Members"]) {
                    let name = text(&m["Name"]);
                    if !seen.insert(name.to_owned()) {
                        continue;
                    }
                    if (verb == "inventory" && m["MemberType"] == "Property")
                        || wanted == Some(name)
                    {
                        result.push(self.access_member(requested, &n, m, p, verb != "inventory"));
                        if verb != "inventory" {
                            return result;
                        }
                    }
                }
            }
        }
        if wanted.is_some() {
            result.push(json!({"record":"miss","query":query,"next":"verify member spelling and source revisions; no access claim"}));
        }
        result
    }
}

fn evidence_print(mut v: Value) {
    v["schema"] = json!("roblox-evidence-v1");
    println!("{}", v);
}
fn reference(
    kind: &str,
    v: Value,
    shared: &mut serde_json::Map<String, Value>,
    ids: &mut HashMap<String, String>,
) -> Value {
    let key = format!("{kind}:{}", v);
    let id = if let Some(id) = ids.get(&key) {
        id.clone()
    } else {
        let id = format!("{kind}-{}", shared.len() + 1);
        ids.insert(key, id.clone());
        shared.insert(id.clone(), v);
        id
    };
    json!({"$ref":id})
}
fn batch(c: &Corpus, args: &[String]) -> i32 {
    if args.is_empty()
        || args.len() % 2 != 0
        || args
            .chunks(2)
            .any(|p| !["access", "inventory", "behavior"].contains(&p[0].as_str()))
    {
        evidence_print(
            json!({"record":"miss","query":"batch","next":"supply access/inventory/behavior QUERY pairs"}),
        );
        return 2;
    }
    if !c.need_dump() {
        return 3;
    }
    let p = c.provenance();
    let mut shared = serde_json::Map::new();
    let mut ids = HashMap::new();
    let mut results = Vec::new();
    for pair in args.chunks(2) {
        let mut records = Vec::new();
        for mut record in c.evidence(&pair[0], &pair[1], &p) {
            record["schema"] = json!("roblox-evidence-v1");
            match text(&record["record"]) {
                "class-context" => {
                    record["sources"] = reference(
                        "provenance",
                        record["sources"].clone(),
                        &mut shared,
                        &mut ids,
                    );
                    let classes = arr(&record["classes"])
                        .iter()
                        .map(|v| reference("class", v.clone(), &mut shared, &mut ids))
                        .collect::<Vec<_>>();
                    record["classes"] = json!(classes);
                    record = reference("context", record, &mut shared, &mut ids);
                }
                "behavior" => {
                    let source = reference(
                        "provenance",
                        record["provenance"].clone(),
                        &mut shared,
                        &mut ids,
                    );
                    let map = record.as_object_mut().unwrap();
                    map.remove("provenance");
                    map.remove("schema");
                    map.remove("record");
                    record = reference("behavior", record, &mut shared, &mut ids);
                    record["schema"] = json!("roblox-evidence-v1");
                    record["record"] = json!("behavior");
                    record["provenance"] = source;
                }
                "access" if record.get("behavior").is_some() => {
                    record["behavior"] = json!(arr(&record["behavior"])
                        .iter()
                        .map(|v| reference("behavior", v.clone(), &mut shared, &mut ids))
                        .collect::<Vec<_>>());
                }
                _ => {}
            }
            records.push(record);
        }
        results.push(json!({"verb":pair[0],"query":pair[1],"records":records}));
    }
    println!(
        "{}",
        json!({"schema":"roblox-evidence-batch-v1","shared":shared,"results":results})
    );
    0
}
fn render_type(v: &Value) -> String {
    if v.is_object() {
        let n = v.get("Name").map(s).unwrap_or_else(|| "void".into());
        if v["Category"] == "Enum" {
            format!("Enum.{n}")
        } else {
            n
        }
    } else {
        s(v)
    }
}
fn summary(entry: &Value) -> String {
    let a = line(&entry["summary"]);
    let b = line(&entry["deprecation_message"]);
    if b.is_empty() {
        a
    } else if a.is_empty() {
        b
    } else {
        format!("{a} - {b}")
    }
}
impl Corpus {
    fn header(&self, c: &Value) -> String {
        let name = text(&c["Name"]);
        let y = self.y("classes", name);
        let chain = self
            .chain(name)
            .into_iter()
            .skip(1)
            .collect::<Vec<_>>()
            .join(",");
        let mut ts = tags(&c["Tags"], CLASS_TAGS);
        let sample = text(arr(&y["code_samples"]).first().unwrap_or(&Value::Null));
        let mut sum = summary(&y);
        if let Some(h) = self.overlay.get(name) {
            if !ts.is_empty() {
                ts.push(',');
            }
            ts.push_str("house");
            if !sum.is_empty() {
                sum.push_str("; ");
            }
            sum.push_str(&format!("house: {}", line(&json!(h))));
        }
        format!(
            "{name}|{}|{}|{}|{}",
            field(&chain),
            field(&ts),
            field(sample),
            field(&sum)
        )
    }
    fn member_record(
        &self,
        cls: &str,
        m: &Value,
        ym: &HashMap<String, Value>,
        qualify: bool,
    ) -> String {
        let name = text(&m["Name"]);
        let kind = text(&m["MemberType"]);
        let prefix = if qualify { cls } else { "" };
        let params = arr(&m["Parameters"])
            .iter()
            .map(|p| {
                let default = if kind == "Function" && !p["Default"].is_null() && p["Default"] != ""
                {
                    format!("={}", s(&p["Default"]))
                } else {
                    String::new()
                };
                format!(
                    "{}:{}{}",
                    text(&p["Name"]),
                    render_type(&p["Type"]),
                    default
                )
            })
            .collect::<Vec<_>>()
            .join(",");
        let (sig, ret) = match kind {
            "Property" => (format!("{prefix}.{name}"), render_type(&m["ValueType"])),
            "Function" => {
                let rt = &m["ReturnType"];
                let r = if let Some(a) = rt.as_array() {
                    a.iter().map(render_type).collect::<Vec<_>>().join(",")
                } else if rt.is_null() {
                    "void".into()
                } else {
                    render_type(rt)
                };
                (
                    format!("{prefix}:{name}({params})"),
                    if r.is_empty() || r == "null" || r == "()" {
                        "void".into()
                    } else {
                        r
                    },
                )
            }
            "Event" => (
                format!("{prefix}.{name}({params})"),
                "RBXScriptSignal".into(),
            ),
            _ => (
                format!("{prefix}.{name}({params})"),
                if m["ReturnType"].is_null() {
                    "void".into()
                } else {
                    render_type(&m["ReturnType"])
                },
            ),
        };
        let entry = ym.get(name).unwrap_or(&Value::Null);
        let sample = text(arr(&entry["code_samples"]).first().unwrap_or(&Value::Null));
        let mut ts = tags(&m["Tags"], MEMBER_TAGS);
        let mut sum = summary(entry);
        if let Some(h) = self
            .overlay
            .get(&format!("{cls}:{name}"))
            .or_else(|| self.overlay.get(&format!("{cls}.{name}")))
        {
            if !ts.is_empty() {
                ts.push(',');
            }
            ts.push_str("house");
            if !sum.is_empty() {
                sum.push_str("; ");
            }
            sum.push_str(&format!("house: {}", line(&json!(h))));
        }
        format!(
            "{sig}|{}|{}|{}|{}|{}",
            field(&ret),
            field(text(&m["ThreadSafety"])),
            field(&ts),
            field(sample),
            field(&sum)
        )
    }
    fn visible(m: &Value, all: bool) -> bool {
        let sec = m.get("Security").unwrap_or(&json!("None")).clone();
        all || if sec.is_object() {
            sec.get("Read").unwrap_or(&json!("None")) == "None"
        } else {
            sec == "None"
        }
    }
    fn legacy_class(&self, name: &str, verb: &str, all: bool) {
        let Some(c) = self.class(name) else {
            println!("miss|{name}|no such class");
            return;
        };
        println!("{}", self.header(c));
        let chain = if verb == "instance" {
            self.chain(name)
        } else {
            vec![name.to_owned()]
        };
        for n in chain {
            if let Some(c) = self.class(&n) {
                let ym = Self::members(&self.y("classes", &n));
                for m in arr(&c["Members"]) {
                    if (verb != "props" || m["MemberType"] == "Property") && Self::visible(m, all) {
                        println!(
                            "{}",
                            self.member_record(&n, m, &ym, verb == "instance" && n != name)
                        );
                    }
                }
            }
        }
    }
    fn enum_print(&self, name: &str, items: bool) {
        let Some(e) = arr(&self.dump["Enums"])
            .iter()
            .find(|e| text(&e["Name"]) == name)
        else {
            println!("miss|{name}|no such enum");
            return;
        };
        let y = self.y("enums", name);
        let ts = tags(&e["Tags"], CLASS_TAGS);
        let sum = line(&y["summary"]);
        println!("{name}|void|{}|void|{}", field(&ts), field(&sum));
        if items {
            for item in arr(&e["Items"]) {
                let n = text(&item["Name"]);
                let yi = arr(&y["items"])
                    .iter()
                    .find(|v| text(&v["name"]) == n)
                    .unwrap_or(&Value::Null);
                let ts = tags(&item["Tags"], MEMBER_TAGS);
                let sum = line(&yi["summary"]);
                println!(
                    ".{n}|{}|void|{}|void|{}",
                    s(&item["Value"]),
                    field(&ts),
                    field(&sum)
                );
            }
        }
    }
    fn ops(&self, name: &str) -> Vec<(String, String, String, String, String)> {
        let y = self.y("datatypes", name);
        let mut rows: Vec<_> = arr(&y["math_operations"])
            .iter()
            .map(|v| {
                (
                    text(&v["operation"]).to_owned(),
                    text(&v["type_a"]).to_owned(),
                    text(&v["type_b"]).to_owned(),
                    text(&v["return_type"]).to_owned(),
                    "doc".to_owned(),
                )
            })
            .collect();
        let syn: Vec<_> = rows
            .iter()
            .filter(|(o, a, b, _, _)| {
                ["*", "/", "//"].contains(&o.as_str()) && b == "number" && a != "number"
            })
            .map(|(o, a, _, r, _)| {
                (
                    o.clone(),
                    "number".into(),
                    a.clone(),
                    r.clone(),
                    "syn".into(),
                )
            })
            .collect();
        rows.extend(syn);
        rows
    }
    fn find_index(&self) -> Value {
        let path = self.cache.join("find_index.json");
        let index = json_file(&path);
        let manifest = json_file(&self.cache.join("corpus-refresh.json"));
        if index["schema"] == 1
            && index["classes"].is_object()
            && index["enums"].is_object()
            && ["api_dump_sha256", "creator_docs_revision"]
                .iter()
                .all(|k| !text(&manifest[*k]).is_empty() && index[*k] == manifest[*k])
        {
            return index;
        }
        let stamp = !path.exists() && self.engine.is_dir();
        let index = self.build_find(stamp);
        if stamp {
            let _ = atomic_json(&path, &index);
        }
        index
    }
    fn build_find(&self, stamp: bool) -> Value {
        let mut classes = serde_json::Map::new();
        for c in self.classes() {
            let name = text(&c["Name"]);
            let y = self.y("classes", name);
            let mut members = serde_json::Map::new();
            for (n, e) in Self::members(&y) {
                let sum = summary(&e);
                if !sum.is_empty() {
                    members.insert(n, json!(sum));
                }
            }
            classes.insert(
                name.into(),
                json!({"summary":line(&y["summary"]),"members":members}),
            );
        }
        let mut enums = serde_json::Map::new();
        for e in arr(&self.dump["Enums"]) {
            let n = text(&e["Name"]);
            let sum = line(&self.y("enums", n)["summary"]);
            if !sum.is_empty() {
                enums.insert(n.into(), json!(sum));
            }
        }
        let mut out = json!({"schema":1,"classes":classes,"enums":enums});
        if stamp {
            out["api_dump_sha256"] = json!(sha(&self.cache.join("API-Dump.json")));
            out["creator_docs_revision"] = json!(self.rev());
        }
        out
    }
    fn find(&self, terms: &[String], all: bool) {
        if terms.is_empty() {
            println!("miss|void|no terms");
            return;
        }
        let index = self.find_index();
        let score = |name: &str, sum: &str| -> usize {
            let n = name.to_lowercase();
            let s = sum.to_lowercase();
            terms
                .iter()
                .filter(|t| !t.is_empty())
                .map(|t| {
                    let t = t.to_lowercase();
                    3 * usize::from(n.contains(&t)) + s.matches(&t).count()
                })
                .sum()
        };
        let mut hits: Vec<(usize, usize, String, Value)> = Vec::new();
        for c in self.classes() {
            let n = text(&c["Name"]);
            let entry = &index["classes"][n];
            let sc = score(n, text(&entry["summary"]));
            if sc > 0 {
                hits.push((sc, 0, n.into(), c.clone()));
            }
            for m in arr(&c["Members"]) {
                if !Self::visible(m, all) {
                    continue;
                }
                let mn = text(&m["Name"]);
                let sc = score(mn, text(&entry["members"][mn]));
                if sc > 0 {
                    hits.push((sc, 1, n.into(), m.clone()));
                }
            }
        }
        for e in arr(&self.dump["Enums"]) {
            let n = text(&e["Name"]);
            let sc = score(n, text(&index["enums"][n]));
            if sc > 0 {
                hits.push((sc, 2, n.into(), e.clone()));
            }
        }
        hits.sort_by(|a, b| b.0.cmp(&a.0).then(a.1.cmp(&b.1)));
        for (_, kind, n, v) in hits.into_iter().take(20) {
            match kind {
                0 => println!("{}", self.header(&v)),
                1 => println!(
                    "{}",
                    self.member_record(&n, &v, &Self::members(&self.y("classes", &n)), true)
                ),
                _ => {
                    let t = tags(&v["Tags"], CLASS_TAGS);
                    let sum = text(&index["enums"][&n]);
                    println!("{n}|void|{}|void|{}", field(&t), field(sum));
                }
            }
        }
    }
}

fn front(path: &Path) -> (Value, String) {
    let t = fs::read_to_string(path).unwrap_or_default();
    if let Some(rest) = t.strip_prefix("---\n") {
        if let Some((fm, body)) = rest.split_once("\n---") {
            let body = body.strip_prefix('\n').unwrap_or(body);
            let mut map = serde_json::Map::new();
            for l in fm.lines() {
                if let Some((k, v)) = l.split_once(':') {
                    if k == "title" || k == "description" {
                        let x = v.trim();
                        let val = serde_yaml::from_str::<Value>(x).unwrap_or(json!(x));
                        map.insert(k.into(), val);
                    }
                }
            }
            return (json!(map), body.into());
        }
    }
    (Value::Null, t)
}
fn slug(s: &str) -> String {
    Regex::new("[^a-z0-9]+")
        .unwrap()
        .replace_all(&s.to_lowercase(), "-")
        .trim_matches('-')
        .to_owned()
}
fn headings(body: &str) -> Vec<(usize, String)> {
    let re = Regex::new(r"^(#{1,4})\s+(.+)$").unwrap();
    body.lines()
        .filter_map(|l| re.captures(l).map(|c| (c[1].len(), c[2].trim().to_owned())))
        .collect()
}
impl Corpus {
    fn build_docs(&self) -> Value {
        let mut out = Vec::new();
        for e in walkdir::WalkDir::new(&self.content)
            .into_iter()
            .filter_map(|x| x.ok())
            .filter(|x| x.file_type().is_file())
        {
            let path = e.path();
            if path.extension().and_then(|x| x.to_str()) != Some("md") {
                continue;
            }
            let rel = path
                .strip_prefix(&self.content)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            if ["education/", "production/", "creator-programs/"]
                .iter()
                .any(|p| rel.starts_with(p))
                || (rel.starts_with("resources/")
                    && !["resources/modules/", "resources/feature-packages/"]
                        .iter()
                        .any(|p| rel.starts_with(p)))
            {
                continue;
            }
            let (fm, _) = front(path);
            if fm.get("title").is_some() {
                out.push(json!({"path":rel,"title":s(&fm["title"]),"description":if fm["description"].is_null(){String::new()}else{s(&fm["description"])}}));
            }
        }
        json!(out)
    }
    fn docs(&self, terms: &[String]) -> i32 {
        let path = self.cache.join("docs_index.json");
        let data = fs::read(&path)
            .ok()
            .and_then(|s| serde_json::from_slice::<Value>(&s).ok());
        let Some(index) = data else {
            println!("ENV|docs-index-absent-or-malformed|run api_dump --sync to rebuild the local docs index");
            return 3;
        };
        if !index.is_array() {
            println!(
                "ENV|docs-index-malformed|run api_dump --sync to rebuild the local docs index"
            );
            return 3;
        }
        let mut rows: Vec<(usize, &Value)> = arr(&index)
            .iter()
            .filter_map(|e| {
                let mut score = 0;
                for t in terms.iter().filter(|t| !t.is_empty()) {
                    let t = t.to_lowercase();
                    if text(&e["title"]).to_lowercase().contains(&t) {
                        score += 3;
                    }
                    if text(&e["description"]).to_lowercase().contains(&t) {
                        score += 1;
                    }
                    if text(&e["path"]).to_lowercase().contains(&t) {
                        score += 1;
                    }
                }
                if score > 0 {
                    Some((score, e))
                } else {
                    None
                }
            })
            .collect();
        rows.sort_by(|a, b| b.0.cmp(&a.0));
        for (_, e) in rows.into_iter().take(20) {
            let title = line(&e["title"]);
            let desc = line(&e["description"]);
            println!("{}|{}|{}", text(&e["path"]), field(&title), field(&desc));
        }
        0
    }
    fn doc(&self, spec: &str, code: bool) {
        let (rel, anchor) = if code {
            (spec, None)
        } else {
            spec.split_once('#')
                .map(|(a, b)| (a, Some(b)))
                .unwrap_or((spec, None))
        };
        let path = self.content.join(rel);
        if !path.exists() {
            println!("miss|{rel}|no such doc");
            return;
        }
        let (_, mut body) = front(&path);
        if code {
            let re = Regex::new(r"(?s)```(?:lua|luau)\n(.*?)```").unwrap();
            for (i, c) in re.captures_iter(&body).enumerate() {
                let block = &c[1];
                println!("{spec}#{}|api-evidence", i + 1);
                print!("{block}");
                if !block.ends_with('\n') {
                    println!();
                }
            }
            return;
        }
        if anchor.is_none() && body.len() >= 20 * 1024 {
            let h = headings(&body)
                .into_iter()
                .map(|(_, h)| slug(&h))
                .collect::<Vec<_>>()
                .join(",");
            println!("{rel}|{}KB|{}", body.len() / 1024, field(&h));
            return;
        }
        if let Some(a) = anchor.filter(|a| !a.is_empty()) {
            let re = Regex::new(r"^(#{1,4})\s+(.+)$").unwrap();
            let mut out = Vec::new();
            let mut level = 0;
            for l in body.split('\n') {
                if let Some(c) = re.captures(l) {
                    if level > 0 && c[1].len() <= level {
                        break;
                    }
                    if slug(&c[2]) == a {
                        level = c[1].len();
                    }
                }
                if level > 0 {
                    out.push(l);
                }
            }
            if out.is_empty() {
                println!("miss|{rel}#{a}|no such heading");
                return;
            }
            body = out.join("\n");
        }
        print!("{body}");
        if !body.ends_with('\n') {
            println!();
        }
    }
    fn sample(&self, spec: &str) -> Result<()> {
        let re = Regex::new(r"^([A-Za-z0-9_]+):([A-Za-z0-9_]+)$").unwrap();
        let Some(cap) = re.captures(spec) else {
            println!("miss|{spec}|expected Class:Member");
            return Ok(());
        };
        let cls = &cap[1];
        let member = &cap[2];
        let y = self.y("classes", cls);
        if y.is_null() {
            println!("miss|{cls}|no class yaml");
            return Ok(());
        }
        let entries = Self::members(&y);
        if arr(&entries.get(member).unwrap_or(&Value::Null)["code_samples"]).is_empty() {
            return Ok(());
        }
        let declared: HashSet<String> = entries
            .iter()
            .filter(|(_, v)| !arr(&v["code_samples"]).is_empty())
            .map(|(k, _)| k.clone())
            .collect();
        let dir = self.cache.join("samples");
        fs::create_dir_all(&dir)?;
        let path = dir.join(format!("{cls}.json"));
        let mut cached = json_file(&path);
        if !cached.is_object() {
            let url = format!("https://create.roblox.com/docs/reference/engine/classes/{cls}");
            let result = reqwest::blocking::Client::builder()
                .timeout(std::time::Duration::from_secs(20))
                .user_agent("Mozilla/5.0")
                .build()?
                .get(url)
                .send()
                .and_then(|r| r.error_for_status())
                .and_then(|r| r.text());
            let Ok(html) = result else {
                eprintln!("WARN sample-fetch-failed {cls} - serving nothing, never blocking");
                return Ok(());
            };
            let html = html.replace("\\n", "\n").replace("\\\"", "\"");
            let blocks = Regex::new(r"(?s)```lua\n(.*?)```").unwrap();
            let words = Regex::new(r"\b([A-Za-z0-9_]+)\b").unwrap();
            let anchors: Vec<_> = words
                .find_iter(&html)
                .filter(|m| declared.contains(m.as_str()))
                .collect();
            let mut map: HashMap<String, Vec<String>> = HashMap::new();
            for block in blocks.captures_iter(&html) {
                let start = block.get(0).unwrap().start();
                if let Some(a) = anchors.iter().rev().find(|a| a.start() < start) {
                    map.entry(a.as_str().into())
                        .or_default()
                        .push(block[1].into());
                }
            }
            if map.len() < declared.len() {
                eprintln!(
                    "WARN sample-anchor-parse {cls}: {} members extracted, {} declared",
                    map.len(),
                    declared.len()
                );
            }
            cached = json!(map);
            let _ = fs::write(path, cached.to_string());
        }
        let blocks = arr(&cached[member]);
        if !blocks.is_empty() {
            println!("{spec}|api-evidence");
            for b in blocks {
                let b = text(b);
                print!("{b}");
                if !b.ends_with('\n') {
                    println!();
                }
            }
        }
        Ok(())
    }
    fn library(&self, name: &str) {
        let y = self.y("libraries", name);
        if y.is_null() {
            println!("miss|{name}|no such library");
            return;
        }
        let throws = self.thrown("libraries");
        let ts = arr(&y["tags"])
            .iter()
            .filter_map(Value::as_str)
            .collect::<Vec<_>>()
            .join(",");
        let sum = line(&y["summary"]);
        println!("{name}|void|{}|void|{}", field(&ts), field(&sum));
        for kind in ["properties", "functions"] {
            for m in arr(&y[kind]) {
                let qual = text(&m["name"]);
                let short = qual.rsplit('.').next().unwrap_or("");
                let params = arr(&m["parameters"])
                    .iter()
                    .map(|p| {
                        let ty = Regex::new(r"\s*\|\s*")
                            .unwrap()
                            .replace_all(text(&p["type"]), "|")
                            .into_owned();
                        let d = if p["default"].is_null() || p["default"] == "" {
                            String::new()
                        } else {
                            format!("={}", s(&p["default"]))
                        };
                        format!("{}:{ty}{d}", text(&p["name"]))
                    })
                    .collect::<Vec<_>>()
                    .join(",");
                let (sig, ret) = if kind == "functions" {
                    let r = arr(&m["returns"])
                        .iter()
                        .filter_map(|v| v["type"].as_str())
                        .filter(|s| !s.is_empty())
                        .collect::<Vec<_>>()
                        .join(",");
                    (
                        format!(".{short}({params})"),
                        if r.is_empty() || r == "()" {
                            "void".into()
                        } else {
                            r
                        },
                    )
                } else {
                    (
                        format!(".{short}"),
                        m.get("type").map(s).unwrap_or_else(|| "void".into()),
                    )
                };
                let mut ts = arr(&m["tags"])
                    .iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>();
                if throws.contains(qual) {
                    ts.push("Throws");
                }
                let ts = ts.join(",");
                let sum = line(&m["summary"]);
                println!(
                    "{sig}|{}|{}|{}|void|{}",
                    field(&ret),
                    field(text(&m["thread_safety"])),
                    field(&ts),
                    field(&sum)
                );
            }
        }
    }
}

fn throws(prose: &str) -> bool {
    let re = Regex::new(r"(?i)\bthrows?\b|\bwill throw\b|\bthrowing\b|\berror will be (?:generated|raised|thrown)\b|\ban error is (?:generated|raised|thrown)\b|\braises? an error\b|\bwill (?:error|raise)\b|\berrors? (?:if|when|upon|on)\b|\bresults? in an error\b").unwrap();
    let neg = Regex::new(r"(?i)\b(?:not|never|no|without|rather than)\s+(?:\w+\s+){0,2}$").unwrap();
    let result = re.find_iter(prose).any(|m| {
        let mut start = m.start().saturating_sub(24);
        while !prose.is_char_boundary(start) {
            start += 1;
        }
        !neg.is_match(&prose[start..m.start()])
    });
    result
}
impl Corpus {
    fn thrown(&self, kind: &str) -> HashSet<String> {
        let mut out = HashSet::new();
        let dir = self.engine.join(kind);
        let Ok(entries) = fs::read_dir(dir) else {
            return out;
        };
        for ent in entries.flatten() {
            let path = ent.path();
            if path.extension().and_then(|x| x.to_str()) != Some("yaml") {
                continue;
            }
            let y = yaml(&path);
            let cls = text(&y["name"]);
            let groups: &[&str] = if kind == "classes" {
                &["properties", "methods", "events", "callbacks"]
            } else {
                &["properties", "functions"]
            };
            for group in groups {
                for e in arr(&y[*group]) {
                    let prose = format!("{} {}", text(&e["summary"]), text(&e["description"]))
                        .split_whitespace()
                        .collect::<Vec<_>>()
                        .join(" ");
                    if throws(&prose) {
                        let name = text(&e["name"]);
                        out.insert(if kind == "classes" {
                            format!(
                                "{}:{}",
                                if cls.is_empty() {
                                    path.file_stem().and_then(|x| x.to_str()).unwrap_or("")
                                } else {
                                    cls
                                },
                                name.rsplit(['.', ':']).next().unwrap_or("")
                            )
                        } else {
                            name.into()
                        });
                    }
                }
            }
        }
        out
    }
    fn globals(&self, updates: Option<&str>) -> Result<()> {
        let mut services = Vec::new();
        let mut nc = Vec::new();
        let mut constraints = Vec::new();
        let mut bodies = Vec::new();
        let mut yields = Vec::new();
        let mut canyield = Vec::new();
        let mut safe = Vec::new();
        let mut streaming = Vec::new();
        for c in self.classes() {
            let name = text(&c["Name"]);
            if contains(&c["Tags"], "Service") {
                services.push(name.to_owned());
            }
            if contains(&c["Tags"], "NotCreatable") {
                nc.push(name.to_owned());
            }
            let chain = self.chain(name);
            if chain.iter().any(|s| s == "Constraint") {
                constraints.push(name.to_owned());
            }
            if chain.iter().any(|s| s == "BodyMover") {
                bodies.push(name.to_owned());
            }
            for m in arr(&c["Members"]) {
                let key = format!("{name}:{}", text(&m["Name"]));
                if contains(&m["Tags"], "Yields") {
                    yields.push(key.clone());
                }
                if contains(&m["Tags"], "CanYield") {
                    canyield.push(key.clone());
                }
                let ts = text(&m["ThreadSafety"]);
                if ts == "Safe" || ts == "ReadSafe" {
                    safe.push((key, ts.to_owned()));
                }
                if (name == "Workspace" || name == "Model")
                    && m["MemberType"] == "Property"
                    && text(&m["Name"]).contains("Stream")
                {
                    let sec = &m["Security"];
                    let write = if sec.is_object() {
                        text(&sec["Write"])
                    } else {
                        text(sec)
                    };
                    let mut tags = arr(&m["Tags"])
                        .iter()
                        .filter_map(Value::as_str)
                        .map(str::to_owned)
                        .collect::<Vec<_>>();
                    if !write.is_empty() && write != "None" {
                        tags.push(write.into());
                    }
                    streaming.push((text(&m["Name"]).to_owned(), name.to_owned(), tags.join(",")));
                }
            }
        }
        services.sort();
        nc.sort();
        constraints.sort();
        bodies.sort();
        yields.sort();
        canyield.sort();
        safe.sort();
        streaming.sort();
        let mut thrown = self.thrown("classes");
        thrown.extend(self.thrown("libraries"));
        let mut thrown: Vec<_> = thrown.into_iter().collect();
        thrown.sort();
        let mut ops = Vec::new();
        for dt in [
            "Vector2",
            "Vector3",
            "Vector2int16",
            "Vector3int16",
            "CFrame",
            "UDim",
            "UDim2",
        ] {
            ops.extend(self.ops(dt));
        }
        let docops = ops.iter().filter(|x| x.4 == "doc").count();
        let quote = |s: &str| format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\""));
        let mut lines = vec![
            "-- generated by api_dump --emit-globals; refresh explicitly after an API dump update"
                .to_owned(),
            "return {".into(),
            format!(
                "\tservices = {{ {} }},",
                services
                    .iter()
                    .map(|s| quote(s))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
        ];
        for (key, values) in [
            ("notcreatable", &nc),
            ("constraints", &constraints),
            ("bodymovers", &bodies),
            ("yields", &yields),
            ("canyield", &canyield),
            ("throws", &thrown),
        ] {
            lines.push(format!("\t{key} = {{"));
            for v in values {
                lines.push(format!("\t\t[{}] = true,", quote(v)));
            }
            lines.push("\t},".into());
        }
        lines.push("\tthreadsafe = {".into());
        for (k, v) in safe {
            lines.push(format!("\t\t[{}] = {},", quote(&k), quote(&v)));
        }
        lines.push("\t},".into());
        lines.push("\tstreaming = {".into());
        for (n, c, t) in streaming {
            lines.push(format!(
                "\t\t[{}] = {{ class = {}, tags = {} }},",
                quote(&n),
                quote(&c),
                quote(&t)
            ));
        }
        lines.push("\t},".into());
        lines.push("\tops = {".into());
        for (o, a, b, r, src) in ops {
            lines.push(format!(
                "\t\t{{ op = {}, a = {}, b = {}, ret = {}, src = {} }},",
                quote(&o),
                quote(&a),
                quote(&b),
                quote(&r),
                quote(&src)
            ));
        }
        lines.push("\t},".into());
        lines.push("\tupdates = {".into());
        let mut versions = Vec::new();
        if let Some(dir) = updates {
            if let Ok(entries) = fs::read_dir(dir) {
                let re = Regex::new("ReleaseDate\\s*=\\s*\"([^\"]+)\"").unwrap();
                for e in entries.flatten() {
                    let path = e.path();
                    if !["lua", "luau"]
                        .contains(&path.extension().and_then(|x| x.to_str()).unwrap_or(""))
                        || ["init.lua", "init.luau"]
                            .contains(&path.file_name().and_then(|x| x.to_str()).unwrap_or(""))
                    {
                        continue;
                    }
                    if let Ok(t) = fs::read_to_string(&path) {
                        if let Some(m) = re.captures(&t) {
                            versions.push((
                                path.file_stem().unwrap().to_string_lossy().to_string(),
                                m[1].to_owned(),
                            ));
                        }
                    }
                }
            }
        }
        versions.sort();
        for (k, v) in versions {
            lines.push(format!("\t\t[{}] = {},", quote(&k), quote(&v)));
        }
        lines.push("\t},".into());
        lines.push("}".into());
        fs::create_dir_all(&self.cache)?;
        let path = self.cache.join("api_globals.luau");
        let tmp = path.with_extension(format!("{}.tmp", std::process::id()));
        fs::write(&tmp, format!("{}\n", lines.join("\n")))?;
        fs::rename(tmp, &path)?;
        println!(
            "{}|{}c|{}s|{}ops|{}throws",
            path.display(),
            self.classes().len(),
            services.len(),
            docops,
            thrown.len()
        );
        Ok(())
    }
    fn sync(&mut self) -> Result<i32> {
        let docs = self.cache.join("creator-docs");
        let index_path = self.cache.join("docs_index.json");
        let manifest_path = self.cache.join("corpus-refresh.json");
        let manifest = json_file(&manifest_path);
        let assets = if !self.cache.join("API-Dump.json").is_file() {
            Some("API-Dump.json is missing")
        } else if !docs.join(".git").is_dir() {
            Some("Creator Docs .git is missing")
        } else if !self.engine.is_dir() {
            Some("Creator Docs engine corpus is missing")
        } else if !index_path.is_file() {
            Some("docs_index.json is missing")
        } else if !self.dump["Classes"].is_array() || !self.dump["Enums"].is_array() {
            Some("API-Dump.json has an invalid schema")
        } else if !json_file(&index_path).is_array() {
            Some("docs_index.json has an invalid schema")
        } else if !walkdir::WalkDir::new(&self.engine)
            .into_iter()
            .filter_map(|e| e.ok())
            .any(|e| {
                ["yaml", "yml"]
                    .contains(&e.path().extension().and_then(|x| x.to_str()).unwrap_or(""))
            })
        {
            Some("Creator Docs engine corpus has no YAML records")
        } else {
            None
        };
        let age = manifest["refreshed_at"].as_f64().map(|t| now() - t);
        let malformed = assets.is_some_and(|e| !e.contains("missing"))
            || (assets.is_none()
                && manifest_path.exists()
                && (age.is_none() || age.is_some_and(|a| a < -300.0)));
        if assets.is_none() && age.is_some_and(|a| (-300.0..86400.0).contains(&a)) {
            println!("sync|fresh|no network or Creator Docs Git writes");
            let idx = json_file(&self.cache.join("find_index.json"));
            if idx["schema"] != 1
                || !idx["classes"].is_object()
                || !idx["enums"].is_object()
                || ["api_dump_sha256", "creator_docs_revision"]
                    .iter()
                    .any(|k| text(&manifest[*k]).is_empty() || manifest[*k] != idx[*k])
            {
                atomic_json(&self.cache.join("find_index.json"), &self.build_find(true))?;
                println!("find-index|rebuilt|local corpus");
            }
            return Ok(0);
        }
        if malformed {
            println!(
                "sync|repairing-malformed|{}",
                assets.unwrap_or(if age.is_none() {
                    "successful-refresh timestamp is malformed"
                } else {
                    "successful-refresh timestamp is in the future"
                })
            );
        }
        let find = self.cache.join("find_index.json");
        let _ = fs::remove_file(&find);
        println!("find-index|deleted|{}", find.display());
        fs::create_dir_all(&self.cache)?;
        let download = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(60))
            .user_agent("harness/api_dump")
            .build()?
            .get(DUMP_URL)
            .send()
            .and_then(|r| r.error_for_status())
            .and_then(|r| r.bytes());
        let data = match download {
            Ok(v) => v,
            Err(e) => {
                println!("ENV|api-dump-sync-failed|check network/cache permission, then retry harness api --sync: {}",e.to_string().chars().take(120).collect::<String>());
                return Ok(3);
            }
        };
        let dump: Value = serde_json::from_slice(&data).unwrap_or(Value::Null);
        if !dump["Classes"].is_array() || !dump["Enums"].is_array() {
            println!("ENV|api-dump-malformed|retry harness api --sync after the upstream response is valid");
            return Ok(3);
        }
        let target = self.cache.join("API-Dump.json");
        let tmp = target.with_extension(format!("{}.tmp", std::process::id()));
        if let Err(e) = fs::write(&tmp, &data).and_then(|_| fs::rename(&tmp, &target)) {
            let _ = fs::remove_file(&tmp);
            println!("ENV|api-dump-sync-failed|check network/cache permission, then retry harness api --sync: {}",e.to_string().chars().take(120).collect::<String>());
            return Ok(3);
        }
        self.dump = dump;
        println!("dump|synced|{} bytes", data.len());
        let git = |args: &[&std::ffi::OsStr]| {
            Command::new("git")
                .env("GIT_LFS_SKIP_SMUDGE", "1")
                .env("GIT_OPTIONAL_LOCKS", "0")
                .args(args)
                .output()
                .map(|o| o.status.success())
                .unwrap_or(false)
        };
        if !docs.join(".git").is_dir() {
            let clone = self
                .cache
                .join(format!("creator-docs.sync-{}", std::process::id()));
            let _ = fs::remove_dir_all(&clone);
            if !git(&[
                "clone".as_ref(),
                "--depth".as_ref(),
                "1".as_ref(),
                "https://github.com/Roblox/creator-docs".as_ref(),
                clone.as_os_str(),
            ]) {
                let _ = fs::remove_dir_all(clone);
                println!("ENV|creator-docs-sync-failed|check network/cache permission, then retry harness api --sync");
                return Ok(3);
            }
            let quarantine = if docs.exists() {
                let q = self
                    .cache
                    .join(format!("creator-docs.malformed-{}", now() as u64));
                if let Err(e) = fs::rename(&docs, &q) {
                    let _ = fs::remove_dir_all(&clone);
                    println!(
                        "ENV|creator-docs-sync-failed|could not quarantine malformed cache: {}",
                        e.to_string().chars().take(120).collect::<String>()
                    );
                    return Ok(3);
                }
                Some(q)
            } else {
                None
            };
            if let Err(e) = fs::rename(&clone, &docs) {
                if let Some(q) = quarantine {
                    let _ = fs::rename(q, &docs);
                }
                let _ = fs::remove_dir_all(clone);
                println!(
                    "ENV|creator-docs-sync-failed|could not install repaired cache: {}",
                    e.to_string().chars().take(120).collect::<String>()
                );
                return Ok(3);
            }
            println!("docs|cloned|{}", docs.display());
        } else {
            if malformed
                && !git(&[
                    "-C".as_ref(),
                    docs.as_os_str(),
                    "restore".as_ref(),
                    "--source=HEAD".as_ref(),
                    "--worktree".as_ref(),
                    "--".as_ref(),
                    ".".as_ref(),
                ])
            {
                println!(
                    "ENV|creator-docs-sync-failed|could not restore malformed generated docs cache"
                );
                return Ok(3);
            }
            if !git(&[
                "-C".as_ref(),
                docs.as_os_str(),
                "pull".as_ref(),
                "--ff-only".as_ref(),
                "--deepen".as_ref(),
                "50".as_ref(),
            ]) {
                println!("ENV|creator-docs-sync-failed|check network/cache permission, then retry harness api --sync");
                return Ok(3);
            }
            println!("docs|synced|{}", docs.display());
        }
        let index = self.build_docs();
        atomic_json(&index_path, &index)?;
        println!("index|rebuilt|{} files", arr(&index).len());
        if !self.engine.is_dir()
            || !walkdir::WalkDir::new(&self.engine)
                .into_iter()
                .filter_map(|e| e.ok())
                .any(|e| {
                    ["yaml", "yml"]
                        .contains(&e.path().extension().and_then(|x| x.to_str()).unwrap_or(""))
                })
        {
            println!("ENV|corpus-malformed|Creator Docs engine corpus has no YAML records");
            return Ok(3);
        }
        let idx = self.build_find(true);
        atomic_json(&find, &idx)?;
        println!(
            "find-index|rebuilt|{} classes, {} enums",
            idx["classes"].as_object().map_or(0, |o| o.len()),
            idx["enums"].as_object().map_or(0, |o| o.len())
        );
        atomic_json(
            &manifest_path,
            &json!({"refreshed_at":now(),"api_dump_sha256":sha(&self.cache.join("API-Dump.json")),"creator_docs_revision":self.rev()}),
        )?;
        println!("refresh|successful|{}", now() as u64);
        Ok(0)
    }
}

const HELP: &str = "harness api — flat lookup over the Roblox API dump + creator-docs clone.

Reference verbs answer what a call IS; doc verbs answer what it is FOR.
Output is records, not a report: one record per line, pipe-delimited, fixed
field positions; `void` fills an empty field. Schemas are listed below.

  header   name|super|tags|sample|summary
  member   sig|ret|threadsafety|tags|sample|summary
  ops      op|a|b|ret|src
  docs     path|title|description
  ENV      ENV|cause|remedy

Exit codes: 0 ok · 2 crash · 3 environment precondition unmet.
Security-filtered by default: only Security.Read == \"None\" members surface;
--all lifts the filter for a deliberate lookup.

Additive evidence verbs emit JSON lines with schema roblox-evidence-v1:
  access Class[.Member]  Full restrictions, inherited owner and class prose.
  inventory Class       All inherited properties, including restricted ones.
  behavior TopicOrAPI   Sourced operational decisions and scoped unknowns.
  batch VERB QUERY ...  Batch access/inventory/behavior pairs; shared evidence
                        appears once in roblox-evidence-batch-v1. Resolve $ref
                        through shared, then apply any sibling fields.
These verbs do not change legacy records. Unknown is not permission. ReadSafe
is parallel read safety, not write permission, replication, or startup timing.";

pub fn run(args: &[OsString]) -> Result<i32> {
    let all = args.iter().any(|a| a == "--all");
    let args: Vec<String> = args
        .iter()
        .filter(|a| *a != "--all")
        .map(|a| a.to_string_lossy().into_owned())
        .collect();
    let mut c = Corpus::new();
    if args.is_empty() {
        println!("{HELP}");
        return Ok(0);
    }
    let verb = args[0].as_str();
    let rest = &args[1..];
    if verb == "--sync" {
        return c.sync();
    }
    if verb == "batch" {
        return Ok(batch(&c, rest));
    }
    if ["access", "inventory", "behavior"].contains(&verb) {
        if rest.len() != 1 {
            evidence_print(
                json!({"record":"miss","query":verb,"next":"supply one class, member or behavior topic"}),
            );
            return Ok(2);
        }
        if !c.need_dump() {
            return Ok(3);
        }
        let p = c.provenance();
        for record in c.evidence(verb, &rest[0], &p) {
            evidence_print(record);
        }
        return Ok(0);
    }
    if [
        "class",
        "instance",
        "props",
        "services",
        "enum",
        "enumitems",
        "find",
        "--check-overlay",
        "--emit-globals",
        "describe",
    ]
    .contains(&verb)
        && !c.need_dump()
    {
        return Ok(3);
    }
    if [
        "library",
        "ops",
        "describe",
        "sample",
        "docs",
        "doc",
        "code",
        "--emit-globals",
    ]
    .contains(&verb)
        && !c.need_docs()
    {
        return Ok(3);
    }
    let name = rest.first().map(String::as_str).unwrap_or("");
    match verb {
        "class" | "instance" | "props" => c.legacy_class(name, verb, all),
        "services" => {
            let mut names: Vec<_> = c
                .classes()
                .iter()
                .filter(|v| contains(&v["Tags"], "Service"))
                .map(|v| text(&v["Name"]))
                .collect();
            names.sort();
            println!("{}", names.join(","));
        }
        "enum" | "enumitems" => c.enum_print(name, verb == "enumitems"),
        "find" => c.find(rest, all),
        "library" => c.library(name),
        "ops" => {
            let rows = c.ops(name);
            if rows.is_empty() {
                println!("miss|{name}|no math_operations");
            } else {
                for (o, a, b, r, src) in rows {
                    println!(
                        "{}|{}|{}|{}|{src}",
                        field(&o),
                        field(&a),
                        field(&b),
                        field(&r)
                    );
                }
            }
        }
        "describe" => {
            let re = Regex::new(r"^([A-Za-z0-9_]+)[.:]([A-Za-z0-9_]+)$").unwrap();
            if let Some(cap) = re.captures(name) {
                let cls = &cap[1];
                let member = &cap[2];
                let y = Corpus::members(&c.y("classes", cls));
                if let (Some(class), Some(entry)) = (c.class(cls), y.get(member)) {
                    if let Some(m) = arr(&class["Members"])
                        .iter()
                        .find(|m| text(&m["Name"]) == member)
                    {
                        println!("{}", c.member_record(cls, m, &y, false));
                    }
                    let desc = strip_markup(text(&entry["description"]));
                    if !desc.trim().is_empty() {
                        println!("{}", desc.trim());
                    }
                } else {
                    println!("miss|{name}|not in corpus");
                }
            } else {
                println!("miss|{name}|expected Class.Member");
            }
        }
        "docs" => return Ok(c.docs(rest)),
        "doc" => c.doc(name, false),
        "code" => c.doc(name, true),
        "sample" => c.sample(name)?,
        "--emit-globals" => {
            let updates = rest
                .iter()
                .position(|x| x == "--updates")
                .and_then(|i| rest.get(i + 1))
                .map(String::as_str);
            c.globals(updates)?;
        }
        "--check-overlay" => {
            let re = Regex::new(r"^([A-Za-z0-9_]+)(?:[.:]([A-Za-z0-9_]+))?$").unwrap();
            let mut dead = false;
            for key in c.overlay.keys() {
                let valid = re.captures(key).is_some_and(|cap| {
                    c.class(&cap[1]).is_some_and(|cls| {
                        cap.get(2).is_none_or(|member| {
                            arr(&cls["Members"])
                                .iter()
                                .any(|m| text(&m["Name"]) == member.as_str())
                        })
                    })
                });
                if !valid {
                    println!("overlay|{key}|dead");
                    dead = true;
                }
            }
            return Ok(if dead { 2 } else { 0 });
        }
        _ => {
            println!("miss|{verb}|unknown verb");
            return Ok(2);
        }
    }
    Ok(0)
}
