use anyhow::{anyhow, Result};
use clap::{Parser, ValueEnum};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashMap, HashSet},
    ffi::OsString,
    fs,
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant, UNIX_EPOCH},
};

const LIMIT: u64 = 128 * 1024 * 1024;
#[derive(Clone, Copy, ValueEnum, PartialEq)]
enum Coverage {
    Sample,
    Full,
}
impl Coverage {
    fn name(self) -> &'static str {
        if self == Self::Full {
            "full"
        } else {
            "sample"
        }
    }
}
#[derive(Parser)]
struct FramesArgs {
    capture: PathBuf,
    #[arg(long)]
    root: Option<PathBuf>,
    #[arg(long)]
    downloads: Option<PathBuf>,
    #[arg(long)]
    place: Option<String>,
    #[arg(long)]
    marker: Vec<String>,
    #[arg(long, value_enum, default_value = "sample")]
    coverage: Coverage,
    #[arg(long, default_value_t = 1)]
    min_frames: i64,
    #[arg(long)]
    expected_frames: Option<usize>,
    #[arg(long, default_value_t = 20.0)]
    spike_ms: f64,
    #[arg(long, default_value = "node")]
    node: String,
}
#[derive(Parser)]
struct CaptureArgs {
    #[arg(value_parser=["baseline", "collect"])]
    action: String,
    #[arg(long)]
    root: Vec<PathBuf>,
    #[arg(long)]
    baseline: PathBuf,
    #[arg(long)]
    output: Option<PathBuf>,
    #[arg(long)]
    human_complete: bool,
    #[arg(long)]
    place: Option<String>,
    #[arg(long)]
    run: Option<String>,
    #[arg(long)]
    marker: Vec<String>,
    #[arg(long, value_enum, default_value = "sample")]
    coverage: Coverage,
    #[arg(long, default_value_t = 1)]
    min_frames: i64,
    #[arg(long)]
    expected_frames: Option<usize>,
    #[arg(long, default_value_t = 20.0)]
    spike_ms: f64,
    #[arg(long, default_value_t = 5.0)]
    wait: f64,
    #[arg(long, default_value = "node")]
    node: String,
    #[arg(long)]
    select: Option<PathBuf>,
}
#[derive(Serialize, Deserialize)]
struct Report {
    marker: String,
    coverage: String,
    first: usize,
    last: usize,
    frames: usize,
    scope_average_ms: f64,
    scope_max_ms: f64,
    frame_average_ms: f64,
    frame_max_ms: f64,
    spike_threshold_ms: f64,
    spikes: Vec<(usize, f64)>,
    overflow: usize,
}
fn num(v: &Value) -> Result<f64> {
    v.as_f64()
        .filter(|v| v.is_finite())
        .ok_or_else(|| anyhow!("nonfinite event data"))
}
fn repr(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Null => "None".into(),
        _ => v.to_string(),
    }
}
fn analyze(
    data: &Value,
    place: &str,
    markers: &[String],
    mode: Coverage,
    minimum: i64,
    expected: Option<usize>,
    spike: f64,
    run: Option<&str>,
) -> Result<Vec<Report>> {
    if repr(&data["GeneralInfo"]["PlaceId"]) != place {
        return Err(anyhow!("wrong place"));
    }
    if minimum < 1 || !spike.is_finite() || spike <= 0.0 {
        return Err(anyhow!("invalid window bounds"));
    }
    if markers.is_empty() || markers.iter().collect::<HashSet<_>>().len() != markers.len() {
        return Err(anyhow!("unique workload markers required"));
    }
    if mode == Coverage::Full && !expected.is_some_and(|v| (1..=100000).contains(&v)) {
        return Err(anyhow!("expected frame count must be 1..100000"));
    }
    let runs: HashSet<&str> = markers
        .iter()
        .filter_map(|m| {
            let mut p = m.split('/');
            if p.next() == Some("Harness") {
                let r = p.next()?;
                p.next()?;
                Some(r)
            } else {
                None
            }
        })
        .collect();
    if runs.len() > 1 {
        return Err(anyhow!("different run windows"));
    }
    let run = run
        .filter(|s| !s.is_empty())
        .or_else(|| runs.iter().next().copied());
    let available = data
        .get("RunId")
        .or_else(|| data["GeneralInfo"].get("RunId"));
    if let (Some(r), Some(v)) = (run, available) {
        if !v.is_null() && repr(v) != r {
            return Err(anyhow!("wrong run identity"));
        }
    }
    if let Some(r) = run {
        if markers
            .iter()
            .any(|m| m.starts_with("Harness/") && !m.starts_with(&format!("Harness/{r}/")))
        {
            return Err(anyhow!("marker run mismatch"));
        }
    }
    let frames = data["Frames"]
        .as_array()
        .filter(|a| !a.is_empty())
        .ok_or_else(|| anyhow!("unsupported viewer data"))?;
    let timers = data["TimerInfo"]
        .as_array()
        .ok_or_else(|| anyhow!("unsupported viewer data"))?;
    if data["ThreadClobbered"]
        .as_array()
        .is_some_and(|a| a.iter().any(truthy))
    {
        return Err(anyhow!("clobbered capture"));
    }
    let names: HashMap<String, String> = timers
        .iter()
        .map(|t| {
            (
                t["id"].to_string(),
                t["name"].as_str().unwrap_or("").to_owned(),
            )
        })
        .collect();
    let mut selected: Vec<BTreeMap<usize, Vec<f64>>> =
        markers.iter().map(|_| BTreeMap::new()).collect();
    let mut indices: Vec<Vec<usize>> = markers.iter().map(|_| Vec::new()).collect();
    for (index, frame) in frames.iter().enumerate() {
        if let Some(threads) = frame["tt"].as_array() {
            for (thread, types) in threads.iter().enumerate() {
                let types = types
                    .as_array()
                    .ok_or_else(|| anyhow!("incomplete event arrays"))?;
                let ids = frame["ti"]
                    .get(thread)
                    .and_then(Value::as_array)
                    .ok_or_else(|| anyhow!("incomplete event arrays"))?;
                let times = frame["ts"]
                    .get(thread)
                    .and_then(Value::as_array)
                    .ok_or_else(|| anyhow!("incomplete event arrays"))?;
                if types.len() != ids.len() || types.len() != times.len() {
                    return Err(anyhow!("incomplete event arrays"));
                }
                let mut stack: Vec<(String, f64, Vec<usize>, String)> = Vec::new();
                for ((kind, id), time) in types.iter().zip(ids).zip(times) {
                    let Some(kind) = kind.as_i64() else { continue };
                    if kind != 0 && kind != 1 {
                        continue;
                    }
                    let instant = num(time)?;
                    let key = id.to_string();
                    let name = names.get(&key).map(String::as_str).unwrap_or("");
                    let matches: Vec<usize> = markers
                        .iter()
                        .enumerate()
                        .filter_map(|(i, m)| {
                            if name == m
                                || name
                                    .strip_prefix(m.as_str())
                                    .is_some_and(|s| s.starts_with('/'))
                            {
                                Some(i)
                            } else {
                                None
                            }
                        })
                        .collect();
                    if kind == 1 {
                        stack.push((key, instant, matches, name.to_owned()));
                        continue;
                    }
                    let Some((start, begin, old, start_name)) = stack.pop() else {
                        if !matches.is_empty() {
                            return Err(anyhow!("partial workload scope"));
                        }
                        continue;
                    };
                    if start != key {
                        if !matches.is_empty() || !old.is_empty() {
                            return Err(anyhow!("mismatched workload scope"));
                        }
                        continue;
                    }
                    for m in old {
                        if truthy(&frame["paused"])
                            || truthy(&frame["incomplete"])
                            || instant < begin
                        {
                            return Err(anyhow!("incomplete workload frame"));
                        }
                        selected[m].entry(index).or_default().push(instant - begin);
                        let suffix = start_name[markers[m].len()..].trim_matches('/');
                        if !suffix.is_empty() && suffix.chars().all(|c| c.is_ascii_digit()) {
                            if let Ok(v) = suffix.parse() {
                                indices[m].push(v);
                            }
                        }
                    }
                }
                if stack.iter().any(|x| !x.2.is_empty()) {
                    return Err(anyhow!("partial workload scope"));
                }
            }
        }
    }
    let mut reports = Vec::new();
    for (m, observations) in selected.iter().enumerate() {
        let active: Vec<usize> = observations.keys().copied().collect();
        if active.is_empty() {
            return Err(anyhow!("workload marker absent: {}", markers[m]));
        }
        let first = active[0];
        let last = *active.last().unwrap();
        if active.len() < minimum as usize || last - first + 1 != active.len() {
            return Err(anyhow!("insufficient or discontinuous coverage"));
        }
        let mut idx = indices[m].clone();
        idx.sort_unstable();
        if mode == Coverage::Full
            && (idx.len() != expected.unwrap() || idx.iter().enumerate().any(|(i, n)| *n != i + 1))
        {
            return Err(anyhow!(
                "partial capture; full measurement coverage required"
            ));
        }
        if !idx.is_empty() && idx.iter().enumerate().any(|(i, n)| *n != idx[0] + i) {
            return Err(anyhow!("duplicate or missing workload indices"));
        }
        let mut costs = Vec::new();
        let mut periods = Vec::new();
        let mut spikes = Vec::new();
        let mut count: usize = 0;
        for &i in &active {
            let duration = num(&frames[i]["frameend"])? - num(&frames[i]["framestart"])?;
            if duration <= 0.0 {
                return Err(anyhow!("invalid frame interval"));
            }
            periods.push(duration);
            costs.push(observations[&i].iter().sum::<f64>());
            if duration > spike {
                count += 1;
                if spikes.len() < 256 {
                    spikes.push((i, duration));
                }
            }
        }
        reports.push(Report {
            marker: markers[m].clone(),
            coverage: mode.name().into(),
            first,
            last,
            frames: active.len(),
            scope_average_ms: costs.iter().sum::<f64>() / costs.len() as f64,
            scope_max_ms: costs.iter().copied().fold(0.0, f64::max),
            frame_average_ms: periods.iter().sum::<f64>() / periods.len() as f64,
            frame_max_ms: periods.iter().copied().fold(0.0, f64::max),
            spike_threshold_ms: spike,
            spikes,
            overflow: count.saturating_sub(256),
        });
    }
    Ok(reports)
}
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().unwrap_or(0.0) != 0.0,
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(a) => !a.is_empty(),
    }
}
fn render(reports: &[Report]) {
    for r in reports {
        println!("PROFILE|{}|{} frames={}|scope-average={:.3}ms|frame-interval-average={:.3}ms|spikes={} max={:.3}ms overflow={}",r.marker,r.coverage,r.frames,r.scope_average_ms,r.frame_average_ms,r.spikes.len()+r.overflow,r.frame_max_ms,r.overflow);
    }
}
fn export_html(path: &Path, dest: &Path, node: &str, timeout: Duration) -> Result<PathBuf> {
    fs::create_dir_all(dest)?;
    let adapter = Path::new(env!("CARGO_MANIFEST_DIR")).join("tools/frame_census/export_html.cjs");
    let mut child = Command::new(node)
        .arg("--max-old-space-size=512")
        .arg(adapter)
        .arg(path)
        .arg(dest)
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()?;
    let start = Instant::now();
    loop {
        if child.try_wait()?.is_some() {
            let output = child.wait_with_output()?;
            if !output.status.success() {
                let err = String::from_utf8_lossy(&output.stderr);
                return Err(anyhow!(
                    "HTML export rejected: {}",
                    err.lines()
                        .next()
                        .unwrap_or("")
                        .chars()
                        .take(180)
                        .collect::<String>()
                ));
            }
            return Ok(dest.join("viewer-data.json"));
        }
        if start.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            return Err(anyhow!("HTML export timed out"));
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}
fn read_json(path: &Path) -> Result<Value> {
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}
fn env_failure(cause: &str, remedy: impl std::fmt::Display) -> i32 {
    println!("ENV|{cause}|{remedy}");
    3
}
fn frames(a: FramesArgs) -> Result<i32> {
    let capture = a.capture.to_string_lossy();
    if capture.ends_with(".html") || capture.ends_with("viewer-data.json") {
        if a.marker.is_empty() || a.place.is_none() {
            return Ok(env_failure(
                "window-required",
                "supply --place and --marker; select sample or full coverage",
            ));
        }
        let temp = tempfile::Builder::new()
            .prefix("harness-viewer-")
            .tempdir()?;
        let path = if capture.ends_with(".html") {
            export_html(&a.capture, temp.path(), &a.node, Duration::from_secs(60))?
        } else {
            a.capture.clone()
        };
        render(&analyze(
            &read_json(&path)?,
            a.place.as_deref().unwrap(),
            &a.marker,
            a.coverage,
            a.min_frames,
            a.expected_frames,
            a.spike_ms,
            None,
        )?);
        return Ok(0);
    }
    let mut stem = capture.to_string();
    for suffix in [".csv", "_counters.csv", "_summary.json"] {
        if stem.ends_with(suffix) {
            stem.truncate(stem.len() - suffix.len());
            break;
        }
    }
    let downloads = a
        .downloads
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join("Downloads"));
    let alternatives = [
        PathBuf::from(&stem),
        downloads.join(Path::new(&stem).file_name().unwrap_or_default()),
    ];
    let paths = |base: &Path| -> Vec<PathBuf> {
        [".csv", "_counters.csv", "_summary.json"]
            .iter()
            .map(|s| PathBuf::from(format!("{}{s}", base.display())))
            .collect()
    };
    let Some(trio) = alternatives
        .iter()
        .map(|b| paths(b))
        .find(|v| v.iter().all(|p| p.is_file()))
    else {
        let missing = paths(&alternatives[0])
            .iter()
            .filter(|p| !p.is_file())
            .map(|p| {
                p.file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .into_owned()
            })
            .collect::<Vec<_>>()
            .join(", ");
        return Ok(env_failure("native-exports-missing",format!("export summary.json + counters.csv + csv from the web UI: open the dump in the browser, use the flame-graph Export menu - Summary JSON, Counters CSV, Timeline CSV save to Downloads beside the dump (missing: {missing})")));
    };
    let summary = match read_json(&trio[2]) {
        Ok(v) => v,
        Err(e) => return Ok(env_failure("summary-unparseable", e)),
    };
    for k in ["num_frames", "cpu_time_median"] {
        if summary.get(k).is_none() {
            return Ok(env_failure(
                "summary-shape-changed",
                format!("missing {k} - schema drifted, refusing to parse fiction"),
            ));
        }
    }
    let counters = match fs::read_to_string(&trio[1]) {
        Ok(v) => v,
        Err(e) => return Ok(env_failure("counters-unreadable", e)),
    };
    if !counters
        .lines()
        .next()
        .is_some_and(|l| l.contains("Name") && l.contains("Value"))
    {
        return Ok(env_failure(
            "counters-shape-changed",
            "header is not Name, Value, Limit - refusing to parse fiction",
        ));
    }
    let text = match fs::read_to_string(&trio[0]) {
        Ok(v) => v,
        Err(e) => return Ok(env_failure("csv-unreadable", e)),
    };
    let mut thread = false;
    let mut anchor = false;
    let mut details = Vec::new();
    for line in text.lines() {
        let c: Vec<&str> = line.split(',').map(str::trim).collect();
        if c.is_empty() || c[0].is_empty() {
            continue;
        }
        if c[0] == "frames" && c.get(1).is_some_and(|v| v.parse::<i64>().is_ok()) {
            anchor = true;
            continue;
        }
        if c[0].starts_with("Thread Name:") {
            thread = true;
            continue;
        }
        if c.len() >= 4 {
            if let (Ok(begin), Ok(end)) = (c[2].parse::<f64>(), c[3].parse::<f64>()) {
                if thread {
                    details.push((c[0].to_owned(), c[1].to_owned(), begin, end));
                } else {
                    anchor = true;
                }
            }
        }
    }
    if !anchor && details.is_empty() {
        return Ok(env_failure(
            "csv-shape-changed",
            "no frames anchor, no sections - refusing to parse fiction",
        ));
    }
    let mut wanted = HashSet::new();
    if let Some(place) = a.place {
        wanted.insert(place.parse::<i64>()?);
    } else {
        let root = a.root.unwrap_or(std::env::current_dir()?);
        if let Ok(s) = fs::read_to_string(root.join("AGENTS.md")) {
            let mut active = false;
            for line in s.lines() {
                if line.starts_with("## ") {
                    if active {
                        break;
                    }
                    active = line == "## places";
                    continue;
                }
                if active {
                    let v: Vec<_> = line.trim().split('|').collect();
                    if v.len() == 2 {
                        if let Ok(n) = v[1].parse::<i64>() {
                            wanted.insert(n);
                        }
                    }
                }
            }
        }
    }
    if !wanted.is_empty()
        && !repr(&summary["general_info"]["PlaceId"])
            .parse::<i64>()
            .ok()
            .is_some_and(|v| wanted.contains(&v))
    {
        return Ok(env_failure(
            "wrong-place",
            "supply the matching native exports",
        ));
    }
    if a.coverage == Coverage::Full {
        return Ok(env_failure(
            "coverage-unavailable",
            "native timeline has no workload indices; use saved HTML event arrays",
        ));
    }
    let mut rows: HashMap<(String, String), Vec<f64>> = HashMap::new();
    for (group, marker, begin, end) in details {
        if !begin.is_finite() || !end.is_finite() || end < begin {
            return Err(anyhow!("invalid event duration"));
        }
        if !a.marker.is_empty() && !a.marker.contains(&marker) {
            continue;
        }
        rows.entry((group, marker)).or_default().push(end - begin);
    }
    if rows.is_empty() {
        return Ok(env_failure(
            "missing-events",
            "native exports contain no selected event details",
        ));
    }
    let mut rows: Vec<_> = rows.into_iter().collect();
    rows.sort_by(|a, b| b.1.iter().sum::<f64>().total_cmp(&a.1.iter().sum::<f64>()));
    println!("PROFILE|native-event-window|inclusive scopes");
    for ((group, marker), v) in rows.iter().take(15) {
        let sum = v.iter().sum::<f64>();
        println!(
            "scope|{marker}|{group}|average={:.3}ms|calls={}|total={:.3}ms|spikes={} max={:.3}ms",
            sum / v.len() as f64,
            v.len(),
            sum,
            v.iter().filter(|x| **x > a.spike_ms).count(),
            v.iter().copied().fold(f64::NEG_INFINITY, f64::max)
        );
    }
    Ok(0)
}

