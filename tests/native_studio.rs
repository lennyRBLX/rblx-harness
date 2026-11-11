use std::{fs, path::Path, process::Command};

fn run(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_harness"))
        .args(args)
        .output()
        .expect("start harness")
}

fn generate(args: &[&str], output: &Path) -> String {
    let result = run(args);
    assert!(
        result.status.success(),
        "harness failed: {}{}",
        String::from_utf8_lossy(&result.stdout),
        String::from_utf8_lossy(&result.stderr)
    );
    fs::read_to_string(output).expect("generated command")
}

// Decode the quoted Luau literal following a generated assignment. This checks
// actual encoded bytes independently of the implementation's encoder.
fn assigned_bytes(command: &str, prefix: &str) -> Vec<u8> {
    let rest = command
        .split_once(prefix)
        .expect("missing assignment")
        .1
        .as_bytes();
    assert_eq!(rest.first(), Some(&b'"'));
    let mut bytes = Vec::new();
    let mut i = 1;
    while rest[i] != b'"' {
        if rest[i] == b'\\' {
            assert!(rest[i + 1..i + 4].iter().all(u8::is_ascii_digit));
            let n = (rest[i + 1] - b'0') as u16 * 100
                + (rest[i + 2] - b'0') as u16 * 10
                + (rest[i + 3] - b'0') as u16;
            bytes.push(u8::try_from(n).unwrap());
            i += 4;
        } else {
            bytes.push(rest[i]);
            i += 1;
        }
    }
    bytes
}

fn before(command: &str, first: &str, second: &str) {
    let a = command
        .find(first)
        .unwrap_or_else(|| panic!("missing {first:?}"));
    let b = command
        .find(second)
        .unwrap_or_else(|| panic!("missing {second:?}"));
    assert!(a < b, "{first:?} must precede {second:?}");
}

