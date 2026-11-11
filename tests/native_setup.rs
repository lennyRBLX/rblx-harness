use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tempfile::TempDir;

const BIN: &str = env!("CARGO_BIN_EXE_harness");
const SOURCE: &str = env!("CARGO_MANIFEST_DIR");

fn put(root: &Path, name: &str, data: &str) {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, data).unwrap();
}
fn read(root: &Path, name: &str) -> String {
    fs::read_to_string(root.join(name)).unwrap()
}
fn json_file(root: &Path, name: &str) -> Value {
    serde_json::from_str(&read(root, name)).unwrap()
}
fn command(root: &Path, args: &[&str], envs: &[(&str, &Path)]) -> Output {
    let mut cmd = Command::new(BIN);
    cmd.arg("--root")
        .arg(root)
        .args(args)
        .env("RBLX_HARNESS_TESTING", "1");
    for (key, value) in envs {
        cmd.env(key, value);
    }
    let out = cmd.output().unwrap();
    assert!(
        out.status.success(),
        "stdout: {}\nstderr: {}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    out
}
fn project() -> TempDir {
    let dir = tempfile::tempdir().unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink(SOURCE, dir.path().join("rblx-harness")).unwrap();
    #[cfg(windows)]
    std::os::windows::fs::symlink_dir(SOURCE, dir.path().join("rblx-harness")).unwrap();
    put(
        dir.path(),
        "manifest.json",
        r#"{"places":["Lobby"],"assets":[]}"#,
    );
    dir
}
fn setup(root: &Path) {
    command(
        root,
        &["setup", "--project", root.to_str().unwrap(), "--from-state"],
        &[],
    );
}
fn copy_tree(from: &Path, to: &Path) {
    fs::create_dir_all(to).unwrap();
    for entry in fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let dest = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&entry.path(), &dest);
        } else if entry.file_type().unwrap().is_file() {
            fs::copy(entry.path(), dest).unwrap();
        }
    }
}
fn stdout(out: Output) -> String {
    String::from_utf8(out.stdout).unwrap()
}
fn agent_names(root: &Path, host: &str, ext: &str) {
    for name in [
        "debugger",
        "implementer",
        "optimizer",
        "researcher",
        "reviewer",
    ] {
        assert!(root.join(format!(".{host}/agents/{name}.{ext}")).is_file());
    }
}
fn assert_cleanup_hooks(doc: &Value) {
    for event in ["SubagentStop", "SessionEnd"] {
        let entries = doc["hooks"][event].as_array().unwrap();
        assert!(
            entries.iter().any(|entry| {
                let command = entry["hooks"][0]["command"].as_str().unwrap_or("");
                command.contains("hook")
                    && command.contains("coord")
                    && entry["hooks"][0]["timeout"] == 5
            }),
            "missing cleanup hook for {event}: {entries:?}"
        );
    }
}

#[test]
fn harness_setup_rebuilds_ignored_codex_and_claude_code_support_and_all_source_skills() {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path();
    for name in ["shared", "openai", "anthropic"] {
        copy_tree(&PathBuf::from(SOURCE).join(name), &root.join(name));
    }
    fs::copy(BIN, root.join("harness")).unwrap();
    let run = || {
        let out = Command::new(root.join("harness"))
            .current_dir(root)
            .args(["setup", "--harness"])
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
    };
    run();
    assert!(root.join(".codex/config.toml").is_file());
    agent_names(root, "codex", "toml");
    agent_names(root, "claude", "md");
    assert_cleanup_hooks(&json_file(root, ".codex/hooks.json"));
    let settings = json_file(root, ".claude/settings.json");
    assert_cleanup_hooks(&settings);
    assert_eq!(settings["env"]["MAX_MCP_OUTPUT_TOKENS"], "6000");
    for skill in [
        "rblx-debug",
        "rblx-gui",
        "rblx-new-game",
        "rblx-optimize",
        "rblx-plan",
        "rblx-test",
        "rblx-writer",
    ] {
        for host in [".agents", ".claude"] {
            let path = root.join(host).join("skills").join(skill);
            assert!(fs::symlink_metadata(&path)
                .unwrap()
                .file_type()
                .is_symlink());
            assert!(path.join("SKILL.md").is_file());
        }
    }
    assert!(!root.join(".roblox").exists());
    let before = read(root, ".claude/settings.json");
    run();
    assert_eq!(before, read(root, ".claude/settings.json"));
}

#[test]
fn codex_config_merge_preserves_custom_tables() {
    let dir = project();
    let root = dir.path();
    put(root, ".codex/config.toml", "[custom]\nvalue = 7\n");
    setup(root);
    let first = read(root, ".codex/config.toml");
    let config: toml::Value = toml::from_str(&first).unwrap();
    assert_eq!(config["custom"]["value"].as_integer(), Some(7));
    assert_eq!(config["tool_output_token_limit"].as_integer(), Some(6000));
    setup(root);
    assert_eq!(first, read(root, ".codex/config.toml"));
}

#[test]
fn claude_settings_merge_preserves_custom_values() {
    let dir = project();
    let root = dir.path();
    put(root, ".claude/settings.json", &json!({"custom":{"value":7},"env":{"MAX_MCP_OUTPUT_TOKENS":"9000"},"permissions":{"allow":["Bash(custom)"]}}).to_string());
    setup(root);
    let first = read(root, ".claude/settings.json");
    let doc: Value = serde_json::from_str(&first).unwrap();
    assert_eq!(doc["custom"]["value"], 7);
    assert_eq!(doc["env"]["MAX_MCP_OUTPUT_TOKENS"], "9000");
    assert_eq!(doc["env"]["BASH_MAX_OUTPUT_LENGTH"], "24000");
    let allow = doc["permissions"]["allow"].as_array().unwrap();
    assert!(allow.contains(&json!("Bash(custom)")) && allow.contains(&json!("Agent(researcher)")));
    setup(root);
    assert_eq!(first, read(root, ".claude/settings.json"));
}

