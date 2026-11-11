pub mod api;
pub mod argon;
pub mod buffer;
pub mod checks;
pub mod coord;
pub mod gates;
pub mod hooks;
pub mod offline;
pub mod profile;
pub mod project_gate;
pub mod scaffold;
pub mod session;
pub mod setup;
pub mod studio;
pub mod toolchain;
pub mod types;
pub mod verify;

use std::ffi::OsString;
use std::path::PathBuf;

const HELP: &str = "Roblox domain tools. Native shell, search, editing, and Git remain available.\n\nUsage: harness [--root PROJECT] FAMILY [ACTION] [ARGS...]\n\nFamilies: api, types, data-write, check, inspect, coord, profile, studio, argon, scaffold, setup, hook\n";

fn is_help(value: &std::ffi::OsStr) -> bool {
    value == "--help" || value == "-h"
}

pub fn run<I>(args: I) -> anyhow::Result<i32>
where
    I: IntoIterator<Item = OsString>,
{
    let mut args: Vec<OsString> = args.into_iter().collect();
    if args.first().is_some_and(|arg| is_help(arg)) || args.is_empty() {
        print!("{HELP}");
        return Ok(0);
    }

    let mut root = std::env::current_dir()?;
    let index = 0;
    while index < args.len() {
        let token = args[index].to_string_lossy();
        if token == "--root" {
            let value = args
                .get(index + 1)
                .ok_or_else(|| anyhow::anyhow!("--root needs a path"))?;
            root = PathBuf::from(value);
            args.drain(index..=index + 1);
        } else if let Some(value) = token.strip_prefix("--root=") {
            root = PathBuf::from(value);
            args.remove(index);
        } else {
            break;
        }
    }
    if args.is_empty() {
        print!("{HELP}");
        return Ok(0);
    }
    let root = root
        .canonicalize()
        .map_err(|error| anyhow::anyhow!("project root is unavailable: {error}"))?;
    if !root.is_dir() {
        anyhow::bail!("project root is not a directory: {}", root.display());
    }
    let family = args[0].to_string_lossy().into_owned();
    args.remove(0);
    std::env::set_current_dir(&root)?;

    let code = match family.as_str() {
        "api" => api::run(&args)?,
        "types" => types::run(&args)?,
        "data-write" => checks::run_data(&args)?,
        "check" => match args.first().and_then(|value| value.to_str()) {
            Some("harness") => verify::run(&args[1..])?,
            Some("project") => {
                let mut forwarded = vec![
                    OsString::from("--project-root"),
                    root.as_os_str().to_owned(),
                ];
                forwarded.extend(args.drain(1..));
                project_gate::run(&forwarded)?
            }
            Some("style") => checks::run_style(&args[1..])?,
            _ => checks::run(&args)?,
        },
        "inspect" => {
            if args.first().is_some_and(|value| value == "session") {
                session::run(&args[1..])?
            } else {
                offline::run_inspect(&args)?
            }
        }
        "coord" => coord::run(&args)?,
        "profile" => {
            if args.first().is_some_and(|value| value == "results") {
                buffer::run(&args[1..])?
            } else {
                profile::run(&args)?
            }
        }
        "studio" => {
            if args.first().is_some_and(|value| value == "decode") {
                buffer::run(&args[1..])?
            } else {
                studio::run(&args)?
            }
        }
        "argon" => argon::run(&args)?,
        "scaffold" => scaffold::run(&args)?,
        "setup" => setup::run(&args)?,
        "hook" => hooks::run(&args)?,
        other => anyhow::bail!("unknown command family '{other}'\n{HELP}"),
    };
    Ok(code)
}