#[test]
fn hot_reload_and_source_persistence_refuse_stale_state_and_preserve_callers() {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path();
    let old = root.join("original.luau");
    let new = root.join("changed.luau");
    let target = root.join("target.json");
    let output = root.join("command.luau");
    let old_bytes = b"return {Value = \"old\"}\r\n";
    let new_bytes = "return {Value = \"炎\"}\r\n".as_bytes();
    fs::write(&old, old_bytes).unwrap();
    fs::write(&new, new_bytes).unwrap();
    fs::write(&target, r#"["ReplicatedStorage", "Quoted\".炎"]"#).unwrap();
    let old_path = old.to_str().unwrap();
    let new_path = new.to_str().unwrap();
    let target_path = target.to_str().unwrap();
    let out_path = output.to_str().unwrap();

    let args = [
        "studio",
        "reload",
        "patch",
        "--side",
        "Server",
        "--session",
        "HR1",
        "--path-file",
        target_path,
        "--source",
        new_path,
        "--expected",
        old_path,
        "--revision",
        "0",
        "--audited",
        "--output",
        out_path,
    ];
    let patch = generate(&args, &output);
    assert_eq!(assigned_bytes(&patch, "local Expected = "), old_bytes);
    assert_eq!(assigned_bytes(&patch, "Candidate.Source = "), new_bytes);
    assert!(patch.contains("ExpectedRevision = 0"));
    before(
        &patch,
        "assert(State.Revision == Request.ExpectedRevision",
        "local Candidate = Target:Clone()",
    );
    before(
        &patch,
        "assert(Target.Source == Expected",
        "local Candidate = Target:Clone()",
    );
    before(
        &patch,
        "assert(Editor:GetEditorSource(Target) == Expected",
        "local Candidate = Target:Clone()",
    );
    before(
        &patch,
        "assert(State.Status ~= \"Pending\"",
        "local Candidate = Target:Clone()",
    );
    before(
        &patch,
        "Candidate.Source = ",
        "Root.Command:Invoke(Request)",
    );
    assert!(patch.contains("if not Success then\n    Candidate:Destroy()"));
    assert!(!patch.contains("Target.Source = "));
    assert!(patch.contains("Ambiguous path segment"));
    assert!(patch.contains("Quoted\\034.\\231\\130\\142"));

    let undo = generate(
        &[
            "studio",
            "reload",
            "undo",
            "--side",
            "Server",
            "--session",
            "HR1",
            "--path-file",
            target_path,
            "--revision",
            "1",
            "--output",
            out_path,
        ],
        &output,
    );
    assert!(undo.contains("ExpectedRevision = 1"));
    assert!(undo.contains("Root.Command:Invoke(Request)"));
    assert!(!undo.contains("Target.Source = "));
    let bootstrap = generate(
        &[
            "studio",
            "reload",
            "bootstrap",
            "--side",
            "Client",
            "--session",
            "HR1",
            "--output",
            out_path,
        ],
        &output,
    );
    assert!(bootstrap.contains("PlayerScripts"));
    assert!(bootstrap.contains("Instance.new(\"LocalScript\")"));
    let snapshot = generate(
        &[
            "studio",
            "source",
            "snapshot",
            "--side",
            "Edit",
            "--path-file",
            target_path,
            "--output",
            out_path,
        ],
        &output,
    );
    assert!(snapshot.contains("Stored = Target.Source, Editor = Editor:GetEditorSource(Target)"));
    assert!(!snapshot.contains("Target.Source = "));
    let persist = generate(
        &[
            "studio",
            "source",
            "persist",
            "--side",
            "Edit",
            "--path-file",
            target_path,
            "--source",
            new_path,
            "--expected",
            old_path,
            "--expected-editor",
            old_path,
            "--output",
            out_path,
        ],
        &output,
    );
    assert_eq!(assigned_bytes(&persist, "local Expected = "), old_bytes);
    assert_eq!(
        assigned_bytes(&persist, "local ExpectedEditor = "),
        old_bytes
    );
    assert_eq!(assigned_bytes(&persist, "local NewSource = "), new_bytes);
    before(
        &persist,
        "assert(not RunService:IsRunning()",
        "Editor:UpdateSourceAsync",
    );
    before(
        &persist,
        "assert(Target.Source == Expected",
        "Editor:UpdateSourceAsync",
    );
    before(
        &persist,
        "assert(Editor:GetEditorSource(Target) == ExpectedEditor",
        "Editor:UpdateSourceAsync",
    );
    before(
        &persist,
        "if Current ~= ExpectedEditor or Target.Source ~= Expected then",
        "return NewSource",
    );
    before(
        &persist,
        "assert(Editor:GetEditorSource(Target) == NewSource",
        "Target.Source = NewSource",
    );
    before(
        &persist,
        "assert(Target.Source == Expected or Target.Source == NewSource",
        "Target.Source = NewSource",
    );

    generate(&args, &output);
    let original = fs::read(&output).unwrap();
    for (flag, replacement) in [
        ("--session", Some("bad/ID")),
        ("--revision", Some("-1")),
        ("--side", Some("Edit")),
        ("--path-file", Some(old_path)),
        ("--output", Some(old_path)),
        ("--audited", None),
    ] {
        let mut invalid = args.to_vec();
        let index = invalid.iter().position(|arg| *arg == flag).unwrap();
        if let Some(value) = replacement {
            invalid[index + 1] = value;
        } else {
            invalid.remove(index);
        }
        let result = run(&invalid);
        assert!(!result.status.success(), "accepted invalid {flag}");
        assert_eq!(
            fs::read(&output).unwrap(),
            original,
            "invalid {flag} changed output"
        );
        assert_eq!(
            fs::read(&old).unwrap(),
            old_bytes,
            "invalid {flag} changed input"
        );
        assert_eq!(
            fs::read(&new).unwrap(),
            new_bytes,
            "invalid {flag} changed input"
        );
    }
    for invalid_path in ["[]", "[\"\"]", "[42]", "not-json"] {
        fs::write(&target, invalid_path).unwrap();
        assert!(
            !run(&args).status.success(),
            "accepted invalid path {invalid_path}"
        );
        assert_eq!(fs::read(&output).unwrap(), original);
    }
}
