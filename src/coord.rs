use anyhow::{anyhow, bail, Context, Result};
use clap::Parser;
use rusqlite::{params, Connection};
use serde_json::{json, Value};
use std::{
    ffi::OsString,
    fs,
    io::Read,
    path::{Component, Path, PathBuf},
    process::Command,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

#[derive(Parser)]
struct Args {
    #[arg(long, default_value = ".")]
    root: PathBuf,
    #[arg(value_parser = ["begin", "check", "end", "hook"])]
    action: String,
    #[arg(long)]
    owner: Option<String>,
    #[arg(long)]
    parent: Option<String>,
    #[arg(long = "path")]
    paths: Vec<String>,
    #[arg(long)]
    lease: Option<i64>,
    #[arg(long)]
    pid: Option<i64>,
    #[arg(long, default_value_t = 300)]
    ttl: i64,
    #[arg(long)]
    overlap: bool,
    #[arg(long, default_value = "HEAD")]
    base: String,
}

fn git(root: &Path, args: &[&str]) -> Result<String> {
    let out = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .env("GIT_OPTIONAL_LOCKS", "0")
        .output()?;
    if !out.status.success() {
        bail!("git failed")
    }
    Ok(String::from_utf8_lossy(&out.stdout)
        .trim_end_matches('\n')
        .to_owned())
}
fn expand(path: &Path) -> PathBuf {
    if let Ok(rest) = path.strip_prefix("~") {
        if let Some(home) = dirs::home_dir() {
            return home.join(rest);
        }
    }
    path.to_path_buf()
}
// Resolve existing ancestors as Path.resolve() does, including symlinks.
fn resolve(path: &Path) -> Result<PathBuf> {
    let path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    let mut ancestor = path.as_path();
    let mut suffix = Vec::new();
    while !ancestor.exists() {
        let name = ancestor
            .file_name()
            .ok_or_else(|| anyhow!("invalid path"))?;
        suffix.push(name.to_os_string());
        ancestor = ancestor.parent().ok_or_else(|| anyhow!("invalid path"))?;
    }
    let mut out = fs::canonicalize(ancestor)?;
    for name in suffix.iter().rev() {
        out.push(name);
    }
    Ok(out)
}
fn identity(s: &str) -> Result<()> {
    if s.is_empty()
        || s.len() > 160
        || !s
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_./:-".contains(&c))
    {
        bail!("invalid owner")
    }
    Ok(())
}
fn scopes(root: &Path, paths: &[String]) -> Result<Vec<String>> {
    let mut result = Vec::new();
    for name in paths {
        let p = Path::new(name);
        if name.is_empty()
            || name.chars().count() > 4096
            || p.is_absolute()
            || p.components().any(|c| c == Component::ParentDir)
        {
            bail!("scope must be repo-relative")
        }
        let absolute = resolve(&root.join(p))?;
        let rel = absolute.strip_prefix(root).context("outside root")?;
        let name = if rel.as_os_str().is_empty() {
            ".".to_owned()
        } else {
            rel.to_string_lossy().into_owned()
        };
        if name == ".git" || name.starts_with(".git/") {
            bail!("Git metadata cannot be leased")
        }
        result.push(name);
    }
    result.sort();
    result.dedup();
    if result.is_empty() || result.len() > 100 {
        bail!("provide 1..100 scopes")
    }
    Ok(result)
}
fn overlaps(a: &[String], b: &[String]) -> bool {
    a.iter().any(|a| {
        b.iter().any(|b| {
            a == "."
                || b == "."
                || a == b
                || a.strip_prefix(b).is_some_and(|x| x.starts_with('/'))
                || b.strip_prefix(a).is_some_and(|x| x.starts_with('/'))
        })
    })
}
fn alive(pid: i64) -> bool {
    if !(1..(1i64 << 31)).contains(&pid) {
        return true;
    }
    unsafe {
        libc::kill(pid as libc::pid_t, 0) == 0
            || std::io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
    }
}
fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
#[derive(Debug)]
struct Lease {
    id: i64,
    owner: String,
    parent: Option<String>,
    worktree: String,
    paths: Vec<String>,
    pid: Option<i64>,
    expires: f64,
}
fn open(root: &Path, create: bool) -> Result<Option<Connection>> {
    let top = resolve(Path::new(&git(root, &["rev-parse", "--show-toplevel"])?))?;
    if top != root {
        bail!("coord requires worktree root")
    }
    let common = git(
        root,
        &["rev-parse", "--path-format=absolute", "--git-common-dir"],
    )?;
    let path = PathBuf::from(common).join("harness/coord.sqlite3");
    if !path.exists() && !create {
        return Ok(None);
    }
    if fs::symlink_metadata(&path).is_ok_and(|m| m.file_type().is_symlink())
        || fs::symlink_metadata(path.parent().unwrap()).is_ok_and(|m| m.file_type().is_symlink())
    {
        bail!("state symlink")
    }
    if !path.parent().unwrap().exists() {
        fs::create_dir_all(path.parent().unwrap())?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(path.parent().unwrap(), fs::Permissions::from_mode(0o700))?;
        }
    }
    let db = Connection::open(&path)?;
    db.busy_timeout(Duration::from_secs(1))?;
    if create {
        db.execute_batch("CREATE TABLE IF NOT EXISTS leases (lease INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT UNIQUE NOT NULL, parent TEXT, worktree TEXT NOT NULL, paths TEXT NOT NULL, pid INTEGER, expires REAL NOT NULL)")?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
        }
    }
    Ok(Some(db))
}
fn load(db: &Connection) -> Result<Vec<Lease>> {
    let mut stmt = db.prepare("SELECT * FROM leases LIMIT 1001")?;
    let mut columns = stmt.column_names();
    columns.sort_unstable();
    if columns
        != [
            "expires", "lease", "owner", "parent", "paths", "pid", "worktree",
        ]
    {
        bail!("invalid schema")
    }
    let mut rows = stmt.query([])?;
    let mut out = Vec::new();
    let mut dead = Vec::new();
    while let Some(r) = rows.next()? {
        let id: i64 = r.get("lease")?;
        let owner: String = r.get("owner")?;
        let parent: Option<String> = r.get("parent")?;
        let worktree: String = r.get("worktree")?;
        let raw: String = r.get("paths")?;
        let pid: Option<i64> = r.get("pid")?;
        let expires: f64 = r.get("expires")?;
        let paths: Vec<String> = serde_json::from_str(&raw)?;
        if id < 1
            || !Path::new(&worktree).is_absolute()
            || !expires.is_finite()
            || paths.is_empty()
            || paths.len() > 100
            || paths.iter().any(|p| {
                p.is_empty()
                    || p.chars().count() > 4096
                    || Path::new(p).is_absolute()
                    || Path::new(p).components().any(|c| c == Component::ParentDir)
            })
        {
            bail!("invalid stored lease")
        }
        identity(&owner)?;
        if let Some(p) = &parent {
            identity(p)?
        }
        if let Some(p) = pid {
            if !(1..(1i64 << 31)).contains(&p) {
                bail!("invalid pid")
            }
            if !alive(p) {
                dead.push(id);
                continue;
            }
        }
        out.push(Lease {
            id,
            owner,
            parent,
            worktree,
            paths,
            pid,
            expires,
        });
        if out.len() + dead.len() > 1000 {
            bail!("owner limit")
        }
    }
    drop(rows);
    drop(stmt);
    for id in dead {
        db.execute("DELETE FROM leases WHERE lease=?", [id])?;
    }
    Ok(out)
}
fn operate(args: &Args, root: &Path) -> Result<Value> {
    if args.overlap && args.action != "check" {
        bail!("invalid overlap")
    }
    if args.lease.is_some_and(|x| x < 1) {
        bail!("invalid lease")
    }
    let owner = args
        .owner
        .clone()
        .or_else(|| {
            std::env::var("CODEX_THREAD_ID")
                .ok()
                .filter(|x| !x.is_empty())
        })
        .or_else(|| {
            std::env::var("CLAUDE_CODE_SESSION_ID")
                .ok()
                .filter(|x| !x.is_empty())
        });
    let selected = if args.action == "begin" || (args.action == "check" && !args.paths.is_empty()) {
        Some(scopes(root, &args.paths)?)
    } else {
        None
    };
    if args.action == "begin" || args.action == "end" || args.lease.is_some() {
        identity(owner.as_deref().unwrap_or(""))?;
    }
    if let Some(p) = &args.parent {
        if args.action == "begin" {
            identity(p)?;
        }
    }
    if args.action == "begin"
        && (owner == args.parent
            || !(30..=3600).contains(&args.ttl)
            || args
                .pid
                .is_some_and(|p| !(1..(1i64 << 31)).contains(&p) || !alive(p)))
    {
        bail!("invalid parent, expiry or process")
    }
    if args.action == "end" && args.lease.is_none() {
        bail!("end requires lease")
    }
    let Some(mut db) = open(root, args.action == "begin")? else {
        return Ok(if args.lease.is_some() && args.action == "check" {
            json!({"state":"stale"})
        } else if args.action == "end" {
            json!({"state":"ended"})
        } else {
            json!({"state":"clear","owners":[],"omitted":0})
        });
    };
    let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
    let rows = load(&tx)?;
    let root = root.to_string_lossy();
    let now = now();
    let result = match args.action.as_str() {
        "begin" => {
            let owner = owner.as_deref().unwrap();
            let paths = selected.as_ref().unwrap();
            let existing = rows.iter().find(|r| r.owner == owner);
            if existing.is_some_and(|r| r.worktree != root || r.parent != args.parent) {
                json!({"state":"stale"})
            } else {
                let busy: Vec<_> = rows
                    .iter()
                    .filter(|r| r.owner != owner && r.worktree == root && overlaps(paths, &r.paths))
                    .collect();
                if !busy.is_empty() {
                    json!({"state": if busy.iter().any(|r| r.expires <= now) {"unknown"} else {"busy"},"owners":busy.iter().take(10).map(|r| &r.owner).collect::<Vec<_>>(),"omitted":busy.len().saturating_sub(10)})
                } else if let Some(r) = existing.filter(|r| r.paths == *paths && r.pid == args.pid)
                {
                    tx.execute(
                        "UPDATE leases SET expires=? WHERE lease=?",
                        params![now + args.ttl as f64, r.id],
                    )?;
                    json!({"state":"owned","lease":r.id})
                } else {
                    if let Some(r) = existing {
                        tx.execute("DELETE FROM leases WHERE lease=?", [r.id])?;
                    } else if rows.len() >= 1000 {
                        bail!("owner limit")
                    }
                    tx.execute("INSERT INTO leases (owner,parent,worktree,paths,pid,expires) VALUES (?,?,?,?,?,?)", params![owner,args.parent,root.as_ref(),serde_json::to_string(paths)?,args.pid,now + args.ttl as f64])?;
                    json!({"state":"owned","lease":tx.last_insert_rowid()})
                }
            }
        }
        "end" => {
            tx.execute(
                "DELETE FROM leases WHERE owner=? AND lease=? AND worktree=?",
                params![owner, args.lease, root.as_ref()],
            )?;
            json!({"state":"ended"})
        }
        _ => {
            if let Some(id) = args.lease {
                match rows
                    .iter()
                    .find(|r| Some(&r.owner) == owner.as_ref() && r.id == id && r.worktree == root)
                {
                    None => json!({"state":"stale"}),
                    Some(r)
                        if selected.as_ref().is_some_and(|s| {
                            s.iter().any(|p| {
                                !r.paths.iter().any(|scope| {
                                    scope == "."
                                        || p == scope
                                        || p.strip_prefix(scope).is_some_and(|x| x.starts_with('/'))
                                })
                            })
                        }) =>
                    {
                        json!({"state":"outsideScope"})
                    }
                    Some(_) => {
                        tx.execute(
                            "UPDATE leases SET expires=? WHERE lease=?",
                            params![now + 300.0, id],
                        )?;
                        json!({"state":"owned","lease":id})
                    }
                }
            } else {
                let busy: Vec<_> = rows
                    .iter()
                    .filter(|r| {
                        r.worktree == root
                            && selected.as_ref().is_none_or(|p| overlaps(p, &r.paths))
                    })
                    .collect();
                json!({"state":if busy.iter().any(|r| r.expires <= now) {"unknown"} else if busy.is_empty() {"clear"} else {"busy"},"owners":busy.iter().take(10).map(|r| &r.owner).collect::<Vec<_>>(),"omitted":busy.len().saturating_sub(10)})
            }
        }
    };
    tx.commit()?;
    Ok(result)
}
fn hook() -> Result<()> {
    let mut input = Vec::new();
    std::io::stdin()
        .take(1024 * 1024 + 1)
        .read_to_end(&mut input)?;
    if input.len() > 1024 * 1024 {
        bail!("input limit")
    }
    let event: Value = serde_json::from_slice(&input)?;
    let obj = event.as_object().context("invalid event")?;
    let owner = match obj.get("hook_event_name").and_then(Value::as_str) {
        Some("SubagentStop") => obj.get("agent_id"),
        Some("SessionEnd") => obj.get("session_id"),
        _ => return Ok(()),
    }
    .and_then(Value::as_str)
    .context("missing owner")?;
    identity(owner)?;
    let cwd = resolve(Path::new(
        obj.get("cwd")
            .and_then(Value::as_str)
            .context("missing cwd")?,
    ))?;
    let root = resolve(Path::new(&git(&cwd, &["rev-parse", "--show-toplevel"])?))?;
    if let Some(mut db) = open(&root, false)? {
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        load(&tx)?;
        tx.execute("WITH RECURSIVE ended(owner) AS (SELECT ? UNION SELECT leases.owner FROM leases JOIN ended ON leases.parent = ended.owner) DELETE FROM leases WHERE owner IN ended",[owner])?;
        tx.commit()?;
    }
    Ok(())
}
pub fn run(args: &[OsString]) -> Result<i32> {
    let args =
        Args::try_parse_from(std::iter::once(OsString::from("coord")).chain(args.iter().cloned()))?;
    if args.action == "hook" {
        if hook().is_ok() {
            println!("{{}}");
        } else {
            println!("{{\"systemMessage\": \"coord cleanup unavailable\"}}");
        }
        return Ok(0);
    }
    let result = (|| -> Result<Value> {
        let root = resolve(&expand(&args.root))?;
        let mut result = operate(&args, &root)?;
        if args.overlap {
            let paths = if args.paths.is_empty() {
                vec![".".to_owned()]
            } else {
                args.paths.clone()
            };
            result["overlap"] = crate::offline::overlap_report(&root, &paths, &args.base);
        }
        Ok(result)
    })();
    match result {
        Ok(result) => {
            println!("{}", serde_json::to_string(&result)?);
            let ok = matches!(result["state"].as_str(), Some("owned" | "clear" | "ended"))
                && !matches!(
                    result["overlap"]["state"].as_str(),
                    Some("unknown" | "conflict")
                );
            Ok(if ok { 0 } else { 2 })
        }
        Err(_) => {
            println!(
                "{{\"state\": \"unknown\", \"error\": \"coord unavailable or invalid request\"}}"
            );
            Ok(2)
        }
    }
}
