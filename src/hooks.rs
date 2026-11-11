use anyhow::{anyhow, Result};
use std::ffi::OsString;

pub fn run(args: &[OsString]) -> Result<i32> {
    match args.first().and_then(|arg| arg.to_str()) {
        Some("coord") => crate::coord::run(&[OsString::from("hook")]),
        Some(other) => Err(anyhow!("unknown hooks command: {other}")),
        None => Err(anyhow!("missing hooks command")),
    }
}
