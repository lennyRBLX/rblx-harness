use rblx_harness::buffer::{decode, encode_records, Collector};
use serde_json::{json, Value};
use std::{
    ffi::OsString,
    fs,
    path::Path,
    process::{Command, Output, Stdio},
};

fn cli(root: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_harness"))
        .arg("--root")
        .arg(root)
        .args(args)
        .env("HOME", root)
        .output()
        .unwrap()
}
fn stdout(out: &Output) -> String {
    String::from_utf8(out.stdout.clone()).unwrap()
}
fn response(out: &Output) -> Value {
    serde_json::from_slice(&out.stdout).unwrap_or_else(|_| {
        panic!(
            "stdout: {} stderr: {}",
            stdout(out),
            String::from_utf8_lossy(&out.stderr)
        )
    })
}
fn git(root: &Path, args: &[&str]) {
    let out = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
}

#[test]
fn project_validation_boot_output_and_verification_selection() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    git(root, &["init", "-q"]);
    fs::write(
        root.join("manifest.json"),
        r#"{"schema":1,"places":["Main"],"assets":["plugin","unknown"]}"#,
    )
    .unwrap();
    let errors = rblx_harness::project_gate::validate(root);
    assert!(errors
        .iter()
        .any(|e| e.contains("marker: .roblox is absent")));
    assert!(errors.iter().any(|e| e.contains("legacy plugin asset")));
    assert!(errors.iter().any(|e| e.contains("unknown assets")));
    assert!(errors.iter().any(|e| e.contains("project Main")));
    let boot = cli(root, &["studio", "boot"]);
    assert_eq!(boot.status.code(), Some(3));
    let verdict = response(&boot);
    assert_eq!(verdict["pass"], false);
    assert_eq!(verdict["environment"]["cause"], "no-project");
    let list = cli(
        root,
        &["check", "harness", "--list", "--case", "BOOT OUTPUT"],
    );
    assert!(
        list.status.success(),
        "{}",
        String::from_utf8_lossy(&list.stderr)
    );
    assert_eq!(
        stdout(&list).trim(),
        "project validation, boot output, and verification selection"
    );
    let missing = cli(
        root,
        &[
            "check",
            "harness",
            "--list",
            "--case",
            "no-such-workflow-xyz",
        ],
    );
    assert_eq!(missing.status.code(), Some(2));
}