#[test]
fn claude_roblox_settings_profile_allows_the_harness_cache_and_remains_optional() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    let home = root.join("claude");
    let env = [("CLAUDE_CONFIG_DIR", home.as_path())];
    assert!(stdout(command(root, &["setup", "permissions"], &env)).contains("ABSENT"));
    assert!(!home.exists());
    assert!(
        stdout(command(root, &["setup", "permissions", "--install"], &env)).contains("INSTALLED")
    );
    let name = "claude/rblx-harness-roblox.json";
    let first = read(root, name);
    let doc: Value = serde_json::from_str(&first).unwrap();
    assert!(doc["sandbox"]["filesystem"]["allowWrite"]
        .as_array()
        .unwrap()
        .contains(&json!("~/.cache/harness")));
    assert!(doc["sandbox"]["network"]["allowedDomains"]
        .as_array()
        .unwrap()
        .contains(&json!("github.com")));
    assert!(!home.join("settings.json").exists());
    assert!(
        stdout(command(root, &["setup", "permissions", "--install"], &env)).contains("PRESENT")
    );
    assert_eq!(first, read(root, name));
}

#[test]
fn native_codex_migration_and_consolidated_commands() {
    let dir = project();
    let root = dir.path();
    let legacy = "PYTHONDONTWRITEBYTECODE=1 python3 \"$(git rev-parse --show-toplevel)/openai/hooks/adapter.py\" --host codex --event PreToolUse --hook-scope project";
    let custom = json!({"matcher":"Bash", "hooks":[{"type":"command","command":"custom-check"}]});
    put(root, ".codex/hooks.json", &json!({"custom":42,"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":legacy}]},custom]}}).to_string());
    setup(root);
    let hooks = json_file(root, ".codex/hooks.json");
    assert_eq!(hooks["custom"], 42);
    assert_eq!(hooks["hooks"]["PreToolUse"], json!([custom]));
    assert_cleanup_hooks(&hooks);
    agent_names(root, "codex", "toml");
    let first = read(root, ".codex/hooks.json");
    setup(root);
    assert_eq!(first, read(root, ".codex/hooks.json"));
    let home = root.join("codex-home");
    let env = [("CODEX_HOME", home.as_path())];
    assert!(stdout(command(root, &["setup", "codex-permissions"], &env)).contains("ABSENT"));
    command(root, &["setup", "codex-permissions", "--install"], &env);
    let config = read(root, "codex-home/config.toml");
    let parsed: toml::Value = toml::from_str(&config).unwrap();
    assert_eq!(
        parsed["permissions"]["Roblox"]["filesystem"]["~/.cache/harness"].as_str(),
        Some("write")
    );
    command(root, &["setup", "codex-permissions", "--install"], &env);
    assert_eq!(config, read(root, "codex-home/config.toml"));
}

#[test]
fn native_claude_code_settings_agents_hook_migration_and_permission_profile() {
    let dir = project();
    let root = dir.path();
    let retired = json!({"type":"command","command":"python3","args":["-B","${CLAUDE_PROJECT_DIR}/.roblox-harness/claude/hooks/adapter.py","--host","claude","--event","PreToolUse","--hook-scope","project"]});
    let custom = json!({"type":"command","command":"custom-check"});
    put(root, ".claude/settings.json", &json!({"custom":true,"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[retired,custom]}]}}).to_string());
    setup(root);
    let doc = json_file(root, ".claude/settings.json");
    assert_eq!(doc["custom"], true);
    assert_eq!(doc["hooks"]["PreToolUse"][0]["hooks"], json!([custom]));
    assert_cleanup_hooks(&doc);
    agent_names(root, "claude", "md");
    assert!(!root.join(".claude/skills/rblx-new-game").exists());
    let first = read(root, ".claude/settings.json");
    setup(root);
    assert_eq!(first, read(root, ".claude/settings.json"));
    let home = root.join("profile-home");
    let env = [("CLAUDE_CONFIG_DIR", home.as_path())];
    put(root, "profile-home/rblx-harness-roblox.json", &json!({"sandbox":{"filesystem":{"allowWrite":["/custom"]},"network":{"allowedDomains":["example.com"]}},"custom":7}).to_string());
    command(root, &["setup", "claude-permissions", "--install"], &env);
    let profile = json_file(root, "profile-home/rblx-harness-roblox.json");
    assert_eq!(profile["custom"], 7);
    let writes = profile["sandbox"]["filesystem"]["allowWrite"]
        .as_array()
        .unwrap();
    assert!(writes.contains(&json!("/custom")) && writes.contains(&json!("~/.cache/harness")));
    let domains = profile["sandbox"]["network"]["allowedDomains"]
        .as_array()
        .unwrap();
    assert!(domains.contains(&json!("example.com")) && domains.contains(&json!("github.com")));
    let first = read(root, "profile-home/rblx-harness-roblox.json");
    command(root, &["setup", "claude-permissions", "--install"], &env);
    assert_eq!(first, read(root, "profile-home/rblx-harness-roblox.json"));
}
