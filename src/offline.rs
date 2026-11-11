use anyhow::{anyhow, bail, Context, Result};
use clap::{Parser, Subcommand};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    ffi::{OsStr, OsString},
    fs,
    io::Write,
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

const LIMIT: u64 = 8 * 1024 * 1024;
#[derive(Parser)]
struct Args {
    #[arg(long, default_value = ".")]
    root: PathBuf,
    #[arg(long, default_value_t = 12000)]
    max_chars: usize,
    #[arg(long)]
    since: Option<PathBuf>,
    #[arg(long)]
    no_cache: bool,
    #[command(subcommand)]
    mode: Mode,
}
#[derive(Subcommand)]
enum Mode {
    Read {
        #[arg(long = "file", required = true)]
        files: Vec<String>,
    },
    Diff {
        #[arg(long = "path", required = true)]
        paths: Vec<String>,
        #[arg(long, default_value = "HEAD")]
        base: String,
        #[arg(long)]
        overlap: bool,
    },
}
fn sha(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}
fn expand(path: &Path) -> PathBuf {
    if let Ok(rest) = path.strip_prefix("~") {
        if let Some(home) = dirs::home_dir() {
            return home.join(rest);
        }
    }
    path.to_path_buf()
}
fn resolve(path: &Path) -> Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    // Canonicalize one component at a time, retaining missing components.
    let mut out = PathBuf::from("/");
    for component in absolute.components() {
        match component {
            Component::RootDir | Component::CurDir => (),
            Component::ParentDir => {
                out.pop();
            }
            Component::Normal(p) => {
                out.push(p);
                if out.exists() {
                    out = fs::canonicalize(out)?;
                }
            }
            _ => (),
        }
    }
    Ok(out)
}
fn within(root: &Path, name: &str) -> Result<PathBuf> {
    let p = resolve(&root.join(name))?;
    if !p.starts_with(root) {
        bail!("path is outside --root: {name}")
    }
    Ok(p)
}
fn relative(root: &Path, name: &str) -> Result<()> {
    within(root, name)?;
    let p = Path::new(name);
    if p.is_absolute() || p.components().any(|c| c == Component::ParentDir) {
        bail!("diff paths must be repo-relative")
    }
    Ok(())
}
fn run_git(
    root: &Path,
    args: &[OsString],
    env: &[(OsString, OsString)],
    input: Option<&[u8]>,
    accepted: &[i32],
    deadline: Option<Instant>,
) -> Result<Vec<u8>> {
    let mut cmd = Command::new("git");
    cmd.arg("-C")
        .arg(root)
        .args(args)
        .env("GIT_OPTIONAL_LOCKS", "0")
        .envs(env.iter().map(|(k, v)| (k, v)))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if input.is_some() {
        cmd.stdin(Stdio::piped());
    }
    let mut child = cmd.spawn()?;
    // Concurrent draining is required for binary diffs larger than pipe capacity.
    let mut stdout = child.stdout.take().unwrap();
    let mut stderr = child.stderr.take().unwrap();
    let a = std::thread::spawn(move || {
        let mut data = Vec::new();
        std::io::Read::read_to_end(&mut stdout, &mut data).map(|_| data)
    });
    let b = std::thread::spawn(move || {
        let mut data = Vec::new();
        std::io::Read::read_to_end(&mut stderr, &mut data).map(|_| data)
    });
    if let Some(data) = input {
        child.stdin.take().unwrap().write_all(data)?;
    }
    let end = deadline.unwrap_or_else(|| Instant::now() + Duration::from_secs(30));
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if Instant::now() >= end {
            let _ = child.kill();
            let _ = child.wait();
            bail!("Git command timed out")
        }
        std::thread::sleep(Duration::from_millis(5));
    };
    let out = a.join().map_err(|_| anyhow!("stdout reader failed"))??;
    let err = b.join().map_err(|_| anyhow!("stderr reader failed"))??;
    if !accepted.contains(&status.code().unwrap_or(-1)) {
        let error = String::from_utf8_lossy(&err);
        bail!(
            "{}",
            if error.trim().is_empty() {
                "Git command failed"
            } else {
                error.trim()
            }
        )
    }
    Ok(out)
}
fn git(root: &Path, args: &[&str]) -> Result<Vec<u8>> {
    run_git(
        root,
        &args.iter().map(OsString::from).collect::<Vec<_>>(),
        &[],
        None,
        &[0],
        None,
    )
}
fn text(data: &[u8]) -> String {
    String::from_utf8_lossy(data)
        .trim_end_matches('\n')
        .to_owned()
}
fn literal(paths: &[String]) -> Vec<OsString> {
    paths
        .iter()
        .map(|p| OsString::from(format!(":(literal){p}")))
        .collect()
}
fn read_items(root: &Path, specs: &[String]) -> Result<Vec<Value>> {
    let re = regex::Regex::new(r"^(.+):(\d+):(\d+)$")?;
    let mut items = Vec::new();
    for spec in specs {
        let captures = re.captures(spec);
        let name = captures
            .as_ref()
            .map_or(spec.as_str(), |m| m.get(1).unwrap().as_str());
        let path = within(root, name)?;
        if fs::metadata(&path)?.len() > LIMIT {
            bail!("source exceeds 8 MiB: {name}")
        }
        let raw = fs::read(&path)?;
        if raw.contains(&0) {
            bail!("binary source: {name}")
        }
        let source = std::str::from_utf8(&raw)?;
        let mut lines = Vec::new();
        let mut start = 0;
        let mut it = source.char_indices().peekable();
        while let Some((pos, ch)) = it.next() {
            if matches!(
                ch,
                '\n' | '\r'
                    | '\u{b}'
                    | '\u{c}'
                    | '\u{1c}'
                    | '\u{1d}'
                    | '\u{1e}'
                    | '\u{85}'
                    | '\u{2028}'
                    | '\u{2029}'
            ) {
                let mut end = pos + ch.len_utf8();
                if ch == '\r' && it.peek().is_some_and(|(_, c)| *c == '\n') {
                    end = it.next().unwrap().0 + 1;
                }
                lines.push(&source[start..end]);
                start = end;
            }
        }
        if start < source.len() {
            lines.push(&source[start..]);
        }
        let first = if let Some(m) = &captures {
            m[2].parse::<usize>()?
        } else {
            1
        };
        let last = if let Some(m) = &captures {
            m[3].parse::<usize>()?
        } else {
            lines.len()
        };
        if (first < 1 || last < first || first > lines.len() || last > lines.len())
            && (!lines.is_empty() || captures.is_some())
        {
            bail!("invalid source span: {spec}")
        }
        let excerpt = if lines.is_empty() {
            String::new()
        } else {
            lines[first - 1..last].concat()
        };
        items.push(json!({"path":path.strip_prefix(root)?.to_string_lossy(),"first":first,"last":last,"file_sha256":sha(&raw),"sha256":sha(excerpt.as_bytes()),"text":excerpt}));
    }
    Ok(items)
}
fn diff_items(root: &Path, paths: &[String], base: &str) -> Result<Vec<Value>> {
    for p in paths {
        relative(root, p)?;
    }
    git(root, &["rev-parse", "--show-toplevel"])?;
    let revision = text(&git(
        root,
        &[
            "rev-parse",
            "--verify",
            "--end-of-options",
            &format!("{base}^{{commit}}"),
        ],
    )?);
    let mut items = Vec::new();
    for staged in [true, false] {
        let mut args: Vec<OsString> = [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--binary",
            "--no-renames",
            "--unified=3",
        ]
        .iter()
        .map(OsString::from)
        .collect();
        if staged {
            args.push("--cached".into());
            args.push(revision.clone().into());
        }
        args.push("--".into());
        args.extend(literal(paths));
        let patch = run_git(root, &args, &[], None, &[0], None)?;
        items.push(json!({"path":if staged {"staged.diff"}else{"unstaged.diff"},"base":if staged {revision.as_str()}else{"index"},"sha256":sha(&patch),"text":String::from_utf8_lossy(&patch)}));
    }
    let mut args: Vec<OsString> = ["ls-files", "--others", "--exclude-standard", "-z", "--"]
        .iter()
        .map(OsString::from)
        .collect();
    args.extend(literal(paths));
    let names = run_git(root, &args, &[], None, &[0], None)?;
    for raw in names.split(|b| *b == 0).filter(|n| !n.is_empty()) {
        #[cfg(unix)]
        let name = {
            use std::os::unix::ffi::OsStrExt;
            OsStr::from_bytes(raw).to_os_string()
        };
        #[cfg(not(unix))]
        let name = OsString::from(String::from_utf8_lossy(raw).as_ref());
        let path = root.join(&name);
        let metadata = fs::symlink_metadata(&path)?;
        let (data, content) = if metadata.file_type().is_symlink() {
            let target = fs::read_link(&path)?;
            #[cfg(unix)]
            let bytes = {
                use std::os::unix::ffi::OsStrExt;
                target.as_os_str().as_bytes().to_vec()
            };
            #[cfg(not(unix))]
            let bytes = target.to_string_lossy().as_bytes().to_vec();
            let content = format!("symlink -> {}", String::from_utf8_lossy(&bytes));
            (bytes, content)
        } else {
            if metadata.len() > LIMIT {
                bail!("untracked file exceeds 8 MiB: {}", name.to_string_lossy())
            }
            let bytes = fs::read(path)?;
            let content = if bytes.contains(&0) {
                "[binary; inspect separately]".to_owned()
            } else {
                String::from_utf8(bytes.clone())?
            };
            (bytes, content)
        };
        items.push(json!({"path":name.to_string_lossy(),"status":"untracked","sha256":sha(&data),"text":content}));
    }
    Ok(items)
}
// Python's canonical json.dumps(..., sort_keys=True, ensure_ascii=False) spacing.
fn canonical_json(v: &Value, sorted: bool) -> String {
    match v {
        Value::Array(a) => format!(
            "[{}]",
            a.iter()
                .map(|v| canonical_json(v, sorted))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(o) => {
            let mut keys: Vec<_> = o.keys().collect();
            if sorted {
                keys.sort();
            }
            format!(
                "{{{}}}",
                keys.iter()
                    .map(|k| format!(
                        "{}: {}",
                        serde_json::to_string(k).unwrap(),
                        canonical_json(&o[*k], sorted)
                    ))
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        }
        _ => serde_json::to_string(v).unwrap(),
    }
}
struct Snapshot {
    head: String,
    commits: Vec<String>,
    env: Vec<(OsString, OsString)>,
}
fn snapshot(
    root: &Path,
    paths: &[String],
    folder: &Path,
    objects: &OsStr,
    deadline: Instant,
) -> Result<Snapshot> {
    fs::create_dir(folder)?;
    let index = folder.join("index");
    let env: Vec<(OsString, OsString)> = vec![
        ("GIT_INDEX_FILE".into(), index.as_os_str().into()),
        (
            "GIT_OBJECT_DIRECTORY".into(),
            folder.parent().unwrap().join("objects").into_os_string(),
        ),
        ("GIT_ALTERNATE_OBJECT_DIRECTORIES".into(), objects.into()),
        ("GIT_AUTHOR_NAME".into(), "harness".into()),
        ("GIT_AUTHOR_EMAIL".into(), "harness@invalid".into()),
        ("GIT_COMMITTER_NAME".into(), "harness".into()),
        ("GIT_COMMITTER_EMAIL".into(), "harness@invalid".into()),
        ("GIT_AUTHOR_DATE".into(), "2000-01-01T00:00:00Z".into()),
        ("GIT_COMMITTER_DATE".into(), "2000-01-01T00:00:00Z".into()),
    ];
    let run = |args: Vec<OsString>, envs: &[(OsString, OsString)], input: Option<&[u8]>| {
        run_git(root, &args, envs, input, &[0], Some(deadline))
    };
    let mk = |a: &[&str]| a.iter().map(OsString::from).collect::<Vec<_>>();
    let head = text(&run(
        mk(&["rev-parse", "--verify", "HEAD^{commit}"]),
        &[],
        None,
    )?);
    let source = PathBuf::from(text(&run(
        mk(&["rev-parse", "--path-format=absolute", "--git-path", "index"]),
        &[],
        None,
    )?));
    let before = match fs::read(&source) {
        Ok(v) => Some(v),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
        Err(e) => return Err(e.into()),
    };
    if let Some(data) = &before {
        fs::write(&index, data)?;
    } else {
        run(mk(&["read-tree", &head]), &env, None)?;
    }
    let commit = || -> Result<String> {
        let tree = text(&run(mk(&["write-tree"]), &env, None)?);
        Ok(text(&run(
            mk(&["commit-tree", &tree, "-p", &head, "-m", "harness snapshot"]),
            &env,
            None,
        )?))
    };
    let staged = commit()?;
    let mut args = mk(&[
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
    ]);
    args.extend(literal(paths));
    let names = run(args, &[], None)?;
    let names: BTreeSet<_> = names.split(|b| *b == 0).filter(|s| !s.is_empty()).collect();
    if names.len() > 10000 {
        bail!("snapshot file limit")
    }
    let working = if names.is_empty() {
        staged.clone()
    } else {
        let mut input = Vec::new();
        for name in names {
            input.extend_from_slice(b":(literal)");
            input.extend_from_slice(name);
            input.push(0);
        }
        run(
            mk(&["add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul"]),
            &env,
            Some(&input),
        )?;
        commit()?
    };
    let after = fs::read(&source).ok();
    if before != after
        || head
            != text(&run(
                mk(&["rev-parse", "--verify", "HEAD^{commit}"]),
                &[],
                None,
            )?)
    {
        bail!("snapshot changed")
    }
    let mut commits = vec![staged, working];
    commits.sort();
    commits.dedup();
    Ok(Snapshot { head, commits, env })
}
fn reclaim_scratch() {
    let Ok(entries) = fs::read_dir(std::env::temp_dir()) else {
        return;
    };
    let pattern = regex::Regex::new(r"^harness-overlap-([1-9][0-9]*)-[a-z0-9_]+$").unwrap();
    for entry in entries.flatten() {
        let name = entry.file_name();
        let Some(name) = name.to_str() else { continue };
        let Some(caps) = pattern.captures(name) else {
            continue;
        };
        let Ok(pid) = caps[1].parse::<i32>() else {
            continue;
        };
        let path = entry.path();
        if !fs::symlink_metadata(&path).is_ok_and(|m| m.is_dir() && !m.file_type().is_symlink())
            || fs::read(path.join(".owner")).ok().as_deref() != Some(b"harness-overlap-v1")
        {
            continue;
        }
        let dead = unsafe {
            libc::kill(pid, 0) != 0
                && std::io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH)
        };
        if dead {
            let _ = fs::remove_dir_all(path);
        }
    }
}
fn overlap_inner(root: &Path, paths: &[String], base: &str, report: &mut Value) -> Result<()> {
    let deadline = Instant::now() + Duration::from_secs(20);
    for path in paths {
        relative(root, path)?;
    }
    let run = |args: &[&str]| {
        run_git(
            root,
            &args.iter().map(OsString::from).collect::<Vec<_>>(),
            &[],
            None,
            &[0],
            Some(deadline),
        )
    };
    if resolve(Path::new(&text(&run(&["rev-parse", "--show-toplevel"])?)))? != root {
        bail!("overlap requires worktree root")
    }
    let revision = text(&run(&[
        "rev-parse",
        "--verify",
        "--end-of-options",
        &format!("{base}^{{commit}}"),
    ])?);
    report["base"] = json!(revision);
    let records = run(&["worktree", "list", "--porcelain", "-z"])?;
    let mut peers = Vec::new();
    for record in records
        .split(|b| *b == 0)
        .collect::<Vec<_>>()
        .split(|r| r.is_empty())
    {
        if record.is_empty()
            || record[0].strip_prefix(b"worktree ").is_none()
            || record.iter().any(|r| *r == b"bare")
        {
            continue;
        }
        let p = PathBuf::from(String::from_utf8_lossy(&record[0][9..]).to_string());
        if resolve(&p)? != root {
            peers.push(p);
        }
    }
    if peers.is_empty() {
        return Ok(());
    }
    if peers.len() > 20 {
        report["limitations"]
            .as_array_mut()
            .unwrap()
            .push(json!("peerLimit"));
    }
    let mut objects = OsString::from(text(&run(&[
        "rev-parse",
        "--path-format=absolute",
        "--git-path",
        "objects",
    ])?));
    if let Some(extra) = std::env::var_os("GIT_ALTERNATE_OBJECT_DIRECTORIES") {
        objects.push(":");
        objects.push(extra);
    }
    reclaim_scratch();
    let temp = tempfile::Builder::new()
        .prefix(&format!("harness-overlap-{}-", std::process::id()))
        .tempdir()?;
    fs::write(temp.path().join(".owner"), "harness-overlap-v1")?;
    fs::create_dir(temp.path().join("objects"))?;
    let mine = snapshot(root, paths, &temp.path().join("mine"), &objects, deadline)?;
    report["snapshot"] = json!(sha(mine.commits.concat().as_bytes()));
    for (number, peer) in peers.iter().take(20).enumerate() {
        let mut row = json!({"worktree":peer.to_string_lossy(),"state":"unknown","files":[]});
        let result = (|| -> Result<()> {
            let theirs = snapshot(
                peer,
                paths,
                &temp.path().join(number.to_string()),
                &objects,
                deadline,
            )?;
            row["snapshot"] = json!(sha(theirs.commits.concat().as_bytes()));
            let common = text(&run(&[
                "merge-base",
                "--octopus",
                &revision,
                &mine.head,
                &theirs.head,
            ])?);
            let changed = |snap: &Snapshot| -> Result<BTreeSet<Vec<u8>>> {
                let mut result = BTreeSet::new();
                for commit in &snap.commits {
                    let mut args: Vec<OsString> = [
                        "diff",
                        "--no-ext-diff",
                        "--no-textconv",
                        "--no-renames",
                        "--name-only",
                        "-z",
                        &common,
                        commit,
                        "--",
                    ]
                    .iter()
                    .map(OsString::from)
                    .collect();
                    args.extend(literal(paths));
                    let raw = run_git(root, &args, &mine.env, None, &[0], Some(deadline))?;
                    result.extend(
                        raw.split(|b| *b == 0)
                            .filter(|s| !s.is_empty())
                            .map(|s| s.to_vec()),
                    );
                }
                Ok(result)
            };
            let a = changed(&mine)?;
            let b = changed(&theirs)?;
            let shared: BTreeSet<_> = a.intersection(&b).cloned().collect();
            row["files"] = json!(shared
                .iter()
                .map(|s| String::from_utf8_lossy(s).to_string())
                .collect::<Vec<_>>());
            row["state"] = json!(if shared.is_empty() {
                "clear"
            } else {
                "overlap"
            });
            if !shared.is_empty() {
                for first in &mine.commits {
                    for second in &theirs.commits {
                        let args = [
                            "merge-tree",
                            "--write-tree",
                            "--name-only",
                            "--no-messages",
                            "-z",
                            first,
                            second,
                        ]
                        .iter()
                        .map(OsString::from)
                        .collect::<Vec<_>>();
                        let raw = run_git(root, &args, &mine.env, None, &[0, 1], Some(deadline))?;
                        let mut parts = raw.split(|b| *b == 0);
                        let tree = parts.next().unwrap_or_default();
                        if !matches!(tree.len(), 40 | 64) || !tree.iter().all(u8::is_ascii_hexdigit)
                        {
                            bail!("invalid merge output")
                        };
                        if parts.any(|p| shared.contains(p)) {
                            row["state"] = json!("conflict");
                        }
                    }
                }
            }
            Ok(())
        })();
        if result.is_err() {
            row["state"] = json!("unknown");
            report["limitations"]
                .as_array_mut()
                .unwrap()
                .push(json!("peerUnavailable"));
        }
        report["peers"].as_array_mut().unwrap().push(row);
    }
    Ok(())
}
pub(crate) fn overlap_report(root: &Path, paths: &[String], base: &str) -> Value {
    let mut report = json!({"complete":true,"state":"clear","peers":[],"limitations":[]});
    if overlap_inner(root, paths, base, &mut report).is_err() {
        report["limitations"]
            .as_array_mut()
            .unwrap()
            .push(json!("snapshotUnavailable"));
    }
    let limits = report["limitations"].as_array_mut().unwrap();
    limits.sort_by(|a, b| a.as_str().cmp(&b.as_str()));
    limits.dedup();
    let complete = limits.is_empty();
    let peers = report["peers"].as_array().unwrap();
    let state = if !complete {
        "unknown"
    } else if peers.iter().any(|p| p["state"] == "conflict") {
        "conflict"
    } else if peers.iter().any(|p| p["state"] == "overlap") {
        "overlap"
    } else {
        "clear"
    };
    report["state"] = json!(state);
    report["complete"] = json!(complete);
    overlap_preview(&report, 6000)
}
fn overlap_preview(report: &Value, limit: usize) -> Value {
    let mut out = report.clone();
    out["peers"] = json!([]);
    out["omitted_peers"] = json!(0);
    let mut remaining =
        limit.max(512) as isize - canonical_json(&out, false).chars().count() as isize - 96;
    let peers = report["peers"].as_array().unwrap();
    for (i, peer) in peers.iter().enumerate() {
        let files = peer["files"].as_array().unwrap();
        let mut row = peer.clone();
        row["files"] = json!([]);
        row["omitted_files"] = json!(files.len());
        remaining -= canonical_json(&row, false).chars().count() as isize + 2;
        if remaining < 0 {
            out["omitted_peers"] = json!(peers.len() - i);
            out["complete"] = json!(false);
            out["state"] = json!("unknown");
            out["limitations"]
                .as_array_mut()
                .unwrap()
                .push(json!("previewLimit"));
            break;
        }
        for file in files {
            let size = canonical_json(file, false).chars().count() as isize + 2;
            if size > remaining {
                break;
            }
            row["files"].as_array_mut().unwrap().push(file.clone());
            let n = row["omitted_files"].as_u64().unwrap();
            row["omitted_files"] = json!(n - 1);
            remaining -= size;
        }
        out["peers"].as_array_mut().unwrap().push(row);
    }
    out
}
fn inspect(args: &Args) -> Result<(Value, i32)> {
    if !(1..=100000).contains(&args.max_chars) {
        bail!("--max-chars must be 1..100000")
    }
    let root = resolve(&expand(&args.root))?;
    let root_str = root.to_string_lossy().to_string();
    let (mode, items, overlap) = match &args.mode {
        Mode::Read { files } => ("read", read_items(&root, files)?, None),
        Mode::Diff {
            paths,
            base,
            overlap,
        } => {
            let items = diff_items(&root, paths, base)?;
            let report = if *overlap {
                let mut r = json!({"complete":true,"state":"clear","peers":[],"limitations":[]});
                if overlap_inner(&root, paths, base, &mut r).is_err() {
                    r["limitations"]
                        .as_array_mut()
                        .unwrap()
                        .push(json!("snapshotUnavailable"));
                }
                let limits = r["limitations"].as_array_mut().unwrap();
                limits.sort_by(|a, b| a.as_str().cmp(&b.as_str()));
                limits.dedup();
                let complete = limits.is_empty();
                let peers = r["peers"].as_array().unwrap();
                let state = if !complete {
                    "unknown"
                } else if peers.iter().any(|p| p["state"] == "conflict") {
                    "conflict"
                } else if peers.iter().any(|p| p["state"] == "overlap") {
                    "overlap"
                } else {
                    "clear"
                };
                r["state"] = json!(state);
                r["complete"] = json!(complete);
                Some(r)
            } else {
                None
            };
            ("diff", items, report)
        }
    };
    let mut pack = json!({"schema":"harness-context-v1","root":root_str,"mode":mode,"items":items});
    if let Some(report) = overlap {
        pack["overlap"] = report;
    }
    let artifact = if args.no_cache {
        None
    } else {
        let raw = format!("{}\n", canonical_json(&pack, true));
        let cache = dirs::home_dir()
            .context("home unavailable")?
            .join(".cache/harness/context");
        fs::create_dir_all(&cache)?;
        let path = cache.join(format!("{}.json", sha(raw.as_bytes())));
        if fs::read(&path).ok().as_deref() != Some(raw.as_bytes()) {
            let mut temp = tempfile::Builder::new()
                .prefix(".pack-")
                .tempfile_in(&cache)?;
            temp.write_all(raw.as_bytes())?;
            temp.persist(&path)?;
        }
        Some(path)
    };
    let mut old = BTreeSet::new();
    let key = |item: &Value| {
        (
            item["path"].to_string(),
            item["first"].to_string(),
            item["last"].to_string(),
            item["sha256"].to_string(),
        )
    };
    if let Some(since) = &args.since {
        let raw = fs::read(since)?;
        let hash = sha(&raw);
        if since.file_stem().and_then(OsStr::to_str) != Some(hash.as_str()) {
            bail!("--since pack hash mismatch")
        }
        let previous: Value = serde_json::from_slice(&raw)?;
        if previous["root"] != pack["root"] || previous["mode"] != pack["mode"] {
            bail!("--since root or mode mismatch")
        }
        for item in previous["items"].as_array().context("invalid pack")? {
            old.insert(key(item));
        }
    }
    let overlap = pack
        .get("overlap")
        .map(|r| overlap_preview(r, args.max_chars / 2));
    let mut remaining = overlap.as_ref().map_or(args.max_chars, |r| {
        args.max_chars
            .saturating_sub(canonical_json(r, false).chars().count())
    });
    let mut rows = Vec::new();
    let mut complete = true;
    for item in pack["items"].as_array().unwrap() {
        let mut row: Map<String, Value> = item
            .as_object()
            .unwrap()
            .iter()
            .filter(|(k, _)| *k != "text")
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        if old.contains(&key(item)) {
            row.insert(
                "unchanged_from".into(),
                json!(args.since.as_ref().unwrap().to_string_lossy()),
            );
        } else {
            let text = item["text"].as_str().unwrap();
            let size = text.chars().count();
            let part: String = text.chars().take(remaining).collect();
            let taken = part.chars().count();
            remaining -= taken;
            let omitted = size - taken;
            complete &= omitted == 0;
            row.insert("text".into(), json!(part));
            row.insert("omitted_chars".into(), json!(omitted));
        }
        rows.push(Value::Object(row));
    }
    let mut out = json!({"schema":"harness-context-v1","artifact":artifact.as_ref().map(|p|p.to_string_lossy().to_string()),"root":root_str,"preview_complete":complete,"items":rows});
    let mut status = 0;
    if let Some(report) = overlap {
        if report["omitted_peers"] != 0
            || report["peers"]
                .as_array()
                .unwrap()
                .iter()
                .any(|p| p["omitted_files"] != 0)
        {
            out["preview_complete"] = json!(false);
        }
        if report["state"] == "conflict" || report["state"] == "unknown" {
            status = 2;
        }
        out["overlap"] = report;
    }
    Ok((out, status))
}
pub fn run_inspect(args: &[OsString]) -> Result<i32> {
    let args = Args::try_parse_from(
        std::iter::once(OsString::from("inspect")).chain(args.iter().cloned()),
    )?;
    match inspect(&args) {
        Ok((value, status)) => {
            println!("{}", canonical_json(&value, false));
            Ok(status)
        }
        Err(error) => {
            println!(
                "{}",
                canonical_json(&json!({"error":error.to_string()}), false)
            );
            Ok(2)
        }
    }
}
