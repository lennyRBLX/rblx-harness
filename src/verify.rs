use anyhow::Result;
use std::{ffi::OsString, path::Path, process::Command};

const CASES: &[&str] = &[
    "repository surface is seven skills and five agents for Codex and Claude Code",
    "harness setup rebuilds ignored Codex and Claude Code support and all source skills",
    "Codex config merge preserves custom tables",
    "Claude settings merge preserves custom values",
    "Claude Roblox settings profile allows the harness cache and remains optional",
    "new-game approval installs the fixed GitHub submodule into an unborn repository",
    "inspection identifies existing scoped modules without writing",
    "scaffold requires bare service and controller names",
    "integration failure retains state and reports setup-only recovery",
    "full scaffold links assets and preserves existing module bytes",
    "plugins directory is optional",
    "legacy plugin support migrates when the harness is declined",
    "data tools require no human schema review",
    "API access evidence preserves restrictions",
    "type cache preserves validation",
    "project validation, boot output, and verification selection",
    "session audit, bounded context and console deltas",
    "native Codex migration and consolidated commands",
    "local ATC overlap, concurrent scope leases and lifecycle cleanup",
    "native Claude Code settings, agents, hook migration, and permission profile",
    "Luau contracts: const, profile/parallel pairing, codecs and remote ownership",
    "test buffer, capture coverage, collection and cleanup boundaries",
    "Collisions package registry ownership and lifecycle",
    "hot reload and source persistence refuse stale state and preserve callers",
    "PlayerData scaffold departure cleanup and optional packages",
];

fn case(index: usize, root: &Path) -> Result<()> {
    let mut slug = String::new();
    let mut separator = false;
    for ch in CASES[index].chars() {
        if ch.is_ascii_alphanumeric() {
            if separator && !slug.is_empty() {
                slug.push('_');
            }
            slug.push(ch.to_ascii_lowercase());
            separator = false;
        } else {
            separator = true;
        }
    }
    let output = Command::new("cargo")
        .current_dir(root)
        .args(["test", "--tests", &slug, "--", "--exact", "--nocapture"])
        .output()?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let test_output = format!("{stdout}{stderr}");
    if let Some(reason) = test_output.lines().find(|line| line.starts_with("UNRUN|")) {
        anyhow::bail!("{reason}");
    }
    if let Some(reason) = test_output
        .lines()
        .find(|line| line.contains(" ... ignored"))
    {
        anyhow::bail!("UNRUN|{reason}");
    }
    if !output.status.success() {
        anyhow::bail!("native test failed: {}{}", stdout.trim(), stderr.trim());
    }
    let expected = format!("test {slug} ... ok");
    if !stdout.lines().any(|line| line.trim() == expected) {
        anyhow::bail!("native test {slug} did not run successfully");
    }
    Ok(())
}

pub fn run(args: &[OsString]) -> Result<i32> {
    let mut patterns = Vec::new();
    let mut list = false;
    let mut i = 0;
    while i < args.len() {
        let arg = args[i].to_string_lossy();
        if arg == "--list" {
            list = true;
        } else if arg == "--case" {
            i += 1;
            let Some(pattern) = args.get(i) else {
                eprintln!("usage: harness check harness [-h] [--list] [--case MATCH]\nharness check harness: error: argument --case: expected one argument");
                return Ok(2);
            };
            patterns.push(pattern.to_string_lossy().into_owned());
        } else if let Some(pattern) = arg.strip_prefix("--case=") {
            patterns.push(pattern.to_owned());
        } else if arg == "--help" || arg == "-h" {
            println!("usage: harness check harness [-h] [--list] [--case MATCH]\n\nFocused verification for the lean rblx-harness surface.\n\noptions:\n  -h, --help    show this help message and exit\n  --list        List case names without running them\n  --case MATCH  Select names containing MATCH, ignoring case; repeatable, each must match");
            return Ok(0);
        } else {
            eprintln!("usage: harness check harness [-h] [--list] [--case MATCH]\nharness check harness: error: unrecognized arguments: {arg}");
            return Ok(2);
        }
        i += 1;
    }
    for pattern in &patterns {
        if pattern.trim().is_empty()
            || !CASES
                .iter()
                .any(|name| name.to_lowercase().contains(&pattern.to_lowercase()))
        {
            eprintln!("usage: harness check harness [-h] [--list] [--case MATCH]\nharness check harness: error: no cases match {pattern:?}; use --list");
            return Ok(2);
        }
    }
    let selected: Vec<_> = CASES
        .iter()
        .enumerate()
        .filter(|(_, name)| {
            patterns.is_empty()
                || patterns
                    .iter()
                    .any(|p| name.to_lowercase().contains(&p.to_lowercase()))
        })
        .collect();
    if list {
        for (_, name) in selected {
            println!("{name}");
        }
        return Ok(0);
    }
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let mut failures = 0;
    let mut skipped = 0;
    for &(index, name) in &selected {
        if let Err(error) = case(index, root) {
            let message = error.to_string();
            if let Some(reason) = message.strip_prefix("UNRUN|") {
                println!("SKIP|{name}|{reason}");
                skipped += 1;
            } else {
                println!("FAIL|{name}|{error}");
                failures += 1;
            }
        }
    }
    let state = if failures > 0 {
        "FAILED"
    } else if skipped > 0 {
        "BLOCKED"
    } else {
        "READY"
    };
    if !patterns.is_empty() {
        println!(
            "VERIFY|SELECTED|{state}|{}/{}|failures={failures}|skipped={skipped}",
            selected.len(),
            CASES.len()
        );
    } else if failures != 0 {
        println!(
            "VERIFY|FAILED|{failures}/{}|skipped={skipped}",
            selected.len()
        );
    } else if skipped != 0 {
        println!("VERIFY|BLOCKED|{}|skipped={skipped}", selected.len());
    } else {
        println!("VERIFY|READY|{}", selected.len());
    }
    Ok(if failures != 0 {
        2
    } else if skipped != 0 {
        3
    } else {
        0
    })
}
