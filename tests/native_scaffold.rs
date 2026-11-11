use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tempfile::TempDir;

const URL: &str = "https://github.com/lennyRBLX/rblx-harness.git";

fn write(root: &Path, path: &str, bytes: &[u8]) {
    let path = root.join(path);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, bytes).unwrap();
}

fn ok(output: Output) -> Output {
    assert!(
        output.status.success(),
        "stdout: {}\nstderr: {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    output
}

fn command(root: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_harness"))
        .arg("--root")
        .arg(root)
        .args(args)
        .env("RBLX_HARNESS_TESTING", "1")
        .output()
        .unwrap()
}

fn git(root: &Path, args: &[&str]) -> Output {
    ok(Command::new("git")
        .current_dir(root)
        .args(args)
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .output()
        .unwrap())
}

fn copy_tree(source: &Path, destination: &Path) {
    fs::create_dir_all(destination).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&entry.path(), &destination.join(entry.file_name()));
        } else if entry.file_type().unwrap().is_file() {
            fs::copy(entry.path(), destination.join(entry.file_name())).unwrap();
        }
    }
}

struct Fixture {
    _temp: TempDir,
    root: PathBuf,
    bare: PathBuf,
    home: PathBuf,
}
impl Fixture {
    fn new() -> Self {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("game");
        let source = temp.path().join("source");
        let bare = temp.path().join("source.git");
        let home = temp.path().join("home");
        fs::create_dir_all(&root).unwrap();
        fs::create_dir_all(&source).unwrap();
        fs::create_dir_all(&home).unwrap();
        write(
            &source,
            "Cargo.toml",
            b"[package]\nname = 'fixture'\nversion = '0.1.0'\n",
        );
        write(&source, "shared/CORE.md", b"fixture\n");
        write(
            &source,
            "shared/skills/rblx-new-game/SKILL.md",
            b"fixture\n",
        );
        copy_tree(
            &Path::new(env!("CARGO_MANIFEST_DIR")).join("packages"),
            &source.join("packages"),
        );
        git(&source, &["init", "-q"]);
        git(&source, &["config", "user.name", "fixture"]);
        git(
            &source,
            &["config", "user.email", "fixture@example.invalid"],
        );
        git(&source, &["add", "."]);
        git(&source, &["commit", "-qm", "fixture"]);
        ok(Command::new("git")
            .args(["clone", "--bare", "-q"])
            .arg(&source)
            .arg(&bare)
            .output()
            .unwrap());
        Self {
            _temp: temp,
            root,
            bare,
            home,
        }
    }
    fn dependency(&self, args: &[&str]) -> Output {
        let key = format!("url.file://{}.insteadOf", self.bare.display());
        Command::new(env!("CARGO_BIN_EXE_harness"))
            .arg("--root")
            .arg(&self.root)
            .args(["scaffold", "dependency"])
            .args(args)
            .env("HOME", &self.home)
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_CONFIG_COUNT", "1")
            .env("GIT_CONFIG_KEY_0", key)
            .env("GIT_CONFIG_VALUE_0", URL)
            .env("GIT_ALLOW_PROTOCOL", "file")
            .env("RBLX_HARNESS_TESTING", "1")
            .output()
            .unwrap()
    }
    fn install(&self) {
        ok(self.dependency(&["setup", "--yes"]));
    }
}

fn answer(root: &Path, field: &str, value: &str) {
    ok(command(
        root,
        &["scaffold", "project", "answer", field, value],
    ));
}
fn answers(root: &Path, assets: &str, harness: &str) {
    for (field, value) in [
        ("gameplay", "Players win matches for loot"),
        ("places", "Lobby, Match"),
        ("services", "shared: Combat; Match: Round"),
        ("controllers", "shared: Camera; Match: Movement"),
        ("assets", assets),
        ("harness", harness),
    ] {
        answer(root, field, value);
    }
}
fn json_file(root: &Path, path: &str) -> Value {
    serde_json::from_slice(&fs::read(root.join(path)).unwrap()).unwrap()
}
fn text(output: &[u8]) -> String {
    String::from_utf8_lossy(output).into_owned()
}

