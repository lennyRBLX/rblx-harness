use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    process::{Command, Output},
};

fn run(home: &Path, root: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_harness"))
        .env("HOME", home)
        .arg("--root")
        .arg(root)
        .args(args)
        .output()
        .expect("launch harness")
}

fn text(output: &Output) -> String {
    String::from_utf8(output.stdout.clone()).expect("UTF-8 output")
}

fn success(output: &Output) {
    assert!(
        output.status.success(),
        "stdout: {}\nstderr: {}",
        text(output),
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn api_access_evidence_preserves_restrictions() {
    let tmp = tempfile::tempdir().unwrap();
    let home = tmp.path();
    let cache = home.join(".cache/harness");
    fs::create_dir_all(&cache).unwrap();
    let dump = json!({"Version": 1, "Enums": [], "Classes": [
        {"Name": "Base", "Superclass": "<<<ROOT>>>", "Tags": ["NotCreatable"], "Members": [
            {"Name": "Secret", "MemberType": "Property", "ThreadSafety": "ReadSafe",
             "Security": {"Read": "None", "Write": "PluginSecurity"},
             "Capabilities": {"Read": ["Basic"], "Write": ["StudioPlugin"]}, "Tags": ["ReadOnly"]},
            {"Name": "Unknown", "MemberType": "Property"},
            {"Name": "Locked", "MemberType": "Property", "Security": {"Read": "None", "Write": "None"}, "Tags": ["NotScriptable"]}
        ]},
        {"Name": "Child", "Superclass": "Base", "Members": []}
    ]});
    fs::write(cache.join("API-Dump.json"), dump.to_string()).unwrap();
    let output = run(home, tmp.path(), &["api", "access", "Child.Secret"]);
    success(&output);
    let records: Vec<Value> = text(&output)
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert_eq!(records.len(), 2);
    assert_eq!(records[0]["record"], "class-context");
    assert_eq!(records[0]["classes"][1]["name"], "Base");
    let member = &records[1];
    assert_eq!(member["schema"], "roblox-evidence-v1");
    assert_eq!(member["requested_class"], "Child");
    assert_eq!(member["declaring_class"], "Base");
    assert_eq!(member["operations"]["read"]["security"], "None");
    assert_eq!(
        member["operations"]["read"]["contexts"]["game-server"],
        "unknown"
    );
    assert_eq!(member["operations"]["write"]["security"], "PluginSecurity");
    assert_eq!(
        member["operations"]["write"]["capabilities"],
        json!(["StudioPlugin"])
    );
    assert_eq!(
        member["operations"]["write"]["contexts"]["game-client"],
        "denied"
    );
    assert_eq!(
        member["operations"]["write"]["contexts"]["studio-plugin"],
        "unknown"
    );
    assert_eq!(
        member["operations"]["write"]["ordinary_game_denial_basis"],
        json!(["ReadOnly", "requires PluginSecurity"])
    );
    assert_eq!(member["runtime"]["replication"], "unknown");
    assert_eq!(member["documentation"]["status"], "missing");

    let output = run(home, tmp.path(), &["api", "access", "Child.Unknown"]);
    success(&output);
    let unknown: Vec<Value> = text(&output)
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert_eq!(unknown[1]["operations"]["read"]["security"], "unknown");
    assert_eq!(
        unknown[1]["operations"]["read"]["contexts"]["game-server"],
        "unknown"
    );
    let output = run(home, tmp.path(), &["api", "access", "Child.Locked"]);
    success(&output);
    let locked: Vec<Value> = text(&output)
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert_eq!(
        locked[1]["operations"]["read"]["contexts"]["game-server"],
        "denied"
    );
    assert_eq!(
        locked[1]["operations"]["read"]["ordinary_game_denial_basis"],
        json!(["NotScriptable"])
    );
    let output = run(home, tmp.path(), &["api", "access", "Child.Missing"]);
    success(&output);
    let missing: Vec<Value> = text(&output)
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert_eq!(missing[1]["record"], "miss");
}

#[test]
fn type_cache_preserves_validation() {
    let tmp = tempfile::tempdir().unwrap();
    let home = tmp.path().join("home");
    let root = tmp.path().join("project");
    let source = root.join("shared/src/ReplicatedStorage/Types/Inventory.luau");
    fs::create_dir_all(source.parent().unwrap()).unwrap();
    fs::create_dir_all(&home).unwrap();
    fs::write(&source, "export type Item = { count: number }\nreturn {}\n").unwrap();

    let verify = run(&home, &root, &["types", "cache", "verify"]);
    assert_eq!(verify.status.code(), Some(2));
    assert_eq!(text(&verify).trim(), "STALE|missing");
    let ensure = run(&home, &root, &["types", "cache", "ensure"]);
    success(&ensure);
    assert_eq!(text(&ensure).trim(), "OK|rebuilt");
    let verify = run(&home, &root, &["types", "cache", "verify"]);
    success(&verify);
    assert_eq!(text(&verify).trim(), "OK|current");
    let read = run(&home, &root, &["types", "read", "--type", "Item"]);
    success(&read);
    assert!(text(&read).contains("count: number"));
    let bad = run(
        &home,
        &root,
        &["types", "read", "--request", "[{\"scope\":\"type\"}]"],
    );
    assert_eq!(bad.status.code(), Some(2));
    assert!(text(&bad).contains("BLOCKED|WRIT33|type_name is required"));

    fs::write(&source, "export type Item = { count: string }\nreturn {}\n").unwrap();
    let verify = run(&home, &root, &["types", "cache", "verify"]);
    assert_eq!(verify.status.code(), Some(2));
    assert_eq!(text(&verify).trim(), "STALE|stale");
    let read = run(&home, &root, &["types", "read", "--type", "Item"]);
    success(&read);
    assert!(text(&read).contains("count: string"));
    assert!(!text(&read).contains("count: number"));
    let verify = run(&home, &root, &["types", "cache", "verify"]);
    success(&verify);
    assert_eq!(text(&verify).trim(), "OK|current");

    let cache_dir = home.join(".cache/harness/type_cache");
    let index = fs::read_dir(cache_dir)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .find(|path| path.extension().is_some_and(|ext| ext == "json"))
        .unwrap();
    let mut saved: Value = serde_json::from_slice(&fs::read(&index).unwrap()).unwrap();
    saved["definitions"][0]["declaration"] = json!("export type Item = { count: boolean }");
    fs::write(index, saved.to_string()).unwrap();
    let verify = run(&home, &root, &["types", "cache", "verify"]);
    assert_eq!(verify.status.code(), Some(2));
    assert_eq!(text(&verify).trim(), "STALE|stale");
    let read = run(&home, &root, &["types", "read", "--type", "Item"]);
    success(&read);
    assert!(text(&read).contains("count: string"));
    assert!(!text(&read).contains("count: boolean"));
}