#[test]
fn session_audit_bounded_context_and_console_deltas() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    let home = root.join("codex");
    fs::create_dir_all(home.join("sessions")).unwrap();
    fs::create_dir_all(home.join("archived_sessions")).unwrap();
    let call = json!({"type":"response_item","payload":{"type":"function_call","call_id":"c1","name":"read","arguments":"abcd"}});
    let output = json!({"type":"response_item","payload":{"type":"function_call_output","call_id":"c1","output":"abcdefgh"}});
    let meta = json!({"type":"session_meta","payload":{"id":"root","cwd":"/tmp/TargetProject"}});
    fs::write(
        home.join("sessions/root.jsonl"),
        format!("{meta}\n{call}\n{output}\nnot-json\n"),
    )
    .unwrap();
    let child = json!({"type":"session_meta","payload":{"id":"child","parent_thread_id":"root","cwd":"/elsewhere"}});
    fs::write(
        home.join("archived_sessions/child.jsonl"),
        format!("{child}\n{call}\n"),
    )
    .unwrap();
    let unrelated = json!({"type":"session_meta","payload":{"id":"other","cwd":"/other"}});
    fs::write(home.join("sessions/other.jsonl"), format!("{unrelated}\n")).unwrap();
    let stem = root.join("audit");
    let args: Vec<OsString> = vec![
        "--project".into(),
        "targetproject".into(),
        "--codex-home".into(),
        home.into_os_string(),
        "--output".into(),
        stem.clone().into_os_string(),
    ];
    assert_eq!(rblx_harness::session::run(&args).unwrap(), 0);
    let report: Value =
        serde_json::from_slice(&fs::read(stem.with_extension("json")).unwrap()).unwrap();
    assert_eq!(report["coverage"]["session_files"], 2);
    assert_eq!(report["coverage"]["agent_sessions"], 1);
    assert_eq!(report["coverage"]["copied_calls_removed"], 1);
    assert_eq!(report["coverage"]["calls_missing_output"], 0);
    assert_eq!(
        report["sessions"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s["malformed_lines"].as_u64().unwrap())
            .sum::<u64>(),
        1
    );
    fs::write(root.join("source.luau"), "one\ntwo\nthree\n").unwrap();
    let bounded = cli(
        root,
        &[
            "inspect",
            "--max-chars",
            "3",
            "--no-cache",
            "read",
            "--file",
            "source.luau:2:3",
        ],
    );
    let pack = response(&bounded);
    assert_eq!(pack["preview_complete"], false);
    assert_eq!(pack["items"][0]["text"], "two");
    assert_eq!(
        cli(
            root,
            &["inspect", "--no-cache", "read", "--file", "../outside"]
        )
        .status
        .code(),
        Some(2)
    );
    let log = root.join("console.log");
    fs::write(&log, "old line\n").unwrap();
    let logstr = log.to_str().unwrap();
    let first = cli(root, &["studio", "output", "--input", logstr]);
    assert!(first.status.success());
    let first_text = stdout(&first);
    let artifact = first_text
        .lines()
        .find_map(|l| l.strip_prefix("OUTPUT|baseline|artifact="))
        .unwrap();
    fs::write(&log, "old line\nnew line\n").unwrap();
    let second = cli(
        root,
        &["studio", "output", "--input", logstr, "--since", artifact],
    );
    let text = stdout(&second);
    assert!(second.status.success());
    assert!(text.contains("new line"));
    assert!(!text.contains("old line"));
    assert!(text.contains("OUTPUT|append|"));
    fs::write(&log, "rotated\n").unwrap();
    let rotated = cli(
        root,
        &["studio", "output", "--input", logstr, "--since", artifact],
    );
    assert!(stdout(&rotated).contains("OUTPUT|reset-or-rotation|"));
}

#[test]
fn local_atc_overlap_concurrent_scope_leases_and_lifecycle_cleanup() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    git(root, &["init", "-q"]);
    let spawn = |owner: &str| {
        Command::new(env!("CARGO_BIN_EXE_harness"))
            .arg("--root")
            .arg(root)
            .args(["coord", "begin", "--owner", owner, "--path", "src"])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap()
    };
    let a = spawn("one");
    let b = spawn("two");
    let a = a.wait_with_output().unwrap();
    let b = b.wait_with_output().unwrap();
    let va = response(&a);
    let vb = response(&b);
    assert!(matches!(
        (va["state"].as_str(), vb["state"].as_str()),
        (Some("owned"), Some("busy")) | (Some("busy"), Some("owned"))
    ));
    let (owner, lease) = if va["state"] == "owned" {
        ("one", va["lease"].as_i64().unwrap())
    } else {
        ("two", vb["lease"].as_i64().unwrap())
    };
    let lease = lease.to_string();
    let nested = cli(
        root,
        &[
            "coord",
            "check",
            "--owner",
            owner,
            "--lease",
            &lease,
            "--path",
            "src/nested",
        ],
    );
    assert_eq!(response(&nested)["state"], "owned");
    let outside = cli(
        root,
        &[
            "coord",
            "check",
            "--owner",
            owner,
            "--lease",
            &lease,
            "--path",
            "src-other",
        ],
    );
    assert_eq!(response(&outside)["state"], "outsideScope");
    let disjoint = cli(
        root,
        &["coord", "begin", "--owner", "third", "--path", "src-other"],
    );
    assert_eq!(response(&disjoint)["state"], "owned");
    let invalid = cli(
        root,
        &["coord", "begin", "--owner", "fourth", "--path", "../escape"],
    );
    assert_eq!(response(&invalid)["state"], "unknown");
    assert_eq!(
        response(&cli(
            root,
            &["coord", "end", "--owner", owner, "--lease", &lease]
        ))["state"],
        "ended"
    );
    assert_eq!(
        response(&cli(
            root,
            &["coord", "check", "--owner", owner, "--lease", &lease]
        ))["state"],
        "stale"
    );
    assert_eq!(
        response(&cli(root, &["coord", "check", "--path", "src"]))["state"],
        "clear"
    );
}

