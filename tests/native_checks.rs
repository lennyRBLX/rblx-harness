use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn lute() -> PathBuf {
    root()
        .join("tools/bin")
        .join(format!("lute{}", std::env::consts::EXE_SUFFIX))
}

fn text(output: &Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    )
}

fn names(dir: &Path, extension: Option<&str>) -> Vec<String> {
    let mut result: Vec<_> = fs::read_dir(dir)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|path| match extension {
            Some(ext) => path.extension().is_some_and(|value| value == ext),
            None => path.join("SKILL.md").is_file(),
        })
        .map(|path| {
            if extension.is_some() {
                path.file_stem().unwrap().to_string_lossy().into_owned()
            } else {
                path.file_name().unwrap().to_string_lossy().into_owned()
            }
        })
        .collect();
    result.sort();
    result
}

#[test]
fn repository_surface_is_seven_skills_and_five_agents_for_codex_and_claude_code() {
    let root = root();
    assert!(root.join("Cargo.toml").is_file());
    assert!(root.join("src/main.rs").is_file());
    let skills = names(&root.join("shared/skills"), None);
    assert_eq!(
        skills,
        [
            "rblx-debug",
            "rblx-gui",
            "rblx-new-game",
            "rblx-optimize",
            "rblx-plan",
            "rblx-test",
            "rblx-writer"
        ]
    );
    for skill in &skills {
        assert!(
            root.join("shared/skills")
                .join(skill)
                .join("agents/openai.yaml")
                .is_file(),
            "{skill}"
        );
    }
    let agents = [
        "debugger",
        "implementer",
        "optimizer",
        "researcher",
        "reviewer",
    ];
    assert_eq!(names(&root.join("openai/agents"), Some("toml")), agents);
    assert_eq!(names(&root.join("anthropic/agents"), Some("md")), agents);
    assert!(root.join("anthropic/config/settings.json").is_file());

    // Validate the actual definitions using the same public gates used for projects.
    let temp = tempfile::tempdir().unwrap();
    for (host, source, ext) in [(".codex", "openai", "toml"), (".claude", "anthropic", "md")] {
        let target = temp.path().join(host).join("agents");
        fs::create_dir_all(&target).unwrap();
        for agent in agents {
            let file = format!("{agent}.{ext}");
            fs::copy(
                root.join(source).join("agents").join(&file),
                target.join(file),
            )
            .unwrap();
        }
    }
    assert!(rblx_harness::gates::codex_agents(temp.path()).is_ok());
    assert!(rblx_harness::gates::claude_agents(temp.path()).is_ok());
    fs::remove_file(temp.path().join(".codex/agents/reviewer.toml")).unwrap();
    fs::remove_file(temp.path().join(".claude/agents/reviewer.md")).unwrap();
    assert!(rblx_harness::gates::codex_agents(temp.path()).is_err());
    assert!(rblx_harness::gates::claude_agents(temp.path()).is_err());
}

#[test]
fn data_tools_require_no_human_schema_review() {
    if !lute().is_file() {
        let temp = tempfile::tempdir().unwrap();
        let result = Command::new(env!("CARGO_BIN_EXE_harness"))
            .arg("--root")
            .arg(temp.path())
            .args(["data-write", "Score", "--default", "1", "--dev", "1"])
            .output()
            .unwrap();
        assert_eq!(result.status.code(), Some(3), "{}", text(&result));
        assert!(
            text(&result).contains("bundled lute absent"),
            "{}",
            text(&result)
        );
        assert!(!temp
            .path()
            .join("shared/src/ServerScriptService/Services/PlayerData/Default.luau")
            .exists());
        println!("UNRUN|data shape cases require tools/bin/lute");
        return;
    }
    let temp = tempfile::tempdir().unwrap();
    let before = temp.path().join("before.luau");
    let after = temp.path().join("after.luau");
    fs::write(&before, "return { score = 1, old = true }\n").unwrap();
    let check = |source: &str, path: &Path| {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, source).unwrap();
        Command::new(lute())
            .arg("run")
            .arg(root().join("tools/data_shape_diff/data_shape_diff.luau"))
            .arg(&before)
            .arg(path)
            .output()
            .unwrap()
    };
    let result = check("return { score = 2, old = true, extra = 3 }\n", &after);
    assert!(result.status.success(), "{}", text(&result));
    assert!(text(&result).starts_with("ALLOW"));
    let result = check("return { score = 'two' }\n", &after);
    assert!(result.status.success(), "{}", text(&result));
    assert!(text(&result).contains("retyped"), "{}", text(&result));
    assert!(text(&result).contains("dropped"), "{}", text(&result));
    let result = check("return { score = math.random() }\n", &after);
    assert!(!result.status.success(), "{}", text(&result));
    assert!(text(&result).contains("GATE1"), "{}", text(&result));
    let result = check(
        "return { score = 1 }\n",
        &temp.path().join("places/A/Default.luau"),
    );
    assert!(!result.status.success(), "{}", text(&result));
    assert!(text(&result).contains("DATA5"), "{}", text(&result));
}

