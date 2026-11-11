use anyhow::{anyhow, bail, Result};
use clap::Parser;
use num_bigint::BigInt;
use num_rational::BigRational;
use num_traits::{One, Signed, ToPrimitive, Zero};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::{BTreeMap, HashMap},
    ffi::OsString,
    fs,
    path::PathBuf,
};

pub const LIMIT: usize = 65536;
pub const CHUNK: usize = 512;
const MAX_INTEGER: u64 = (1u64 << 53) - 1;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Metric {
    pub method: String,
    pub workload: String,
    pub kind: String,
    pub count: u64,
    pub total_us: u64,
    pub max_us: u64,
    pub threshold_us: u64,
    pub spike_count: u64,
    pub overflow: u64,
    pub window_us: u64,
    pub spikes: Vec<(u64, u64)>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BufferResult {
    pub id: String,
    pub status: String,
    pub passed: u64,
    pub failed: u64,
    pub skipped: u64,
    pub reason: String,
    pub metrics: Vec<Metric>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Record {
    pub side: String,
    pub script: String,
    pub run: String,
    pub result: BufferResult,
}

fn token(s: &str) -> Result<&str> {
    if s.is_empty()
        || s.len() > 96
        || !s
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_.:/-".contains(&b))
    {
        bail!("invalid identity")
    }
    Ok(s)
}
fn integer(s: &str, min: u64) -> Result<u64> {
    if s.is_empty() || (s.len() > 1 && s.starts_with('0')) || !s.bytes().all(|b| b.is_ascii_digit())
    {
        bail!("invalid integer")
    }
    let n = s
        .parse::<u64>()
        .map_err(|_| anyhow!("integer out of range"))?;
    if n < min || n > MAX_INTEGER {
        bail!("integer out of range")
    }
    Ok(n)
}
fn reason(s: &str) -> Result<&str> {
    if s.len() > 160 || !s.bytes().all(|b| (32..=126).contains(&b) && b != b'|') {
        bail!("invalid reason")
    }
    Ok(s)
}

pub fn decode(raw: &[u8]) -> Result<BufferResult> {
    if raw.is_empty() || raw.len() > LIMIT {
        bail!("payload limit")
    }
    if let Some((i, b)) = raw.iter().enumerate().find(|(_, b)| !b.is_ascii()) {
        bail!(
            "'ascii' codec can't decode byte 0x{b:02x} in position {i}: ordinal not in range(128)"
        )
    }
    let text = std::str::from_utf8(raw)?;
    let mut rows = Vec::new();
    let mut previous_cr = false;
    let mut start = 0;
    for (i, c) in text.char_indices() {
        if matches!(c, '\n' | '\r' | '\x0b' | '\x0c' | '\x1c' | '\x1d' | '\x1e') {
            if c == '\n' && previous_cr {
                start = i + 1;
                previous_cr = false;
                continue;
            }
            rows.push(&text[start..i]);
            start = i + 1;
            previous_cr = c == '\r';
        } else {
            previous_cr = false;
        }
    }
    if start < text.len() {
        rows.push(&text[start..]);
    }
    if !text.ends_with('\n') || rows.first() != Some(&"HTB1") {
        bail!("unsupported or truncated buffer")
    }
    if rows.len() < 2 {
        bail!("missing result")
    }
    let r: Vec<_> = rows[1].split('\t').collect();
    if r.len() != 7
        || r[0] != "R"
        || !["pass", "fail", "cancelled", "timeout", "unrun"].contains(&r[2])
    {
        bail!("invalid result")
    }
    let mut result = BufferResult {
        id: token(r[1])?.into(),
        status: r[2].into(),
        passed: integer(r[3], 0)?,
        failed: integer(r[4], 0)?,
        skipped: integer(r[5], 0)?,
        reason: reason(r[6])?.into(),
        metrics: Vec::new(),
    };
    if result.status == "pass" && (result.failed != 0 || result.passed == 0) {
        bail!("empty or failed pass")
    }
    if result.status != "pass" && result.reason == "-" {
        bail!("missing failure reason")
    }
    let mut groups: HashMap<(String, String, String), usize> = HashMap::new();
    for line in &rows[2..] {
        let r: Vec<_> = line.split('\t').collect();
        if r[0] == "M" && r.len() == 11 {
            let method = token(r[1])?;
            let workload = token(r[2])?;
            let kind = r[3];
            let key = (method.to_owned(), workload.to_owned(), kind.to_owned());
            if !["script", "scheduling", "setup", "teardown"].contains(&kind)
                || groups.contains_key(&key)
                || groups.len() >= 32
            {
                bail!("conflicting metric")
            }
            let n: Vec<u64> = r[4..]
                .iter()
                .map(|v| integer(v, 0))
                .collect::<Result<_>>()?;
            let (count, total, max, threshold, spikes, overflow, window) =
                (n[0], n[1], n[2], n[3], n[4], n[5], n[6]);
            let (c, t, m, h, s) = (
                count as u128,
                total as u128,
                max as u128,
                threshold as u128,
                spikes as u128,
            );
            if count == 0
                || threshold == 0
                || max > total
                || t > m * c
                || spikes > count
                || overflow > spikes
            {
                bail!("invalid metric totals")
            }
            if (max > threshold) != (spikes > 0)
                || (spikes > 0 && t < m + (s - 1) * (h + 1))
                || t > s * m + (c - s) * m.min(h)
            {
                bail!("inconsistent spike totals")
            }
            groups.insert(key, result.metrics.len());
            result.metrics.push(Metric {
                method: method.into(),
                workload: workload.into(),
                kind: kind.into(),
                count,
                total_us: total,
                max_us: max,
                threshold_us: threshold,
                spike_count: spikes,
                overflow,
                window_us: window,
                spikes: Vec::new(),
            });
        } else if r[0] == "P" && r.len() == 6 {
            let key = (r[1].to_owned(), r[2].to_owned(), r[3].to_owned());
            let idx = *groups
                .get(&key)
                .ok_or_else(|| anyhow!("spike before metric"))?;
            let g = &mut result.metrics[idx];
            let index = integer(r[4], 1)?;
            let duration = integer(r[5], 0)?;
            if index > g.count
                || duration <= g.threshold_us
                || duration > g.max_us
                || g.spikes.iter().any(|p| p.0 == index)
            {
                bail!("invalid spike")
            }
            g.spikes.push((index, duration));
            if g.spikes.len() > 256 {
                bail!("spike storage limit")
            }
        } else {
            bail!("unsupported payload row")
        }
    }
    for g in &result.metrics {
        if g.spikes.iter().map(|p| p.1 as u128).sum::<u128>() > g.total_us as u128 {
            bail!("spike durations exceed total")
        }
        if g.spikes.len() as u64 + g.overflow != g.spike_count {
            bail!("incomplete spikes")
        }
    }
    Ok(result)
}
fn adler32(data: &[u8]) -> u32 {
    let (mut a, mut b) = (1u32, 0u32);
    for &v in data {
        a = (a + v as u32) % 65521;
        b = (b + a) % 65521;
    }
    (b << 16) | a
}
fn checksum(side: &str, script: &str, run: &str, raw: &[u8]) -> u32 {
    let mut v = format!("{side}|{script}|{run}\0").into_bytes();
    v.extend_from_slice(raw);
    adler32(&v)
}
pub fn encode_records(raw: &[u8], side: &str, script: &str, run: &str) -> Result<Vec<String>> {
    decode(raw)?;
    if side != "SERVER" && side != "CLIENT" {
        bail!("invalid side")
    }
    token(script)?;
    token(run)?;
    let sum = checksum(side, script, run, raw);
    let count = raw.len().div_ceil(CHUNK);
    Ok(raw
        .chunks(CHUNK)
        .enumerate()
        .map(|(i, c)| {
            format!(
                "{side}|{script}|BUF|1|{run}|{}|{count}|{}|{sum:08x}|{}",
                i + 1,
                raw.len(),
                hex::encode(c)
            )
        })
        .collect())
}
#[derive(Clone)]
struct Group {
    side: String,
    script: String,
    run: String,
    count: usize,
    size: usize,
    checksum: String,
    chunks: BTreeMap<usize, Vec<u8>>,
}
pub struct Collector {
    expected: Option<(String, String, String)>,
    groups: Vec<Group>,
    pub errors: Vec<String>,
}
impl Collector {
    pub fn new(expected: Option<(String, String, String)>) -> Self {
        Self {
            expected,
            groups: Vec::new(),
            errors: Vec::new(),
        }
    }
    pub fn feed(&mut self, console: &str) {
        let re = Regex::new(r"(SERVER|CLIENT)\|([^|\s]+)\|BUF\|([^\s]+)").unwrap();
        for line in console.lines() {
            if let Some(c) = re.captures(line) {
                let (side, script, body) = (&c[1], &c[2], &c[3]);
                let outcome = (|| -> Result<()> {
                    let f: Vec<_> = body.split('|').collect();
                    if f.len() != 7 {
                        bail!("truncated transport")
                    }
                    let (version, run) = (f[0], f[1]);
                    if let Some((expected_side, expected_script, expected_run)) = &self.expected {
                        if script != expected_script || run != expected_run {
                            return Ok(());
                        }
                        if side != expected_side {
                            bail!("incorrect runtime prefix")
                        }
                    }
                    if version != "1" {
                        bail!("unsupported transport")
                    }
                    token(script)?;
                    token(run)?;
                    let seq = integer(f[2], 1)? as usize;
                    let count = integer(f[3], 1)? as usize;
                    let size = integer(f[4], 1)? as usize;
                    if size > LIMIT || count != size.div_ceil(CHUNK) || seq > count {
                        bail!("invalid chunk bounds")
                    }
                    let lower_hex = |s: &str| {
                        s.bytes()
                            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                    };
                    if f[5].len() != 8
                        || !lower_hex(f[5])
                        || f[6].is_empty()
                        || f[6].len() > CHUNK * 2
                        || f[6].len() % 2 != 0
                        || !lower_hex(f[6])
                    {
                        bail!("invalid transport encoding")
                    }
                    let chunk = hex::decode(f[6])?;
                    if chunk.len() != CHUNK.min(size - (seq - 1) * CHUNK) {
                        bail!("truncated chunk")
                    }
                    let pos = self
                        .groups
                        .iter()
                        .position(|g| g.side == side && g.script == script && g.run == run);
                    let idx = match pos {
                        Some(i) => i,
                        None => {
                            if self.groups.len() >= 64 {
                                bail!("record limit")
                            }
                            self.groups.push(Group {
                                side: side.into(),
                                script: script.into(),
                                run: run.into(),
                                count,
                                size,
                                checksum: f[5].into(),
                                chunks: BTreeMap::new(),
                            });
                            self.groups.len() - 1
                        }
                    };
                    let g = &mut self.groups[idx];
                    if (g.count, g.size, g.checksum.as_str()) != (count, size, f[5])
                        || g.chunks.get(&seq).is_some_and(|v| v != &chunk)
                    {
                        bail!("conflicting transport")
                    }
                    g.chunks.insert(seq, chunk);
                    Ok(())
                })();
                if let Err(e) = outcome {
                    let e = e.to_string();
                    if !self.errors.contains(&e) && self.errors.len() < 20 {
                        self.errors.push(e)
                    }
                }
            } else if line.contains("|BUF|")
                && !self
                    .errors
                    .iter()
                    .any(|e| e == "malformed transport record")
                && self.errors.len() < 20
            {
                self.errors.push("malformed transport record".into())
            }
        }
    }
    pub fn finish(&self) -> Result<Vec<Record>> {
        if !self.errors.is_empty() {
            bail!("{}", self.errors.join("; "))
        }
        if self.groups.is_empty() {
            bail!("missing output")
        }
        let mut out = Vec::new();
        for g in &self.groups {
            if g.chunks.len() != g.count {
                bail!("incomplete buffer")
            }
            let mut raw = Vec::with_capacity(g.size);
            for i in 1..=g.count {
                raw.extend_from_slice(
                    g.chunks
                        .get(&i)
                        .ok_or_else(|| anyhow!("incomplete buffer"))?,
                )
            }
            if raw.len() != g.size
                || format!("{:08x}", checksum(&g.side, &g.script, &g.run, &raw)) != g.checksum
            {
                bail!("buffer integrity failure")
            }
            out.push(Record {
                side: g.side.clone(),
                script: g.script.clone(),
                run: g.run.clone(),
                result: decode(&raw)?,
            });
        }
        Ok(out)
    }
}
pub fn summary(records: &[Record]) -> String {
    let mut out = Vec::new();
    for r in records {
        let p = format!("{}|{}|", r.side, r.script);
        let v = &r.result;
        out.push(format!(
            "{p}{}|{}|passed={} failed={} skipped={}{}",
            v.id,
            v.status,
            v.passed,
            v.failed,
            v.skipped,
            if v.reason != "-" {
                format!("|{}", v.reason)
            } else {
                String::new()
            }
        ));
        for m in &v.metrics {
            out.push(format!("{p}{}/{}|{}|average={:.3}ms|count={}|window={:.3}ms|spikes={} max={:.3}ms overflow={}",m.method,m.workload,m.kind,m.total_us as f64/m.count as f64/1000.0,m.count,m.window_us as f64/1000.0,m.spike_count,m.max_us as f64/1000.0,m.overflow));
        }
    }
    out.join("\n")
}
fn avg(m: &Metric) -> BigRational {
    BigRational::new(BigInt::from(m.total_us), BigInt::from(m.count))
}
fn f(v: &BigRational) -> f64 {
    v.to_f64().unwrap_or(if v.is_negative() {
        f64::NEG_INFINITY
    } else {
        f64::INFINITY
    })
}
pub fn compare(records: &[Record], baseline: &str, candidate: &str) -> Result<String> {
    token(baseline)?;
    token(candidate)?;
    if baseline == candidate {
        bail!("comparison methods must differ")
    }
    let mut out = Vec::new();
    for r in records {
        let v = &r.result;
        if v.status != "pass" || v.failed != 0 || v.skipped != 0 {
            bail!("comparison requires complete passing results")
        }
        let before: BTreeMap<_, _> = v
            .metrics
            .iter()
            .filter(|m| m.method == baseline)
            .map(|m| ((m.workload.as_str(), m.kind.as_str()), m))
            .collect();
        let after: BTreeMap<_, _> = v
            .metrics
            .iter()
            .filter(|m| m.method == candidate)
            .map(|m| ((m.workload.as_str(), m.kind.as_str()), m))
            .collect();
        if before.is_empty() || !before.keys().eq(after.keys()) {
            bail!("comparison requires matching workload/kind groups")
        }
        for (k, b) in &before {
            let a = after[k];
            if (a.count, a.threshold_us) != (b.count, b.threshold_us) {
                bail!("comparison count/threshold mismatch")
            }
        }
        let p = format!("{}|{}|COMPARE|{baseline}/{candidate}|", r.side, r.script);
        for ((workload, kind), b) in &before {
            let a = after[&(*workload, *kind)];
            let base = avg(b);
            let change = avg(a) - &base;
            let percent = if base.is_zero() {
                "NA".to_string()
            } else {
                format!("{:+.3}", f(&(&change / &base * BigInt::from(100))))
            };
            out.push(format!("{p}{workload}/{kind}|base_us={:.3}|candidate_us={:.3}|delta_us={:+.3}|delta_percent={percent}|max_delta_us={:+}|spike_delta={:+}",f(&base),a.total_us as f64/a.count as f64,f(&change),a.max_us as i64-b.max_us as i64,a.spike_count as i64-b.spike_count as i64));
        }
        let workloads: std::collections::BTreeSet<_> = before.keys().map(|(w, _)| *w).collect();
        for workload in workloads {
            if !["setup", "script", "teardown"]
                .iter()
                .all(|k| before.contains_key(&(workload, *k)))
            {
                out.push(format!("{p}{workload}|timing-model=unavailable|Require paired setup/script/teardown and production reuse"));
                continue;
            }
            let delta = |kind| avg(after[&(workload, kind)]) - avg(before[&(workload, kind)]);
            let fixed = delta("setup") + delta("teardown");
            let per = delta("script");
            let crossover = if per.is_negative() {
                let x = &fixed / (-&per);
                let mut n = x.numer() / x.denom();
                if x.is_positive() && x.numer() % x.denom() != BigInt::zero() {
                    n += 1
                }
                n.max(BigInt::one()).to_string()
            } else if per.is_zero() && !fixed.is_positive() {
                "1".into()
            } else {
                "none".into()
            };
            out.push(format!("{p}{workload}|timing-model=conditional-estimate|fixed_delta_us={:+.3}|per_use_delta_us={:+.3}|late_break_even_uses={crossover}|Require one-time setup/teardown and equal work per script sample; CPU claims also require non-yielding regions",f(&fixed),f(&per)));
        }
    }
    if out.is_empty() {
        bail!("missing comparison results")
    }
    out.push("COMPARE|limits|Timing arithmetic only; require equivalent results or accepted error, comparable data/environment/batching, production frequency/reuse, memory/GC, bytes, and actual consuming-path evidence before selecting a representation".into());
    Ok(out.join("\n"))
}

pub fn historical(text: &str) -> Result<Vec<Value>> {
    let stripped = text.trim();
    let rows: Vec<Value> = if stripped.starts_with('{') {
        vec![serde_json::from_str(stripped)?]
    } else {
        text.lines()
            .filter_map(|line| line.split_once("TEST|").map(|(_, v)| v))
            .map(|v| serde_json::from_str(v).map_err(Into::into))
            .collect::<Result<_>>()?
    };
    if rows.len() > 64 {
        bail!("historical result limit")
    }
    for value in &rows {
        let obj = value
            .as_object()
            .ok_or_else(|| anyhow!("unsupported historical result"))?;
        let status = obj.get("status").and_then(Value::as_str).unwrap_or("");
        if !["pass", "fail", "unrun"].contains(&status) {
            bail!("unsupported historical result")
        }
        let mut counts = [0u64; 3];
        for (i, key) in ["passed", "failed", "skipped"].iter().enumerate() {
            let v = obj.get(*key).ok_or_else(|| anyhow!("'{key}'"))?;
            let s = match v {
                Value::String(s) => s.clone(),
                _ => v.to_string(),
            };
            counts[i] = integer(&s, 0)?;
        }
        if status == "pass" && (counts[0] == 0 || counts[1] != 0) {
            bail!("invalid historical pass")
        }
    }
    if rows.is_empty() {
        bail!("missing historical results")
    }
    Ok(rows)
}

#[derive(Parser)]
#[command(about = "HTB1 buffer transport. Shared by test, debug and optimization collection.")]
struct Args {
    input: PathBuf,
    #[arg(long, value_parser=["SERVER","CLIENT"])]
    side: Option<String>,
    #[arg(long)]
    script: Option<String>,
    #[arg(long)]
    run: Option<String>,
    #[arg(long)]
    historical: bool,
    #[arg(long, num_args=2, value_names=["BASE","CANDIDATE"])]
    compare: Option<Vec<String>>,
}
pub fn run(args: &[OsString]) -> Result<i32> {
    let mut argv = vec![OsString::from("decode")];
    argv.extend_from_slice(args);
    let a = match Args::try_parse_from(argv) {
        Ok(a) => a,
        Err(e) => {
            let code = if e.use_stderr() { 2 } else { 0 };
            e.print()?;
            return Ok(code);
        }
    };
    let action = (|| -> Result<i32> {
        let text = fs::read_to_string(&a.input)?;
        if a.historical {
            if a.compare.is_some() {
                bail!("historical results do not support paired comparisons")
            }
            let rows = historical(&text)?;
            for r in &rows {
                let repr = |key: &str| match &r[key] {
                    Value::String(s) => s.clone(),
                    v => v.to_string(),
                };
                let suffix = match r.get("reason") {
                    Some(Value::String(s)) if !s.is_empty() => format!("|{}", reason(s)?),
                    _ => String::new(),
                };
                println!(
                    "HISTORICAL|legacy-status={}|passed={} failed={} skipped={}{}",
                    repr("status"),
                    repr("passed"),
                    repr("failed"),
                    repr("skipped"),
                    suffix
                );
            }
            return Ok(if rows.iter().all(|r| r["status"] == "pass") {
                0
            } else {
                2
            });
        }
        let (side, script, run) = match (a.side, a.script, a.run) {
            (Some(s), Some(p), Some(r)) if !s.is_empty() && !p.is_empty() && !r.is_empty() => {
                (s, p, r)
            }
            _ => bail!("side, script and run required"),
        };
        let mut collector = Collector::new(Some((side, script, run)));
        collector.feed(&text);
        let records = collector.finish()?;
        let comparison = match a.compare {
            Some(c) => Some(compare(&records, &c[0], &c[1])?),
            None => None,
        };
        println!("{}", summary(&records));
        if let Some(c) = comparison {
            println!("{c}")
        }
        Ok(if records.iter().all(|r| r.result.status == "pass") {
            0
        } else {
            2
        })
    })();
    match action {
        Ok(code) => Ok(code),
        Err(e) => {
            println!("RESULT|rejected|{e}");
            Ok(2)
        }
    }
}