#[test]
fn test_buffer_capture_coverage_collection_and_cleanup_boundaries() {
    let raw = b"HTB1\nR\tcase\tpass\t1\t0\t0\t-\nM\trun\tload\tscript\t2\t15\t10\t8\t1\t0\t100\nP\trun\tload\tscript\t2\t10\n";
    let mut large = String::from("HTB1\nR\tcase\tpass\t1\t0\t0\t-\n");
    for i in 0..20 {
        large.push_str(&format!(
            "M\tmethod{i}\tload\tscript\t1\t5\t5\t8\t0\t0\t0\n"
        ));
    }
    let chunks = encode_records(large.as_bytes(), "SERVER", "Test", "large").unwrap();
    assert!(chunks.len() > 1);
    let mut partial = Collector::new(None);
    partial.feed(&chunks[0]);
    assert!(partial.finish().is_err());
    let mut complete = Collector::new(None);
    for chunk in chunks.iter().rev() {
        complete.feed(chunk);
    }
    assert_eq!(complete.finish().unwrap()[0].result.metrics.len(), 20);
    let parsed = decode(raw).unwrap();
    assert_eq!(parsed.passed, 1);
    assert_eq!(parsed.metrics[0].spikes, vec![(2, 10)]);
    assert!(decode(b"HTB1\nR\tcase\tpass\t0\t0\t0\t-\n").is_err());
    assert!(decode(b"HTB1\nR\tcase\tpass\t1\t0\t0\t-").is_err());
    let records = encode_records(raw, "SERVER", "Test", "run1").unwrap();
    let mut collector = Collector::new(Some(("SERVER".into(), "Test".into(), "run1".into())));
    collector.feed(&format!("noise\n{}\n{}\n", records[0], records[0]));
    let result = collector.finish().unwrap();
    assert_eq!(result.len(), 1);
    assert_eq!(result[0].result.metrics[0].spikes.len(), 1);
    let wrong_side = encode_records(raw, "CLIENT", "Test", "run1").unwrap();
    let mut collector = Collector::new(Some(("SERVER".into(), "Test".into(), "run1".into())));
    collector.feed(&wrong_side.join("\n"));
    assert!(collector.finish().is_err());
    let mut corrupted = records[0].clone();
    let last = corrupted.pop().unwrap();
    corrupted.push(if last == '0' { '1' } else { '0' });
    let mut collector = Collector::new(None);
    collector.feed(&corrupted);
    assert!(collector.finish().is_err());
    let dir = tempfile::tempdir().unwrap();
    let log = dir.path().join("capture.log");
    fs::write(&log, records.join("\n")).unwrap();
    let ok = cli(
        dir.path(),
        &[
            "studio",
            "decode",
            log.to_str().unwrap(),
            "--side",
            "SERVER",
            "--script",
            "Test",
            "--run",
            "run1",
        ],
    );
    assert!(ok.status.success(), "{}", stdout(&ok));
    let wrong = cli(
        dir.path(),
        &[
            "studio",
            "decode",
            log.to_str().unwrap(),
            "--side",
            "SERVER",
            "--script",
            "Test",
            "--run",
            "other",
        ],
    );
    assert_eq!(wrong.status.code(), Some(2));
    assert!(stdout(&wrong).contains("rejected"));
}