#[test]
fn new_game_approval_installs_the_fixed_github_submodule_into_an_unborn_repository() {
    let f = Fixture::new();
    let pending = f.dependency(&["setup"]);
    assert_eq!(pending.status.code(), Some(3));
    assert!(text(&pending.stdout).contains("CONSENT_REQUIRED"));
    assert!(!f.root.join(".git").exists());
    assert!(!f.root.join("rblx-harness").exists());
    f.install();
    assert!(f.root.join(".roblox").is_file());
    assert!(f.root.join("rblx-harness/Cargo.toml").is_file());
    let url = git(
        &f.root,
        &[
            "config",
            "-f",
            ".gitmodules",
            "--get",
            "submodule.rblx-harness.url",
        ],
    );
    assert_eq!(text(&url.stdout).trim(), URL);
    let staged = git(&f.root, &["ls-files", "--stage", "--", "rblx-harness"]);
    assert!(text(&staged.stdout).starts_with("160000 "));
    assert!(!Command::new("git")
        .current_dir(&f.root)
        .args(["rev-parse", "--verify", "HEAD"])
        .output()
        .unwrap()
        .status
        .success());
    assert!(text(&ok(f.dependency(&["setup", "--yes"])).stdout).contains("mode=submodule-ready"));
    assert!(text(&ok(f.dependency(&["status"])).stdout).contains("READY|submodule"));
    git(
        &f.root,
        &["submodule", "deinit", "--force", "--", "rblx-harness"],
    );
    assert!(text(&ok(f.dependency(&["init"])).stdout).contains("READY|submodule"));
}

#[test]
fn inspection_identifies_existing_scoped_modules_without_writing() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path();
    write(
        root,
        "legacy/ServerScriptService/Services/Combat.luau",
        b"return { existing = true }\n",
    );
    write(
        root,
        "places/Match/src/StarterPlayer/StarterPlayerScripts/Controllers/Movement.luau",
        b"return {}\n",
    );
    write(root, "Match.project.json", b"{}\n");
    write(root, "plugins/Services/Hidden.luau", b"return {}\n");
    let result = ok(command(root, &["scaffold", "project", "inspect"]));
    let report: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(report["project"], "existing");
    assert_eq!(report["places"], json!(["Match"]));
    assert!(report["services"]
        .as_array()
        .unwrap()
        .iter()
        .any(|v| v["name"] == "Combat" && v["scope"] == "shared"));
    assert!(report["controllers"]
        .as_array()
        .unwrap()
        .iter()
        .any(|v| v["name"] == "Movement" && v["scope"] == "Match"));
    assert_eq!(report["services"].as_array().unwrap().len(), 1);
    assert!(!root.join("manifest.json").exists());
    assert!(!root.join(".gitignore").exists());
    assert_eq!(fs::read(root.join("Match.project.json")).unwrap(), b"{}\n");
}

#[test]
fn scaffold_requires_bare_service_and_controller_names() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path();
    answer(root, "places", "Lobby");
    let before = fs::read(root.join("manifest.json")).unwrap();
    for (field, value, message) in [
        (
            "services",
            "shared: InventoryService",
            "use Inventory instead of InventoryService",
        ),
        (
            "controllers",
            "shared: CameraController",
            "use Camera instead of CameraController",
        ),
    ] {
        let result = command(root, &["scaffold", "project", "answer", field, value]);
        assert_eq!(result.status.code(), Some(2));
        assert!(text(&result.stderr).contains(message));
        assert_eq!(fs::read(root.join("manifest.json")).unwrap(), before);
    }
    answer(root, "services", "shared: Inventory");
    answer(root, "controllers", "Lobby: Camera");
}

#[test]
fn integration_failure_retains_state_and_reports_setup_only_recovery() {
    let f = Fixture::new();
    answers(&f.root, "none", "yes");
    f.install();
    write(&f.root, ".codex", b"blocked\n");
    let result = command(&f.root, &["scaffold", "project", "emit"]);
    assert_eq!(result.status.code(), Some(2));
    let error = text(&result.stderr);
    assert!(error.contains("project integration failed"), "{error}");
    assert!(
        error.contains("do not rerun scaffold")
            && error.contains("harness setup")
            && error.contains("--from-state"),
        "{error}"
    );
    assert!(f.root.join("Lobby.project.json").is_file());
    let manifest = json_file(&f.root, "manifest.json");
    assert_eq!(manifest["places"], json!(["Lobby", "Match"]));
    fs::remove_file(f.root.join(".codex")).unwrap();
    ok(command(
        &f.root,
        &[
            "setup",
            "--project",
            f.root.to_str().unwrap(),
            "--from-state",
        ],
    ));
    assert!(f.root.join(".codex/config.toml").is_file());
    assert!(f.root.join(".claude/settings.json").is_file());
    assert_eq!(json_file(&f.root, "manifest.json"), manifest);
}