fn scan(root: &Path, home: &Path, source: &str, file: &str, family: &str) -> Output {
    let path = root.join(file);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, source).unwrap();
    Command::new(env!("CARGO_BIN_EXE_harness"))
        .env("HOME", home)
        .arg("--root")
        .arg(root)
        .args(["check", "source", "--only", family])
        .arg(&path)
        .output()
        .unwrap()
}

#[test]
fn luau_contracts_const_profile_parallel_pairing_codecs_and_remote_ownership() {
    let temp = tempfile::tempdir().unwrap();
    let home = temp.path().join("home");
    fs::create_dir_all(home.join(".cache/harness")).unwrap();
    fs::write(home.join(".cache/harness/api_globals.luau"), "return {}\n").unwrap();
    if !lute().is_file() {
        let output = scan(
            temp.path(),
            &home,
            "return {}",
            "Example.luau",
            "correctness",
        );
        assert_eq!(output.status.code(), Some(3), "{}", text(&output));
        println!("UNRUN|Luau rule cases require tools/bin/lute");
        return;
    }
    for (source, status, rule) in [
        ("const T = {}\nT.x = 1", 0, ""),
        ("const X = 1\nX = 2", 2, "GATE4"),
        (
            "debug.profilebegin('a')\nif x then debug.profileend() return end\ndebug.profileend()",
            0,
            "",
        ),
        (
            "debug.profilebegin('a')\nif x then return end\ndebug.profileend()",
            2,
            "OPT20",
        ),
        (
            "task.desynchronize()\nif x then task.synchronize() return end\ntask.synchronize()",
            0,
            "",
        ),
        (
            "task.desynchronize()\nif x then return end\ntask.synchronize()",
            2,
            "OPT15",
        ),
        (
            "event:ConnectParallel(function() require('./m') end)",
            2,
            "OPT15",
        ),
        ("buffer.writeu8(b, 0, 256)", 0, "DATA38"),
        ("buffer.writebits(b, 0, 4, 16)", 0, "DATA38"),
    ] {
        let result = scan(temp.path(), &home, source, "Example.luau", "correctness");
        assert_eq!(
            result.status.code(),
            Some(status),
            "{source}: {}",
            text(&result)
        );
        assert!(
            rule.is_empty() || text(&result).contains(rule),
            "{source}: {}",
            text(&result)
        );
    }
    for source in [
        "buffer.writeu8(b, 0, 255)",
        "buffer.writebits(b, 0, 4, 15)",
        "local function f(buffer) buffer.writeu8(b, 0, 999) end",
    ] {
        let result = scan(temp.path(), &home, source, "Example.luau", "correctness");
        assert_eq!(result.status.code(), Some(0), "{}", text(&result));
        assert!(!text(&result).contains("DATA38"), "{}", text(&result));
    }
    let remote = "const Remote = Instance.new('UnreliableRemoteEvent')";
    let outside = scan(temp.path(), &home, remote, "Feature.luau", "replication");
    assert_eq!(outside.status.code(), Some(2), "{}", text(&outside));
    assert!(text(&outside).contains("WRIT8"), "{}", text(&outside));
    let owner = scan(
        temp.path(),
        &home,
        remote,
        "Packages/Event.luau",
        "replication",
    );
    assert_eq!(owner.status.code(), Some(0), "{}", text(&owner));
    assert!(!text(&owner).contains("WRIT8"), "{}", text(&owner));
}

#[test]
fn collisions_package_registry_ownership_and_lifecycle() {
    if !lute().is_file() {
        println!("UNRUN|collision lifecycle fixture requires tools/bin/lute");
        return;
    }
    let source =
        fs::read_to_string(root().join("packages/ServerScriptService/Modules/Collisions.luau"))
            .unwrap();
    let fixture = fs::read_to_string(root().join("tests/fixtures/collisions.luau")).unwrap();
    let temp = tempfile::tempdir().unwrap();
    let script = temp.path().join("collisions.luau");
    fs::write(&script, format!("const factory = function(game, typeof, Vector3, Enum, OverlapParams)\n{source}\nend\nconst run = (function()\n{fixture}\nend)()\nrun(factory)\n")).unwrap();
    let result = Command::new(lute())
        .arg("run")
        .arg(script)
        .output()
        .unwrap();
    assert!(result.status.success(), "{}", text(&result));
    assert!(text(&result).contains("C01 pass"), "{}", text(&result));
}