#[derive(Clone, Serialize, Deserialize, PartialEq)]
struct Stamp(u128, u64, String);
fn digest(path: &Path) -> Result<String> {
    let metadata = fs::metadata(path)?;
    if metadata.len() > LIMIT {
        return Err(anyhow!("capture size limit"));
    }
    Ok(hex::encode(Sha256::digest(fs::read(path)?)))
}
fn expand(path: &Path) -> PathBuf {
    let s = path.to_string_lossy();
    if s == "~" {
        dirs::home_dir().unwrap_or_default()
    } else if let Some(rest) = s.strip_prefix("~/") {
        dirs::home_dir().unwrap_or_default().join(rest)
    } else {
        path.to_owned()
    }
}
fn inventory(roots: &[PathBuf]) -> Result<BTreeMap<String, Stamp>> {
    let mut result = BTreeMap::new();
    for root in roots {
        let root = expand(root);
        let entries = match fs::read_dir(root) {
            Ok(v) => v,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(e) => return Err(e.into()),
        };
        for entry in entries {
            let entry = entry?;
            let name = entry.file_name().to_string_lossy().into_owned();
            if !(name.starts_with("microprofile") && name.ends_with(".html")
                || name.ends_with("viewer-data.json"))
            {
                continue;
            }
            let kind = entry.file_type()?;
            if !kind.is_file() || kind.is_symlink() {
                continue;
            }
            let path = entry.path().canonicalize()?;
            let m = fs::metadata(&path)?;
            let time = m.modified()?.duration_since(UNIX_EPOCH)?.as_nanos();
            result.insert(
                path.to_string_lossy().into_owned(),
                Stamp(time, m.len(), digest(&path)?),
            );
        }
    }
    Ok(result)
}
fn capture(a: CaptureArgs) -> Result<i32> {
    let roots = if a.root.is_empty() {
        let h = dirs::home_dir().unwrap_or_default();
        vec![h.join("Library/Logs/Roblox"), h.join("Downloads")]
    } else {
        a.root.clone()
    };
    if a.action == "baseline" {
        if let Some(p) = a.baseline.parent().filter(|p| !p.as_os_str().is_empty()) {
            fs::create_dir_all(p)?;
        }
        let mut out = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&a.baseline)?;
        serde_json::to_writer(&mut out, &inventory(&roots)?)?;
        println!("CAPTURE|baseline recorded");
        return Ok(0);
    }
    if !a.human_complete
        || a.place.as_deref().is_none_or(str::is_empty)
        || a.marker.is_empty()
        || a.output.is_none()
    {
        return Err(anyhow!(
            "human completion, place, marker and archive output required"
        ));
    }
    if !a.wait.is_finite()
        || !(0.0..=60.0).contains(&a.wait)
        || a.min_frames < 1
        || !a.spike_ms.is_finite()
        || a.spike_ms <= 0.0
    {
        return Err(anyhow!("invalid capture bounds"));
    }
    if a.coverage == Coverage::Full && !a.expected_frames.is_some_and(|n| n > 0) {
        return Err(anyhow!("expected frame count required"));
    }
    let baseline: BTreeMap<String, Stamp> = serde_json::from_slice(&fs::read(&a.baseline)?)?;
    let deadline = Instant::now() + Duration::from_secs_f64(a.wait);
    let mut observed: HashMap<String, (Stamp, Instant)> = HashMap::new();
    let mut failures: BTreeMap<String, String> = BTreeMap::new();
    loop {
        let now = inventory(&roots)?;
        let mut candidates: Vec<_> = now
            .iter()
            .filter(|(p, s)| baseline.get(*p) != Some(*s))
            .collect();
        candidates.sort_by(|a, b| b.1 .0.cmp(&a.1 .0));
        if candidates.len() > 64 {
            return Err(anyhow!("candidate limit; narrow dump directories"));
        }
        let temp = tempfile::Builder::new()
            .prefix("harness-capture-")
            .tempdir()?;
        let mut accepted = Vec::new();
        let mut pending = Vec::new();
        for (index, (filename, stamp)) in candidates.iter().enumerate() {
            let path = Path::new(filename);
            if let Some(s) = &a.select {
                if fs::canonicalize(s).ok().as_deref() != Some(path) {
                    continue;
                }
            }
            if observed.get(*filename).is_none_or(|(s, _)| s != *stamp) {
                observed.insert((*filename).clone(), ((*stamp).clone(), Instant::now()));
                pending.push((*filename).clone());
                continue;
            }
            if observed[*filename].1.elapsed() < Duration::from_millis(500) {
                pending.push((*filename).clone());
                continue;
            }
            let dir = temp.path().join(index.to_string());
            let parsed = (|| -> Result<Vec<Report>> {
                let p = if path.extension().is_some_and(|s| s == "html") {
                    export_html(
                        path,
                        &dir,
                        &a.node,
                        deadline
                            .saturating_duration_since(Instant::now())
                            .min(Duration::from_secs(60))
                            .max(Duration::from_millis(10)),
                    )?
                } else {
                    path.to_owned()
                };
                let data = read_json(&p)?;
                analyze(
                    &data,
                    a.place.as_deref().unwrap(),
                    &a.marker,
                    a.coverage,
                    a.min_frames,
                    a.expected_frames,
                    a.spike_ms,
                    a.run.as_deref(),
                )
            })();
            match parsed {
                Ok(reports) => {
                    if digest(path)? != stamp.2 {
                        pending.push((*filename).clone());
                    } else {
                        accepted.push(((*filename).clone(), dir, (*stamp).clone(), reports));
                    }
                }
                Err(e) => {
                    let message = e.to_string();
                    if e.downcast_ref::<std::io::Error>().is_some()
                        || e.downcast_ref::<serde_json::Error>().is_some()
                        || message.contains("timed out")
                        || message.to_lowercase().contains("unexpected end")
                        || message.to_lowercase().contains("capture magic")
                    {
                        pending.push((*filename).clone());
                    }
                    failures.insert((*filename).clone(), message);
                }
            }
        }
        if accepted.len() > 1 {
            return Err(anyhow!(
                "ambiguous captures: {}",
                accepted
                    .iter()
                    .map(|v| v.0.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
        if accepted.len() == 1 && pending.is_empty() {
            let (filename, dir, stamp, reports) = accepted.pop().unwrap();
            let path = Path::new(&filename);
            let archive = a.output.as_ref().unwrap().join(&stamp.2);
            fs::create_dir_all(&archive)?;
            let target = archive.join(
                path.file_name()
                    .ok_or_else(|| anyhow!("invalid capture path"))?,
            );
            fs::copy(path, &target)?;
            if dir.is_dir() {
                for item in walkdir::WalkDir::new(&dir).min_depth(1) {
                    let item = item?;
                    let dest = archive.join(item.path().strip_prefix(&dir)?);
                    if item.file_type().is_dir() {
                        fs::create_dir_all(dest)?;
                    } else if item.file_type().is_file() {
                        fs::copy(item.path(), dest)?;
                    }
                }
            }
            if digest(&target)? != stamp.2 {
                return Err(anyhow!("archive integrity failure"));
            }
            let acceptance = json!({"workload":"complete","profiler":"accepted","source":filename,"sha256":stamp.2,"reports":reports});
            let mut output = fs::File::create(archive.join("acceptance.json"))?;
            serde_json::to_writer_pretty(&mut output, &acceptance)?;
            writeln!(output)?;
            let reports: Vec<Report> = serde_json::from_value(acceptance["reports"].clone())?;
            render(&reports);
            println!("CAPTURE|accepted|archive={}", archive.display());
            return Ok(0);
        }
        if Instant::now() >= deadline {
            let detail = failures
                .iter()
                .map(|(p, e)| {
                    format!(
                        "{}: {e}",
                        Path::new(p)
                            .file_name()
                            .unwrap_or_default()
                            .to_string_lossy()
                    )
                })
                .collect::<Vec<_>>()
                .join("; ");
            return Err(anyhow!(
                "capture awaiting review{}{}",
                if pending.is_empty() {
                    String::new()
                } else {
                    format!("; incomplete writes: {}", pending.join(", "))
                },
                if detail.is_empty() {
                    "; no matching new capture".into()
                } else {
                    format!("; {detail}")
                }
            ));
        }
        std::thread::sleep(
            deadline
                .saturating_duration_since(Instant::now())
                .min(Duration::from_millis(250)),
        );
    }
}

const HARNESS: &str = r#"-- luau_hotspot harness: run through execute_luau in play mode; the console
-- echo between the sentinels is the raw JSON capture. GATE5-clean: no Source
-- writes, no script construction.
local SPS = game:GetService("ScriptProfilerService")
local captured = nil
local connection
connection = SPS.OnNewData:Connect(function(player, jsonString)
	captured = jsonString
end)
SPS:{start}({frequency})
task.wait({seconds})
SPS:{stop}()
SPS:{request}()
local deadline = os.clock() + 5
while captured == nil and os.clock() < deadline do
	task.wait(0.1)
end
connection:Disconnect()
if captured == nil then
	print("<<HOTSPOT-NONE {side} - no data returned; is play mode running?>>")
else
	print("<<HOTSPOT {side}")
	print(captured)
	print("HOTSPOT>>")
end
"#;
#[derive(Default)]
struct HotEntry {
    self_time: f64,
    total: f64,
    caller: Option<i64>,
}
fn walk_hotspot(
    index: i64,
    fid: Option<i64>,
    caller: Option<i64>,
    nodes: &[Value],
    seen: &mut HashSet<i64>,
    agg: &mut BTreeMap<i64, HotEntry>,
) -> f64 {
    if index < 1 || index as usize > nodes.len() || !seen.insert(index) {
        return 0.0;
    }
    let node = &nodes[index as usize - 1];
    let total = node["TotalDuration"].as_f64().unwrap_or(0.0);
    let mut child_total = 0.0;
    if let (Some(fids), Some(nids)) = (node["FunctionIds"].as_array(), node["NodeIds"].as_array()) {
        for (f, n) in fids.iter().zip(nids) {
            if let (Some(f), Some(n)) = (f.as_i64(), n.as_i64()) {
                child_total += walk_hotspot(n, Some(f), fid, nodes, seen, agg);
            }
        }
    }
    if let Some(fid) = fid {
        let entry = agg.entry(fid).or_default();
        entry.self_time += (total - child_total).max(0.0);
        entry.total += total;
        if entry.caller.is_none() {
            entry.caller = caller;
        }
    }
    seen.remove(&index);
    total
}
fn elide(source: &str) -> String {
    let root = std::env::current_dir().unwrap_or_default();
    let path = Path::new(source);
    let absolute = if path.is_absolute() {
        path.to_owned()
    } else {
        root.join(path)
    };
    let mut path_parts = Vec::new();
    for part in absolute.components() {
        use std::path::Component;
        match part {
            Component::ParentDir => {
                path_parts.pop();
            }
            Component::Normal(s) => path_parts.push(s.to_string_lossy().into_owned()),
            _ => {}
        }
    }
    let root_parts: Vec<String> = root
        .components()
        .filter_map(|c| {
            if let std::path::Component::Normal(s) = c {
                Some(s.to_string_lossy().into_owned())
            } else {
                None
            }
        })
        .collect();
    let common = root_parts
        .iter()
        .zip(&path_parts)
        .take_while(|(a, b)| a == b)
        .count();
    let mut parts: Vec<String> = vec!["..".into(); root_parts.len() - common];
    parts.extend_from_slice(&path_parts[common..]);
    if parts.first().is_some_and(|p| p == "places") && parts.len() >= 2 {
        parts.remove(0);
    }
    if parts.len() <= 4 {
        return parts.join("/");
    }
    let skip = parts.len() - 4;
    format!(
        "{}/{}/{}/{}/{}",
        parts[0],
        ".".repeat(skip),
        parts[parts.len() - 3],
        parts[parts.len() - 2],
        parts[parts.len() - 1]
    )
}
fn fn_name(fid: i64, functions: &[Value]) -> (String, String, String) {
    if fid < 1 || fid as usize > functions.len() {
        return (format!("anonymous#{fid}"), "void".into(), "void".into());
    }
    let f = &functions[fid as usize - 1];
    let name = f["Name"]
        .as_str()
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| format!("anonymous#{fid}"));
    let mut site = "void".to_owned();
    if truthy(&f["Source"]) {
        let s = repr(&f["Source"]);
        site = if s.contains('/') { elide(&s) } else { s };
        if truthy(&f["Line"]) {
            site.push(':');
            site.push_str(&repr(&f["Line"]));
        }
    }
    let bits = f["Flags"].as_i64().unwrap_or(0);
    let mut flags = Vec::new();
    if bits & 1 != 0 {
        flags.push("native")
    }
    if bits & 2 != 0 {
        flags.push("plugin")
    }
    (
        name,
        site,
        if flags.is_empty() {
            "void".into()
        } else {
            flags.join(",")
        },
    )
}
fn hotspot_file(path: &str) -> Result<i32> {
    let text = fs::read_to_string(path)?;
    let Some(start) = text.find('{') else {
        return Ok(env_failure(
            "capture-unparseable",
            format!("{path} holds no JSON object"),
        ));
    };
    let Some(end) = text.rfind('}') else {
        return Ok(env_failure(
            "capture-unparseable",
            format!("{path} holds no JSON object"),
        ));
    };
    if end < start {
        return Ok(env_failure(
            "capture-unparseable",
            format!("{path} holds no JSON object"),
        ));
    }
    let data: Value = match serde_json::from_str(&text[start..=end]) {
        Ok(v) => v,
        Err(e) => return Ok(env_failure("capture-unparseable", e)),
    };
    if data["Version"].as_i64() != Some(2) {
        return Ok(env_failure(
            "schema-version",
            format!(
                "expected Version 2, got {} - refusing to parse fiction",
                repr(&data["Version"])
            ),
        ));
    }
    let empty = Vec::new();
    let functions = data["Functions"].as_array().unwrap_or(&empty);
    let nodes = data["Nodes"].as_array().unwrap_or(&empty);
    let categories = data["Categories"].as_array().unwrap_or(&empty);
    let mut agg = BTreeMap::new();
    for cat in categories {
        if let Some(id) = cat["NodeId"].as_i64() {
            walk_hotspot(id, None, None, nodes, &mut HashSet::new(), &mut agg);
        }
    }
    let mut rows = Vec::new();
    let mut plugin = 0.0;
    for (fid, entry) in agg {
        let (name, site, flags) = fn_name(fid, functions);
        if flags.contains("plugin") {
            plugin += entry.self_time;
            continue;
        }
        let caller = entry
            .caller
            .map(|id| fn_name(id, functions).0)
            .unwrap_or_else(|| "void".into());
        rows.push((
            entry.self_time / 1000.0,
            entry.total / 1000.0,
            name,
            site,
            caller,
            flags,
        ));
    }
    rows.sort_by(|a, b| b.0.total_cmp(&a.0));
    let duration = (data["SessionEndTime"].as_i64().unwrap_or(0)
        - data["SessionStartTime"].as_i64().unwrap_or(0))
    .max(0);
    let label = Path::new(path)
        .file_name()
        .unwrap_or_default()
        .to_string_lossy();
    let label = label.strip_suffix(".json").unwrap_or(&label);
    println!(
        "luau_hotspot: MEASURED {label} {duration}ms {} samples {:.0}ms plugin excluded\n",
        nodes.len(),
        plugin / 1000.0
    );
    for (self_ms, total, name, site, caller, flags) in rows.iter().take(25) {
        println!("{name}|{self_ms:.1}|{total:.1}|{site}|{caller}|{flags}");
    }
    Ok(0)
}
fn hotspot(args: &[OsString]) -> Result<i32> {
    let a: Vec<String> = args
        .iter()
        .map(|s| s.to_string_lossy().into_owned())
        .collect();
    if a.first().is_some_and(|s| s == "--emit-harness") {
        let side = a.get(1).map(String::as_str).unwrap_or("server");
        let mut seconds = 3.0_f64;
        let mut frequency = 1000_i64;
        for pair in a.windows(2) {
            if pair[0] == "--seconds" {
                seconds = pair[1].parse()?;
            }
            if pair[0] == "--frequency" {
                frequency = pair[1].parse::<i64>()?.clamp(1, 10000);
            }
        }
        let sides: Vec<&str> = if side == "both" {
            vec!["server", "client"]
        } else {
            vec![side]
        };
        for side in sides {
            let server = side == "server";
            let mut body = HARNESS
                .replace(
                    "{start}",
                    if server { "ServerStart" } else { "ClientStart" },
                )
                .replace("{stop}", if server { "ServerStop" } else { "ClientStop" })
                .replace(
                    "{request}",
                    if server {
                        "ServerRequestData"
                    } else {
                        "ClientRequestData"
                    },
                )
                .replace("{frequency}", &frequency.to_string())
                .replace("{seconds}", &format!("{seconds:?}"))
                .replace("{side}", side);
            if !server {
                body = body
                    .replace(
                        "SPS:ClientStart(",
                        "SPS:ClientStart(game:GetService(\"Players\"):GetPlayers()[1], ",
                    )
                    .replace(
                        "SPS:ClientStop()",
                        "SPS:ClientStop(game:GetService(\"Players\"):GetPlayers()[1])",
                    )
                    .replace(
                        "SPS:ClientRequestData()",
                        "SPS:ClientRequestData(game:GetService(\"Players\"):GetPlayers()[1])",
                    );
            }
            println!("{body}");
        }
        return Ok(0);
    }
    if a.first().is_some_and(|s| s == "--from-json") {
        let mut code = 0;
        for p in a.iter().skip(1).filter(|p| !p.starts_with("--")) {
            code = code.max(hotspot_file(p)?);
        }
        return Ok(code);
    }
    println!("luau_hotspot — samples Luau call stacks through ScriptProfilerService.\n\n  luau_hotspot --emit-harness server|client|both [--seconds N] [--frequency HZ]\n  luau_hotspot --from-json FILE [FILE...]");
    Ok(if a.is_empty() { 0 } else { 2 })
}
pub fn run(args: &[OsString]) -> Result<i32> {
    let Some((family, rest)) = args.split_first() else {
        return Err(anyhow!("profile requires capture, frames, luau or results"));
    };
    let family = family.to_string_lossy();
    match family.as_ref() {
        "capture" => {
            let mut a = vec![OsString::from("profile capture")];
            a.extend_from_slice(rest);
            match CaptureArgs::try_parse_from(a) {
                Ok(a) => match capture(a) {
                    Ok(c) => Ok(c),
                    Err(e) => {
                        println!("CAPTURE|awaiting-review|{e}");
                        Ok(2)
                    }
                },
                Err(e) => {
                    let c = if e.use_stderr() { 2 } else { 0 };
                    e.print()?;
                    Ok(c)
                }
            }
        }
        "frames" => {
            let mut a = vec![OsString::from("profile frames")];
            a.extend_from_slice(rest);
            match FramesArgs::try_parse_from(a) {
                Ok(a) => match frames(a) {
                    Ok(c) => Ok(c),
                    Err(e) => {
                        println!("PROFILE|rejected|{e}");
                        Ok(2)
                    }
                },
                Err(e) => {
                    let c = if e.use_stderr() { 2 } else { 0 };
                    e.print()?;
                    Ok(c)
                }
            }
        }
        "luau" => match hotspot(rest) {
            Ok(c) => Ok(c),
            Err(e) => {
                eprintln!("luau_hotspot: CRASH {e} - nothing was analyzed");
                Ok(2)
            }
        },
        "results" => crate::buffer::run(rest),
        _ => Err(anyhow!("unknown profile command '{family}'")),
    }
}

pub const EXCLUDED_IDLE: &[&str] = &[
    "Sleep",
    "waitOnGpu",
    "waitUntilCompleted",
    "waitUntilEmpty",
    "acquireFramebuffer",
];
pub const DIAGNOSTIC_WAITS: &[(&str, &str)] = &[
    (
        "waitOnGpu",
        "gpu-bound - reduce draw calls, texture size, shadows, overdraw",
    ),
    (
        "waitUntilCompleted",
        "gpu-bound - reduce draw calls, texture size, shadows, overdraw",
    ),
    (
        "Wait for Render Thread",
        "main serialized behind render - check what Main feeds Render per frame",
    ),
    (
        "WaitingHybridScriptJob",
        "script-resume budget saturated - too many waiting or long-running scripts",
    ),
    (
        "LegacyLock",
        "stop-the-world serialization - report high values",
    ),
    ("Write Marshalled", "DataModel lock contention"),
    ("Read Marshalled", "DataModel lock contention"),
];
pub const CONTAINERS: &[&str] = &[
    "runJob",
    "Worker::runJob",
    "Thread (FG)",
    "Thread (BG)",
    "TS::JobStep",
    "TS::ArbiterStep",
    "TS::Step",
    "parallelFor",
    "UpdateView",
    "PreRender",
    "deferredThreads",
    "Heartbeat",
    "Stepped",
    "RenderStepped",
    "Render",
    "Simulation",
    "frame",
];
pub const WORKER_CLASS: &[&str] = &["VisibleQuery", "CullJob", "Parallel FastClusters"];
pub const DOLLAR_FAMILIES: &[&str] = &["$Script", "$newindex", "$index", "$namecall", "$call"];
pub fn scope_lookup(scope: &str) -> (&'static str, &'static str, &'static str) {
    const ROWS: &[(&str, &str, &str, &str)] = &[
        (
            "updateInvalidatedFastClusters",
            "Simulation",
            "avatar/MeshPart churn >4ms",
            "reduce per-frame avatar and MeshPart mutation",
        ),
        (
            "stepWorldThrottled",
            "Simulation",
            "physics throttling engaged",
            "watched qualitatively - reduce simulated assemblies",
        ),
        (
            "updateBroadphase",
            "Simulation",
            "collision broadphase load",
            "fewer moving assemblies, simpler collision",
        ),
        (
            "worldStep",
            "Simulation",
            "physics step",
            "reduce assemblies, anchor static parts",
        ),
        (
            "preContactStepSleepStage",
            "Simulation",
            "touch sleep determination",
            "advice|void",
        ),
        (
            "computeLightingPerform",
            "Render",
            "lighting recompute every client frame",
            "reduce dynamic lights and shadow casters",
        ),
        (
            "Pass3dAdorn",
            "Render",
            "3D world GUI (Billboard/Surface/Humanoid labels)",
            "fewer BillboardGuis and name labels in view",
        ),
        (
            "Prepare",
            "Render",
            "scene prep exceeding budget",
            "reduce instance churn reaching the render thread",
        ),
        (
            "Perform",
            "Render",
            "draw submission",
            "reduce draw calls and material variety",
        ),
        (
            "Present",
            "Render",
            "swap wait",
            "gpu-bound when waitUntilCompleted dominates",
        ),
        (
            "ShadowsRender",
            "Render",
            "shadow map cost",
            "CastShadow=false on filler geometry",
        ),
        (
            "UI,Layout",
            "UI",
            "relayout storm from a LayerCollector",
            "batch GUI property writes; cache text bounds",
        ),
        (
            "Layout",
            "UI",
            "relayout storm from a LayerCollector",
            "batch GUI property writes; cache text bounds",
        ),
        (
            "newindex_CFrame",
            "LuaBridge",
            "per-instance CFrame writes",
            "batch into one workspace:BulkMoveTo",
        ),
        (
            "newindex",
            "LuaBridge",
            "property write volume",
            "batch writes; cache instance references",
        ),
        (
            "index",
            "LuaBridge",
            "property read volume",
            "cache reads in locals outside loops",
        ),
        (
            "namecall",
            "LuaBridge",
            "method call volume",
            "hoist repeated calls; cache results",
        ),
        (
            "Script",
            "Scripts",
            "script CPU",
            "luau_hotspot names the function; OPT1's ladder",
        ),
        (
            "deferredThreads",
            "Scripts",
            "deferred signal resumption",
            "attribute to the scripts inside, never the wrapper",
        ),
        (
            "WaitingHybridScriptJob",
            "Scripts",
            "script-resume budget saturated",
            "fewer waiting scripts; shorter resumes",
        ),
        (
            "RunService.Heartbeat",
            "Scripts",
            "per-frame connections",
            "profile labels per OPT20; batch work",
        ),
        (
            "GC",
            "Engine",
            "garbage collection pressure",
            "reduce per-frame allocation; reuse tables and buffers",
        ),
        (
            "Net",
            "Network",
            "replication volume",
            "incremental replication per BC2; smaller payloads",
        ),
        (
            "Replicator",
            "Network",
            "replication packet processing",
            "fewer changing instances; batch state",
        ),
    ];
    ROWS.iter()
        .find(|r| scope.starts_with(r.0))
        .map(|r| (r.1, r.2, r.3))
        .unwrap_or(("void", "advice", "void"))
}