#[test]
fn full_scaffold_links_assets_and_preserves_existing_module_bytes() {
    let f = Fixture::new();
    let service = b"return { ExistingCombat = true }\n";
    let controller = b"return { ExistingMovement = true }\n";
    write(
        &f.root,
        "legacy/ServerScriptService/Services/Combat.luau",
        service,
    );
    write(
        &f.root,
        "places/Match/src/StarterPlayer/StarterPlayerScripts/Controllers/Movement.luau",
        controller,
    );
    answers(&f.root, "all", "yes");
    f.install();
    let result = ok(command(&f.root, &["scaffold", "project", "emit"]));
    assert!(text(&result.stdout).contains("EMITTED|game"));
    let readme = fs::read_to_string(f.root.join("README.md")).unwrap();
    assert!(
        readme.contains("harness setup --project . --from-state"),
        "{readme}"
    );
    assert!(!readme.contains("setup_project.py"), "{readme}");
    assert_eq!(
        fs::read(
            f.root
                .join("shared/src/ServerScriptService/Services/Combat.luau")
        )
        .unwrap(),
        service
    );
    assert_eq!(
        fs::read(
            f.root.join(
                "places/Match/src/StarterPlayer/StarterPlayerScripts/Controllers/Movement.luau"
            )
        )
        .unwrap(),
        controller
    );
    for path in [
        "shared/src/ReplicatedStorage/Packages/Signal.luau",
        "shared/src/ServerScriptService/Services/Payments.luau",
        "shared/src/ReplicatedStorage/Types/PlayerData.luau",
        "shared/src/StarterPlayer/StarterPlayerScripts/Controllers/Effects/init.luau",
    ] {
        let p = f.root.join(path);
        assert!(
            fs::symlink_metadata(&p).unwrap().file_type().is_symlink(),
            "{path}"
        );
        assert!(p.is_file(), "broken {path}");
    }
    assert!(f.root.join("plugins").is_dir());
    assert!(f.root.join(".claude/settings.json").is_file());
    let map = json_file(&f.root, "Match.project.json");
    assert_eq!(
        map["tree"]["ServerScriptService"]["PlaceServices"]["$path"],
        "places/Match/src/ServerScriptService/Services"
    );
}

#[test]
fn plugins_directory_is_optional() {
    let f = Fixture::new();
    answers(&f.root, "none", "yes");
    f.install();
    ok(command(&f.root, &["scaffold", "project", "emit"]));
    assert!(!f.root.join("plugins").exists());
    assert_eq!(json_file(&f.root, "manifest.json")["assets"], json!([]));
}

#[test]
fn legacy_plugin_support_migrates_when_the_harness_is_declined() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path();
    write(root, "plugin/Example.luau", b"return 'custom'\n");
    write(root, "AGENTS.md", b"custom instructions\n");
    answers(root, "none", "no");
    ok(command(root, &["scaffold", "project", "emit"]));
    assert!(!root.join("plugin").exists());
    assert_eq!(
        fs::read(root.join("plugins/Example.luau")).unwrap(),
        b"return 'custom'\n"
    );
    assert_eq!(
        json_file(root, "manifest.json")["assets"],
        json!(["plugins"])
    );
    assert_eq!(
        fs::read(root.join("AGENTS.md")).unwrap(),
        b"custom instructions\n"
    );
    assert!(!root.join("README.md").exists());
    assert!(!root.join("rblx-harness").exists());
}

#[test]
fn playerdata_scaffold_departure_cleanup_and_optional_packages() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path();
    answers(root, "none", "no");
    ok(command(root, &["scaffold", "project", "emit"]));
    assert!(!root.join("shared/src/ReplicatedStorage/Packages").exists());
    let server = root.join("shared/src/ServerScriptService/Server.server.luau");
    let generated = fs::read_to_string(&server).unwrap();
    // The generated entry must guard both absent package levels before connecting
    // departure cleanup, and connect before starting any services.
    let packages = generated
        .find("ReplicatedStorage:FindFirstChild(\"Packages\")")
        .unwrap();
    let optional_cleanup = generated
        .find("packages and packages:FindFirstChild(\"EntityCleanup\")")
        .unwrap();
    let guard = generated.find("if cleanupModule then").unwrap();
    let connection = generated
        .find("Players.PlayerRemoving:Connect(function(player)")
        .unwrap();
    let cleanup = generated.find("EntityCleanup:Cleanup(player)").unwrap();
    let start = generated.find("service:Start()").unwrap();
    assert!(
        packages < optional_cleanup
            && optional_cleanup < guard
            && guard < connection
            && connection < cleanup
            && cleanup < start
    );
    assert!(generated[cleanup..start].contains("end)"));
    ok(command(root, &["scaffold", "project", "emit"]));
    assert_eq!(fs::read_to_string(server).unwrap(), generated);
}
