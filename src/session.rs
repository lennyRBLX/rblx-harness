use anyhow::{Context, Result};
use chrono::{SecondsFormat, Utc};
use clap::{Arg, Command};
use regex::Regex;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::ffi::OsString;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::sync::LazyLock;
use walkdir::WalkDir;

const METHOD: &str = "Unique outer calls; exec batches count once; first matching category. Visible characters/4 rounded up per call, excluding ciphertext and media. Estimates exclude reasoning, hidden context and repeated cached inputs. Recorded usage is deduplicated by response_id; legacy counters are not added.";
const RULES: &[(&str, &str)] = &[
    (
        "Edits and patch generation",
        r"apply_patch|\.write_text\(|\.write_bytes\(",
    ),
    ("Studio execution", r"execute_luau|studio_rpc|boot_smoke"),
    (
        "Studio output and state",
        r"get_console_output|get_studio_state|list_roblox_studios|screen_capture|inspect_instance|search_game_tree",
    ),
    (
        "API and type evidence",
        r"api_dump\.py|type_lookup\.py|web__run|web\.run",
    ),
    (
        "Validation and build",
        r"run_verify\.py|lint_driver|style_assess|deny_scan|luau-lsp|luau-analyze|\bpytest\b|\bunittest\b|argon (?:build|sourcemap)|project_gate\.py|compileall|py_compile",
    ),
    (
        "Rules and skill retrieval",
        r"(?:cat|sed|read_text|rg)[\s\S]*(?:CORE\.md|SKILL\.md|AGENTS\.md|references/engine\.md)",
    ),
    (
        "Git inspection",
        r"git\s+(?:diff|status|show|log|ls-files|rev-parse)\b",
    ),
    (
        "Source retrieval and search",
        r"\b(?:cat|sed|rg|grep|head|tail)\b|read_text\(|get_symbols_overview|find_symbol",
    ),
    (
        "Agent dispatch and messages",
        r"spawn_agent|send_message|followup_task|interrupt_agent",
    ),
    (
        "Waits and status checks",
        r"wait_agent|list_agents|write_stdin|\bsleep\b|^wait\s",
    ),
];
fn cipher() -> &'static Regex {
    static RE: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r"gAAAAA[A-Za-z0-9_=-]{60,}").unwrap());
    &RE
}
fn visible(v: &Value) -> String {
    match v {
        Value::String(s) => cipher().replace_all(s, "").into_owned(),
        Value::Array(a) => a.iter().map(visible).collect::<Vec<_>>().join("\n"),
        Value::Object(m) => {
            if matches!(
                m.get("type").and_then(Value::as_str),
                Some("encrypted_content" | "image" | "input_image" | "audio")
            ) {
                return String::new();
            }
            m.iter()
                .filter(|(k, _)| !matches!(k.as_str(), "encrypted_content" | "data" | "image_url"))
                .map(|(_, v)| visible(v))
                .collect::<Vec<_>>()
                .join("\n")
        }
        _ => String::new(),
    }
}
fn classify(name: &str, text: &str) -> &'static str {
    static COMPILED: LazyLock<Vec<Regex>> = LazyLock::new(|| {
        RULES
            .iter()
            .map(|(_, r)| Regex::new(&format!("(?i:{r})")).unwrap())
            .collect()
    });
    let re = &*COMPILED;
    let full = format!("{name} {text}");
    RULES
        .iter()
        .zip(re)
        .find(|(_, r)| r.is_match(&full))
        .map(|((label, _), _)| *label)
        .unwrap_or("Other tool work")
}
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().map_or(true, |x| x != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(m) => !m.is_empty(),
    }
}
fn nonprintable(c: char) -> bool {
    static NONPRINTABLE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[\p{C}\p{Z}]$").unwrap());
    c != ' ' && NONPRINTABLE.is_match(c.encode_utf8(&mut [0; 4]))
}
fn ascii_json(s: &str) -> String {
    use std::fmt::Write;
    let mut out = String::new();
    for c in s.chars() {
        if c as u32 >= 127 {
            let mut buf = [0u16; 2];
            for unit in c.encode_utf16(&mut buf) {
                let _ = write!(out, "\\u{:04x}", *unit);
            }
        } else {
            out.push(c);
        }
    }
    out
}
fn py_repr(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => {
            let quote = if s.contains('\'') && !s.contains('"') {
                '"'
            } else {
                '\''
            };
            let mut out = String::new();
            out.push(quote);
            for c in s.chars() {
                match c {
                    '\\' => out.push_str("\\\\"),
                    '\n' => out.push_str("\\n"),
                    '\r' => out.push_str("\\r"),
                    '\t' => out.push_str("\\t"),
                    c if c == quote => {
                        out.push('\\');
                        out.push(c);
                    }
                    c if nonprintable(c) => {
                        use std::fmt::Write;
                        if (c as u32) < 256 {
                            let _ = write!(out, "\\x{:02x}", c as u32);
                        } else if (c as u32) < 65536 {
                            let _ = write!(out, "\\u{:04x}", c as u32);
                        } else {
                            let _ = write!(out, "\\U{:08x}", c as u32);
                        }
                    }
                    c => out.push(c),
                }
            }
            out.push(quote);
            out
        }
        Value::Array(a) => format!("[{}]", a.iter().map(py_repr).collect::<Vec<_>>().join(", ")),
        Value::Object(o) => format!(
            "{{{}}}",
            o.iter()
                .map(|(k, v)| format!("{}: {}", py_repr(&Value::String(k.clone())), py_repr(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}
fn py_str(v: &Value) -> String {
    v.as_str().map(str::to_owned).unwrap_or_else(|| py_repr(v))
}
fn dict_key(v: &Value) -> Result<String> {
    match v {
        Value::String(s) => Ok(format!("s{s}")),
        Value::Bool(b) => Ok(format!("n{}", if *b { 1 } else { 0 })),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(format!("n{i}"))
            } else if let Some(i) = n.as_u64() {
                Ok(format!("n{i}"))
            } else {
                let f = n.as_f64().unwrap();
                if f.fract() == 0.0 && f.abs() < 1e19 {
                    Ok(format!("n{f:.0}"))
                } else {
                    Ok(format!("f{f}"))
                }
            }
        }
        Value::Null => Ok("none".into()),
        _ => anyhow::bail!("unhashable JSON value"),
    }
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn expand(path: &Path) -> PathBuf {
    let s = path.to_string_lossy();
    if s == "~" || s.starts_with("~/") {
        if let Some(home) = dirs::home_dir() {
            return home.join(s.strip_prefix("~/").unwrap_or(""));
        }
    }
    path.to_owned()
}
fn resolve(path: &Path) -> Result<PathBuf> {
    let path = expand(path);
    let path = if path.is_absolute() {
        path
    } else {
        std::env::current_dir()?.join(path)
    };
    let mut result = PathBuf::new();
    for c in path.components() {
        match c {
            Component::ParentDir => {
                result.pop();
            }
            Component::CurDir => {}
            c => {
                result.push(c.as_os_str());
                if let Ok(real) = fs::canonicalize(&result) {
                    result = real;
                }
            }
        }
    }
    Ok(result)
}
fn casefold(s: &str) -> String {
    let mut out = String::new();
    for c in s.chars() {
        match c {
            '\u{b5}' => out.push_str("\u{3bc}"),
            '\u{df}' => out.push_str("\u{73}\u{73}"),
            '\u{149}' => out.push_str("\u{2bc}\u{6e}"),
            '\u{17f}' => out.push_str("\u{73}"),
            '\u{1f0}' => out.push_str("\u{6a}\u{30c}"),
            '\u{345}' => out.push_str("\u{3b9}"),
            '\u{390}' => out.push_str("\u{3b9}\u{308}\u{301}"),
            '\u{3b0}' => out.push_str("\u{3c5}\u{308}\u{301}"),
            '\u{3c2}' => out.push_str("\u{3c3}"),
            '\u{3d0}' => out.push_str("\u{3b2}"),
            '\u{3d1}' => out.push_str("\u{3b8}"),
            '\u{3d5}' => out.push_str("\u{3c6}"),
            '\u{3d6}' => out.push_str("\u{3c0}"),
            '\u{3f0}' => out.push_str("\u{3ba}"),
            '\u{3f1}' => out.push_str("\u{3c1}"),
            '\u{3f5}' => out.push_str("\u{3b5}"),
            '\u{587}' => out.push_str("\u{565}\u{582}"),
            '\u{13f8}' => out.push_str("\u{13f0}"),
            '\u{13f9}' => out.push_str("\u{13f1}"),
            '\u{13fa}' => out.push_str("\u{13f2}"),
            '\u{13fb}' => out.push_str("\u{13f3}"),
            '\u{13fc}' => out.push_str("\u{13f4}"),
            '\u{13fd}' => out.push_str("\u{13f5}"),
            '\u{1c80}' => out.push_str("\u{432}"),
            '\u{1c81}' => out.push_str("\u{434}"),
            '\u{1c82}' => out.push_str("\u{43e}"),
            '\u{1c83}' => out.push_str("\u{441}"),
            '\u{1c84}' => out.push_str("\u{442}"),
            '\u{1c85}' => out.push_str("\u{442}"),
            '\u{1c86}' => out.push_str("\u{44a}"),
            '\u{1c87}' => out.push_str("\u{463}"),
            '\u{1c88}' => out.push_str("\u{a64b}"),
            '\u{1e96}' => out.push_str("\u{68}\u{331}"),
            '\u{1e97}' => out.push_str("\u{74}\u{308}"),
            '\u{1e98}' => out.push_str("\u{77}\u{30a}"),
            '\u{1e99}' => out.push_str("\u{79}\u{30a}"),
            '\u{1e9a}' => out.push_str("\u{61}\u{2be}"),
            '\u{1e9b}' => out.push_str("\u{1e61}"),
            '\u{1e9e}' => out.push_str("\u{73}\u{73}"),
            '\u{1f50}' => out.push_str("\u{3c5}\u{313}"),
            '\u{1f52}' => out.push_str("\u{3c5}\u{313}\u{300}"),
            '\u{1f54}' => out.push_str("\u{3c5}\u{313}\u{301}"),
            '\u{1f56}' => out.push_str("\u{3c5}\u{313}\u{342}"),
            '\u{1f80}' => out.push_str("\u{1f00}\u{3b9}"),
            '\u{1f81}' => out.push_str("\u{1f01}\u{3b9}"),
            '\u{1f82}' => out.push_str("\u{1f02}\u{3b9}"),
            '\u{1f83}' => out.push_str("\u{1f03}\u{3b9}"),
            '\u{1f84}' => out.push_str("\u{1f04}\u{3b9}"),
            '\u{1f85}' => out.push_str("\u{1f05}\u{3b9}"),
            '\u{1f86}' => out.push_str("\u{1f06}\u{3b9}"),
            '\u{1f87}' => out.push_str("\u{1f07}\u{3b9}"),
            '\u{1f88}' => out.push_str("\u{1f00}\u{3b9}"),
            '\u{1f89}' => out.push_str("\u{1f01}\u{3b9}"),
            '\u{1f8a}' => out.push_str("\u{1f02}\u{3b9}"),
            '\u{1f8b}' => out.push_str("\u{1f03}\u{3b9}"),
            '\u{1f8c}' => out.push_str("\u{1f04}\u{3b9}"),
            '\u{1f8d}' => out.push_str("\u{1f05}\u{3b9}"),
            '\u{1f8e}' => out.push_str("\u{1f06}\u{3b9}"),
            '\u{1f8f}' => out.push_str("\u{1f07}\u{3b9}"),
            '\u{1f90}' => out.push_str("\u{1f20}\u{3b9}"),
            '\u{1f91}' => out.push_str("\u{1f21}\u{3b9}"),
            '\u{1f92}' => out.push_str("\u{1f22}\u{3b9}"),
            '\u{1f93}' => out.push_str("\u{1f23}\u{3b9}"),
            '\u{1f94}' => out.push_str("\u{1f24}\u{3b9}"),
            '\u{1f95}' => out.push_str("\u{1f25}\u{3b9}"),
            '\u{1f96}' => out.push_str("\u{1f26}\u{3b9}"),
            '\u{1f97}' => out.push_str("\u{1f27}\u{3b9}"),
            '\u{1f98}' => out.push_str("\u{1f20}\u{3b9}"),
            '\u{1f99}' => out.push_str("\u{1f21}\u{3b9}"),
            '\u{1f9a}' => out.push_str("\u{1f22}\u{3b9}"),
            '\u{1f9b}' => out.push_str("\u{1f23}\u{3b9}"),
            '\u{1f9c}' => out.push_str("\u{1f24}\u{3b9}"),
            '\u{1f9d}' => out.push_str("\u{1f25}\u{3b9}"),
            '\u{1f9e}' => out.push_str("\u{1f26}\u{3b9}"),
            '\u{1f9f}' => out.push_str("\u{1f27}\u{3b9}"),
            '\u{1fa0}' => out.push_str("\u{1f60}\u{3b9}"),
            '\u{1fa1}' => out.push_str("\u{1f61}\u{3b9}"),
            '\u{1fa2}' => out.push_str("\u{1f62}\u{3b9}"),
            '\u{1fa3}' => out.push_str("\u{1f63}\u{3b9}"),
            '\u{1fa4}' => out.push_str("\u{1f64}\u{3b9}"),
            '\u{1fa5}' => out.push_str("\u{1f65}\u{3b9}"),
            '\u{1fa6}' => out.push_str("\u{1f66}\u{3b9}"),
            '\u{1fa7}' => out.push_str("\u{1f67}\u{3b9}"),
            '\u{1fa8}' => out.push_str("\u{1f60}\u{3b9}"),
            '\u{1fa9}' => out.push_str("\u{1f61}\u{3b9}"),
            '\u{1faa}' => out.push_str("\u{1f62}\u{3b9}"),
            '\u{1fab}' => out.push_str("\u{1f63}\u{3b9}"),
            '\u{1fac}' => out.push_str("\u{1f64}\u{3b9}"),
            '\u{1fad}' => out.push_str("\u{1f65}\u{3b9}"),
            '\u{1fae}' => out.push_str("\u{1f66}\u{3b9}"),
            '\u{1faf}' => out.push_str("\u{1f67}\u{3b9}"),
            '\u{1fb2}' => out.push_str("\u{1f70}\u{3b9}"),
            '\u{1fb3}' => out.push_str("\u{3b1}\u{3b9}"),
            '\u{1fb4}' => out.push_str("\u{3ac}\u{3b9}"),
            '\u{1fb6}' => out.push_str("\u{3b1}\u{342}"),
            '\u{1fb7}' => out.push_str("\u{3b1}\u{342}\u{3b9}"),
            '\u{1fbc}' => out.push_str("\u{3b1}\u{3b9}"),
            '\u{1fbe}' => out.push_str("\u{3b9}"),
            '\u{1fc2}' => out.push_str("\u{1f74}\u{3b9}"),
            '\u{1fc3}' => out.push_str("\u{3b7}\u{3b9}"),
            '\u{1fc4}' => out.push_str("\u{3ae}\u{3b9}"),
            '\u{1fc6}' => out.push_str("\u{3b7}\u{342}"),
            '\u{1fc7}' => out.push_str("\u{3b7}\u{342}\u{3b9}"),
            '\u{1fcc}' => out.push_str("\u{3b7}\u{3b9}"),
            '\u{1fd2}' => out.push_str("\u{3b9}\u{308}\u{300}"),
            '\u{1fd3}' => out.push_str("\u{3b9}\u{308}\u{301}"),
            '\u{1fd6}' => out.push_str("\u{3b9}\u{342}"),
            '\u{1fd7}' => out.push_str("\u{3b9}\u{308}\u{342}"),
            '\u{1fe2}' => out.push_str("\u{3c5}\u{308}\u{300}"),
            '\u{1fe3}' => out.push_str("\u{3c5}\u{308}\u{301}"),
            '\u{1fe4}' => out.push_str("\u{3c1}\u{313}"),
            '\u{1fe6}' => out.push_str("\u{3c5}\u{342}"),
            '\u{1fe7}' => out.push_str("\u{3c5}\u{308}\u{342}"),
            '\u{1ff2}' => out.push_str("\u{1f7c}\u{3b9}"),
            '\u{1ff3}' => out.push_str("\u{3c9}\u{3b9}"),
            '\u{1ff4}' => out.push_str("\u{3ce}\u{3b9}"),
            '\u{1ff6}' => out.push_str("\u{3c9}\u{342}"),
            '\u{1ff7}' => out.push_str("\u{3c9}\u{342}\u{3b9}"),
            '\u{1ffc}' => out.push_str("\u{3c9}\u{3b9}"),
            '\u{ab70}' => out.push_str("\u{13a0}"),
            '\u{ab71}' => out.push_str("\u{13a1}"),
            '\u{ab72}' => out.push_str("\u{13a2}"),
            '\u{ab73}' => out.push_str("\u{13a3}"),
            '\u{ab74}' => out.push_str("\u{13a4}"),
            '\u{ab75}' => out.push_str("\u{13a5}"),
            '\u{ab76}' => out.push_str("\u{13a6}"),
            '\u{ab77}' => out.push_str("\u{13a7}"),
            '\u{ab78}' => out.push_str("\u{13a8}"),
            '\u{ab79}' => out.push_str("\u{13a9}"),
            '\u{ab7a}' => out.push_str("\u{13aa}"),
            '\u{ab7b}' => out.push_str("\u{13ab}"),
            '\u{ab7c}' => out.push_str("\u{13ac}"),
            '\u{ab7d}' => out.push_str("\u{13ad}"),
            '\u{ab7e}' => out.push_str("\u{13ae}"),
            '\u{ab7f}' => out.push_str("\u{13af}"),
            '\u{ab80}' => out.push_str("\u{13b0}"),
            '\u{ab81}' => out.push_str("\u{13b1}"),
            '\u{ab82}' => out.push_str("\u{13b2}"),
            '\u{ab83}' => out.push_str("\u{13b3}"),
            '\u{ab84}' => out.push_str("\u{13b4}"),
            '\u{ab85}' => out.push_str("\u{13b5}"),
            '\u{ab86}' => out.push_str("\u{13b6}"),
            '\u{ab87}' => out.push_str("\u{13b7}"),
            '\u{ab88}' => out.push_str("\u{13b8}"),
            '\u{ab89}' => out.push_str("\u{13b9}"),
            '\u{ab8a}' => out.push_str("\u{13ba}"),
            '\u{ab8b}' => out.push_str("\u{13bb}"),
            '\u{ab8c}' => out.push_str("\u{13bc}"),
            '\u{ab8d}' => out.push_str("\u{13bd}"),
            '\u{ab8e}' => out.push_str("\u{13be}"),
            '\u{ab8f}' => out.push_str("\u{13bf}"),
            '\u{ab90}' => out.push_str("\u{13c0}"),
            '\u{ab91}' => out.push_str("\u{13c1}"),
            '\u{ab92}' => out.push_str("\u{13c2}"),
            '\u{ab93}' => out.push_str("\u{13c3}"),
            '\u{ab94}' => out.push_str("\u{13c4}"),
            '\u{ab95}' => out.push_str("\u{13c5}"),
            '\u{ab96}' => out.push_str("\u{13c6}"),
            '\u{ab97}' => out.push_str("\u{13c7}"),
            '\u{ab98}' => out.push_str("\u{13c8}"),
            '\u{ab99}' => out.push_str("\u{13c9}"),
            '\u{ab9a}' => out.push_str("\u{13ca}"),
            '\u{ab9b}' => out.push_str("\u{13cb}"),
            '\u{ab9c}' => out.push_str("\u{13cc}"),
            '\u{ab9d}' => out.push_str("\u{13cd}"),
            '\u{ab9e}' => out.push_str("\u{13ce}"),
            '\u{ab9f}' => out.push_str("\u{13cf}"),
            '\u{aba0}' => out.push_str("\u{13d0}"),
            '\u{aba1}' => out.push_str("\u{13d1}"),
            '\u{aba2}' => out.push_str("\u{13d2}"),
            '\u{aba3}' => out.push_str("\u{13d3}"),
            '\u{aba4}' => out.push_str("\u{13d4}"),
            '\u{aba5}' => out.push_str("\u{13d5}"),
            '\u{aba6}' => out.push_str("\u{13d6}"),
            '\u{aba7}' => out.push_str("\u{13d7}"),
            '\u{aba8}' => out.push_str("\u{13d8}"),
            '\u{aba9}' => out.push_str("\u{13d9}"),
            '\u{abaa}' => out.push_str("\u{13da}"),
            '\u{abab}' => out.push_str("\u{13db}"),
            '\u{abac}' => out.push_str("\u{13dc}"),
            '\u{abad}' => out.push_str("\u{13dd}"),
            '\u{abae}' => out.push_str("\u{13de}"),
            '\u{abaf}' => out.push_str("\u{13df}"),
            '\u{abb0}' => out.push_str("\u{13e0}"),
            '\u{abb1}' => out.push_str("\u{13e1}"),
            '\u{abb2}' => out.push_str("\u{13e2}"),
            '\u{abb3}' => out.push_str("\u{13e3}"),
            '\u{abb4}' => out.push_str("\u{13e4}"),
            '\u{abb5}' => out.push_str("\u{13e5}"),
            '\u{abb6}' => out.push_str("\u{13e6}"),
            '\u{abb7}' => out.push_str("\u{13e7}"),
            '\u{abb8}' => out.push_str("\u{13e8}"),
            '\u{abb9}' => out.push_str("\u{13e9}"),
            '\u{abba}' => out.push_str("\u{13ea}"),
            '\u{abbb}' => out.push_str("\u{13eb}"),
            '\u{abbc}' => out.push_str("\u{13ec}"),
            '\u{abbd}' => out.push_str("\u{13ed}"),
            '\u{abbe}' => out.push_str("\u{13ee}"),
            '\u{abbf}' => out.push_str("\u{13ef}"),
            '\u{fb00}' => out.push_str("\u{66}\u{66}"),
            '\u{fb01}' => out.push_str("\u{66}\u{69}"),
            '\u{fb02}' => out.push_str("\u{66}\u{6c}"),
            '\u{fb03}' => out.push_str("\u{66}\u{66}\u{69}"),
            '\u{fb04}' => out.push_str("\u{66}\u{66}\u{6c}"),
            '\u{fb05}' => out.push_str("\u{73}\u{74}"),
            '\u{fb06}' => out.push_str("\u{73}\u{74}"),
            '\u{fb13}' => out.push_str("\u{574}\u{576}"),
            '\u{fb14}' => out.push_str("\u{574}\u{565}"),
            '\u{fb15}' => out.push_str("\u{574}\u{56b}"),
            '\u{fb16}' => out.push_str("\u{57e}\u{576}"),
            '\u{fb17}' => out.push_str("\u{574}\u{56d}"),
            _ => out.extend(c.to_lowercase()),
        }
    }
    out
}
fn matches_project(meta: &Value, project: &str) -> Result<bool> {
    let cwd = meta
        .get("cwd")
        .filter(|v| truthy(v))
        .and_then(Value::as_str)
        .unwrap_or("/");
    if project.contains('/') || project.contains('\\') {
        return Ok(Path::new(cwd) == resolve(Path::new(project))?);
    }
    let remote = meta
        .pointer("/git/repository_url")
        .and_then(Value::as_str)
        .unwrap_or("");
    let remote = remote
        .strip_suffix(".git")
        .unwrap_or(remote)
        .trim_end_matches('/')
        .rsplit('/')
        .next()
        .unwrap_or("");
    Ok(casefold(
        Path::new(cwd)
            .file_name()
            .and_then(|v| v.to_str())
            .unwrap_or(""),
    ) == casefold(project)
        || casefold(remote) == casefold(project))
}
fn lines(raw: &[u8]) -> Vec<&[u8]> {
    let mut result = Vec::new();
    let mut start = 0;
    let mut i = 0;
    while i < raw.len() {
        if raw[i] == b'\n' || raw[i] == b'\r' {
            result.push(&raw[start..i]);
            if raw[i] == b'\r' && raw.get(i + 1) == Some(&b'\n') {
                i += 1;
            }
            start = i + 1;
        }
        i += 1;
    }
    if start < raw.len() {
        result.push(&raw[start..]);
    }
    result
}
fn number(v: &Value, key: &str) -> u64 {
    v.get(key).and_then(Value::as_u64).unwrap_or(0)
}
fn text<'a>(v: &'a Value, key: &str) -> &'a str {
    v.get(key).and_then(Value::as_str).unwrap_or("")
}
fn audit(home: &Path, project: &str) -> Result<Value> {
    let mut inventory: Vec<(PathBuf, Value)> = Vec::new();
    let mut errors = Vec::new();
    for folder in ["sessions", "archived_sessions"] {
        let root = home.join(folder);
        let mut paths: Vec<_> = WalkDir::new(root)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| {
                !e.file_type().is_dir() && e.path().extension().is_some_and(|x| x == "jsonl")
            })
            .map(|e| e.into_path())
            .collect();
        paths.sort();
        for path in paths {
            let first = fs::read(&path)
                .map_err(|e| match e.kind() {
                    std::io::ErrorKind::NotFound => "FileNotFoundError",
                    std::io::ErrorKind::PermissionDenied => "PermissionError",
                    _ => "OSError",
                })
                .and_then(|raw| {
                    let first = lines(&raw).first().copied().ok_or("StopIteration")?;
                    let s = std::str::from_utf8(first).map_err(|_| "UnicodeDecodeError")?;
                    let v: Value = serde_json::from_str(s).map_err(|_| "JSONDecodeError")?;
                    if !v.is_object() || text(&v, "type") != "session_meta" {
                        return Err("ValueError");
                    }
                    let meta = v.get("payload").cloned().unwrap_or_else(|| json!({}));
                    if !meta.is_object()
                        || meta
                            .get("id")
                            .and_then(Value::as_str)
                            .is_none_or(str::is_empty)
                    {
                        return Err("ValueError");
                    }
                    Ok(meta)
                });
            match first { Ok(meta) => inventory.push((path,meta)), Err(e) => errors.push(json!({"file": path.strip_prefix(home).unwrap_or(&path).to_string_lossy(), "error":e})) }
        }
    }
    let mut selected = HashSet::<String>::new();
    for (_, m) in &inventory {
        if matches_project(m, project)? {
            selected.insert(text(m, "id").to_owned());
        }
    }
    loop {
        let mut added = false;
        for (_, m) in &inventory {
            if m.get("parent_thread_id")
                .and_then(Value::as_str)
                .is_some_and(|p| selected.contains(p))
            {
                added |= selected.insert(text(m, "id").to_owned());
            }
        }
        if !added {
            break;
        }
    }
    let mut sessions = Vec::<Value>::new();
    let mut calls = Vec::<Value>::new();
    let mut call_index = HashMap::<String, usize>::new();
    let mut outputs = HashMap::<String, usize>::new();
    let mut usage = HashMap::<String, Value>::new();
    let mut usage_order = Vec::new();
    let mut duplicates = 0u64;
    for (path, meta) in &inventory {
        if !selected.contains(text(meta, "id")) {
            continue;
        }
        let raw = fs::read(path)?;
        let source = path
            .strip_prefix(home)
            .unwrap_or(path)
            .to_string_lossy()
            .to_string();
        let mut session = json!({"id":meta.get("id"),"parent":meta.get("parent_thread_id"),"source":source,"sha256":hash(&raw),"bytes":raw.len(),"started":meta.get("timestamp"),"malformed_lines":0,"usage_records":0,"legacy_usage_seen":false});
        let mut malformed = 0;
        let mut usage_records = 0;
        let mut legacy = false;
        for (line_no, line) in lines(&raw).into_iter().enumerate() {
            let record: Value = match serde_json::from_slice(line) {
                Ok(v) => v,
                Err(_) => {
                    malformed += 1;
                    continue;
                }
            };
            if !record.is_object() {
                anyhow::bail!("transcript record is not an object");
            }
            let empty_payload = json!({});
            let payload = record.get("payload").unwrap_or(&empty_payload);
            if !payload.is_object() {
                anyhow::bail!("transcript payload is not an object");
            }
            let kind = text(payload, "type");
            if text(&record, "type") == "token_usage_record" {
                if let Some(id) = payload.get("response_id").filter(|v| truthy(v)) {
                    let key = dict_key(id)?;
                    if !usage.contains_key(&key)
                        && payload
                            .get("thread_id")
                            .and_then(Value::as_str)
                            .is_some_and(|id| selected.contains(id))
                    {
                        usage_order.push(key.clone());
                        usage.insert(
                            key,
                            payload.get("usage").cloned().unwrap_or_else(|| json!({})),
                        );
                        usage_records += 1;
                    }
                }
            }
            if kind == "token_count" {
                legacy = true;
            }
            if text(&record, "type") != "response_item" {
                continue;
            }
            let key = payload
                .get("call_id")
                .filter(|v| truthy(v))
                .or_else(|| payload.get("id").filter(|v| truthy(v)))
                .cloned();
            if kind == "function_call" || kind == "custom_tool_call" {
                let key = key.unwrap_or_else(|| Value::String(hash(line)));
                let index_key = dict_key(&key)?;
                if call_index.contains_key(&index_key) {
                    duplicates += 1;
                    continue;
                }
                let arguments = payload
                    .get("arguments")
                    .or_else(|| payload.get("input"))
                    .cloned()
                    .unwrap_or_else(|| json!(""));
                let name = match payload.get("name") {
                    None => "unknown",
                    Some(Value::String(s)) => s.as_str(),
                    Some(_) => anyhow::bail!("tool name is not a string"),
                };
                let visible = visible(&arguments);
                let arg_str = py_str(&arguments);
                let fingerprint = hash(format!("{name}\n{arg_str}").as_bytes());
                let call = json!({"call_id":key,"session":meta.get("id"),"source":source,"line":line_no+1,"tool":name,"category":classify(name,&visible),"input_chars":visible.chars().count(),"fingerprint":fingerprint,"opaque":cipher().is_match(&arg_str)});
                call_index.insert(index_key, calls.len());
                calls.push(call);
            } else if (kind == "function_call_output" || kind == "custom_tool_call_output")
                && key.is_some()
            {
                let key = dict_key(key.as_ref().unwrap())?;
                let length = visible(payload.get("output").unwrap_or(&Value::Null))
                    .chars()
                    .count();
                outputs
                    .entry(key)
                    .and_modify(|x| *x = (*x).max(length))
                    .or_insert(length);
            }
        }
        session["malformed_lines"] = json!(malformed);
        session["usage_records"] = json!(usage_records);
        session["legacy_usage_seen"] = json!(legacy);
        sessions.push(session);
    }
    let mut groups = Vec::<(String, Vec<usize>)>::new();
    let mut repeats = Vec::<(String, Vec<usize>)>::new();
    let mut repeat_index = HashMap::<String, usize>::new();
    for (i, call) in calls.iter_mut().enumerate() {
        let output = outputs
            .get(&dict_key(&call["call_id"])?)
            .copied()
            .unwrap_or(0);
        let estimate = (number(call, "input_chars") + output as u64 + 3) / 4;
        call["output_chars"] = json!(output);
        call["estimated_tokens"] = json!(estimate);
        let category = text(call, "category").to_owned();
        if let Some((_, rows)) = groups.iter_mut().find(|(k, _)| *k == category) {
            rows.push(i);
        } else {
            groups.push((category, vec![i]));
        }
        let fp = text(call, "fingerprint").to_owned();
        if let Some(index) = repeat_index.get(&fp) {
            repeats[*index].1.push(i);
        } else {
            repeat_index.insert(fp.clone(), repeats.len());
            repeats.push((fp, vec![i]));
        }
    }
    let categories: Vec<Value> = groups.into_iter().map(|(label,mut rows)| { let sum: u64 = rows.iter().map(|i| number(&calls[*i],"estimated_tokens")).sum(); let session_count = rows.iter().map(|i| text(&calls[*i],"session")).collect::<HashSet<_>>().len(); rows.sort_by_key(|i| std::cmp::Reverse(number(&calls[*i],"estimated_tokens"))); json!({"work":label,"count":rows.len(),"estimated_tokens":sum,"sessions":session_count,"examples":rows.iter().take(3).map(|i| calls[*i].clone()).collect::<Vec<_>>()}) }).collect();
    let mut identical: Vec<Value> = repeats.into_iter().filter(|(_,r)| r.len()>1).map(|(fp,rows)| json!({"fingerprint":fp,"count":rows.len(),"repeat_count":rows.len()-1,"work":calls[rows[0]]["category"],"estimated_tokens":rows.iter().map(|i| number(&calls[*i],"estimated_tokens")).sum::<u64>(),"examples":rows.iter().take(3).map(|i| calls[*i].clone()).collect::<Vec<_>>() })).collect();
    identical.sort_by(|a, b| {
        number(b, "count")
            .cmp(&number(a, "count"))
            .then_with(|| text(a, "fingerprint").cmp(text(b, "fingerprint")))
    });
    let mut totals = Map::new();
    for k in &usage_order {
        if let Some(obj) = usage[k].as_object() {
            for (key, v) in obj {
                let n = if let Some(b) = v.as_bool() {
                    Some(if b { 1 } else { 0 })
                } else {
                    v.as_i64()
                };
                if let Some(n) = n {
                    let old = totals.get(key).and_then(Value::as_i64).unwrap_or(0);
                    totals.insert(key.clone(), json!(old + n));
                }
            }
        }
    }
    let roots: HashSet<_> = sessions
        .iter()
        .filter(|s| !truthy(&s["parent"]))
        .map(|s| text(s, "id"))
        .collect();
    let agents: HashSet<_> = sessions
        .iter()
        .filter(|s| truthy(&s["parent"]))
        .map(|s| text(s, "id"))
        .collect();
    Ok(
        json!({"schema":"harness-session-audit-v1","project":project,"created_utc":Utc::now().to_rfc3339_opts(SecondsFormat::Micros,false),"method":METHOD,
        "coverage":{"session_files":sessions.len(),"session_ids":selected.len(),"root_sessions":roots.len(),"agent_sessions":agents.len(),"archived_files":sessions.iter().filter(|s| text(s,"source").starts_with("archived_sessions/")).count(),"unique_calls":calls.len(),"copied_calls_removed":duplicates,"calls_missing_output":calls.iter().filter(|c| dict_key(&c["call_id"]).map_or(true, |k| !outputs.contains_key(&k))).count(),"opaque_calls":calls.iter().filter(|c| c["opaque"] == true).count(),"usage_responses":usage.len(),"inventory_errors":errors},"recorded_usage":totals,"categories":categories,"identical_calls":identical,"sessions":sessions}),
    )
}
fn comma(n: u64) -> String {
    let s = n.to_string();
    let mut r = String::new();
    for (i, c) in s.chars().enumerate() {
        if i > 0 && (s.len() - i) % 3 == 0 {
            r.push(',');
        }
        r.push(c);
    }
    r
}
fn markdown(report: &Value) -> String {
    let c = &report["coverage"];
    let mut out = Vec::<String>::new();
    let empty = String::new();
    out.push(
        if text(report, "project") == "arena" {
            "# Arena session audit"
        } else {
            "# Session audit"
        }
        .into(),
    );
    out.push(empty.clone());
    out.push(format!("Snapshot: {}", text(report, "created_utc")));
    out.push(empty.clone());
    out.push(METHOD.into());
    out.push(empty.clone());
    out.push(format!("Reviewed {} files for {} sessions ({} roots, {} agents; {} archived files), {} unique call batches. Removed {} copied calls. {} calls contain unreadable encrypted text; {} have no recorded result.",number(c,"session_files"),number(c,"session_ids"),number(c,"root_sessions"),number(c,"agent_sessions"),number(c,"archived_files"),number(c,"unique_calls"),number(c,"copied_calls_removed"),number(c,"opaque_calls"),number(c,"calls_missing_output")));
    out.push(empty.clone());
    out.push(format!(
        "Inventory errors: {}; malformed lines in selected files: {}.",
        c["inventory_errors"].as_array().unwrap().len(),
        report["sessions"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| number(s, "malformed_lines"))
            .sum::<u64>()
    ));
    out.push(empty.clone());
    for (label, field) in [
        ("Count: highest to lowest", "count"),
        (
            "Estimated token cost: highest to lowest",
            "estimated_tokens",
        ),
    ] {
        out.extend([
            format!("## {label}"),
            empty.clone(),
            "| Repeated work | Count | Estimated tokens | Sessions |".into(),
            "|---|---:|---:|---:|".into(),
        ]);
        let mut rows: Vec<_> = report["categories"].as_array().unwrap().iter().collect();
        rows.sort_by(|a, b| {
            number(b, field)
                .cmp(&number(a, field))
                .then_with(|| text(a, "work").cmp(text(b, "work")))
        });
        for r in rows {
            out.push(format!(
                "| {} | {} | {} | {} |",
                text(r, "work"),
                comma(number(r, "count")),
                comma(number(r, "estimated_tokens")),
                number(r, "sessions")
            ));
        }
        out.push(empty.clone());
    }
    let sorted: BTreeMap<_, _> = report["recorded_usage"]
        .as_object()
        .unwrap()
        .iter()
        .collect();
    let usage = sorted
        .iter()
        .map(|(k, v)| format!("{}: {}", ascii_json(&serde_json::to_string(k).unwrap()), v))
        .collect::<Vec<_>>()
        .join(", ");
    out.extend(["## Recorded model usage".into(),empty.clone(),format!("{} unique response usage records: `{{{}}}`.",comma(number(c,"usage_responses")),usage),empty.clone(),"Cached input is part of input; reasoning output is part of output. Do not add either twice. These totals are not attributed to work categories. Sessions with only legacy counters or encrypted work have incomplete accounting.".into(),empty.clone(),"## Exact repeated calls".into(),empty.clone(),"Identical call name and arguments; repetition may be needed after state changes.".into(),empty.clone(),"| Work | Total | Repeats after first | Estimated tokens | Evidence (session / line) |".into(),"|---|---:|---:|---:|---|".into()]);
    for row in report["identical_calls"]
        .as_array()
        .unwrap()
        .iter()
        .take(20)
    {
        let example = &row["examples"][0];
        out.push(format!(
            "| {} | {} | {} | {} | {} / {} |",
            text(row, "work"),
            number(row, "count"),
            number(row, "repeat_count"),
            comma(number(row, "estimated_tokens")),
            text(example, "session"),
            number(example, "line")
        ));
    }
    out.extend([empty.clone(),"The adjacent JSON records every selected session, its content hash, category evidence, and all exact-repeat groups. Call counts identify repeated activity, not proven redundant work. No claimed token savings have been measured.".into(),empty]);
    out.join("\n")
}
pub fn run(args: &[OsString]) -> Result<i32> {
    let command = Command::new("session-audit")
        .about("Audit local Codex rollouts without executing transcript contents.")
        .arg(
            Arg::new("project")
                .long("project")
                .required(true)
                .help("project directory or exact basename/remote name"),
        )
        .arg(
            Arg::new("codex-home")
                .long("codex-home")
                .value_parser(clap::value_parser!(PathBuf)),
        )
        .arg(
            Arg::new("output")
                .long("output")
                .required(true)
                .value_parser(clap::value_parser!(PathBuf))
                .help("output stem for .json and .md"),
        );
    let matches = match command.try_get_matches_from(
        std::iter::once(OsString::from("session-audit")).chain(args.iter().cloned()),
    ) {
        Ok(m) => m,
        Err(e) => {
            let code = e.exit_code();
            e.print()?;
            return Ok(code);
        }
    };
    let home = matches
        .get_one::<PathBuf>("codex-home")
        .cloned()
        .unwrap_or_else(|| {
            dirs::home_dir()
                .unwrap_or_else(|| PathBuf::from("~"))
                .join(".codex")
        });
    let home = expand(&home);
    let report = audit(&home, matches.get_one::<String>("project").unwrap())?;
    let output = matches.get_one::<PathBuf>("output").unwrap();
    if let Some(parent) = output.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(parent).with_context(|| format!("creating {}", parent.display()))?;
    }
    fs::write(
        output.with_extension("json"),
        format!("{}\n", ascii_json(&serde_json::to_string_pretty(&report)?)),
    )?;
    fs::write(output.with_extension("md"), markdown(&report))?;
    println!(
        "{}",
        ascii_json(&serde_json::to_string(&report["coverage"])?)
    );
    Ok(if number(&report["coverage"], "session_files") > 0 {
        0
    } else {
        1
    })
}
