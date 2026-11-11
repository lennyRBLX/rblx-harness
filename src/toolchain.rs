use anyhow::{anyhow, bail, Context, Result};
use reqwest::blocking::Client;
use sha2::{Digest, Sha256};
use std::{
    env, fs,
    io::{Read, Seek, Write},
    path::{Path, PathBuf},
    process::Command,
    time::Duration,
};
use tempfile::NamedTempFile;
use zip::ZipArchive;

const TOOLS: [&str; 3] = ["lute", "argon", "luau-lsp"];
const MAX_ARCHIVE: u64 = 32 * 1024 * 1024;
const MAX_BINARY: u64 = 128 * 1024 * 1024;

#[derive(Clone, Copy)]
struct Release {
    tool: &'static str,
    version: &'static str,
    repository: &'static str,
    tag: &'static str,
    asset: &'static str,
    sha256: &'static str,
}

fn release(
    tool: &'static str,
    version: &'static str,
    repository: &'static str,
    tag: &'static str,
    asset: &'static str,
    sha256: &'static str,
) -> Release {
    Release {
        tool,
        version,
        repository,
        tag,
        asset,
        sha256,
    }
}

fn release_for(tool: &str, os: &str, arch: &str) -> Option<Release> {
    match (tool, os, arch) {
        ("lute", "linux", "aarch64") => Some(release(
            "lute",
            "1.0.0",
            "luau-lang/lute",
            "v1.0.0",
            "lute-linux-aarch64.zip",
            "78638a2013f38e365b31272b60853eb74dc0e0e425a71d806c4930ebd004b318",
        )),
        ("lute", "linux", "x86_64") => Some(release(
            "lute",
            "1.0.0",
            "luau-lang/lute",
            "v1.0.0",
            "lute-linux-x86_64.zip",
            "de7a6dab06b21df572c49257ec24a4cf1ecd54fb854de856aa377a1188255c95",
        )),
        ("lute", "macos", "aarch64") => Some(release(
            "lute",
            "1.0.0",
            "luau-lang/lute",
            "v1.0.0",
            "lute-macos-aarch64.zip",
            "6d120b5d2804e62ab2453565e755d022bd6902307cabcd0fedb4cdcbd4251e84",
        )),
        ("lute", "windows", "x86_64") => Some(release(
            "lute",
            "1.0.0",
            "luau-lang/lute",
            "v1.0.0",
            "lute-windows-x86_64.zip",
            "4f5de7cb1844d0df4e5796ad08d485ce7b6c35f7ba8d54046c7e7a12e7c28d92",
        )),
        ("argon", "linux", "aarch64") => Some(release(
            "argon",
            "2.0.29",
            "argon-rbx/argon",
            "2.0.29",
            "argon-2.0.29-linux-aarch64.zip",
            "06665d6aca4fc2d2f1532bf42d821a9eea4b8caeb4c3a7acb34e458e5e2f85a6",
        )),
        ("argon", "linux", "x86_64") => Some(release(
            "argon",
            "2.0.29",
            "argon-rbx/argon",
            "2.0.29",
            "argon-2.0.29-linux-x86_64.zip",
            "a0c19a38953934cd3229bdc189be0537b46026c8096ac2a9c93a9bdfcfcafe13",
        )),
        ("argon", "macos", "aarch64") => Some(release(
            "argon",
            "2.0.29",
            "argon-rbx/argon",
            "2.0.29",
            "argon-2.0.29-macos-aarch64.zip",
            "890bcb86e0e8d978101eefd78ce3a4c47156dfa4f59be95071efbe8d6047c042",
        )),
        ("argon", "macos", "x86_64") => Some(release(
            "argon",
            "2.0.29",
            "argon-rbx/argon",
            "2.0.29",
            "argon-2.0.29-macos-x86_64.zip",
            "1a8c78bc664e3d8d21fb4d92152c9d7c1a9a2e58c0561b07a6a0b099730f649c",
        )),
        ("argon", "windows", "aarch64") => Some(release(
            "argon",
            "2.0.29",
            "argon-rbx/argon",
            "2.0.29",
            "argon-2.0.29-windows-aarch64.zip",
            "5c4157ac7d2ab154a4e6c8b8d4622415994e6798cd01c8f72520d2b66073b64a",
        )),
        ("argon", "windows", "x86_64") => Some(release(
            "argon",
            "2.0.29",
            "argon-rbx/argon",
            "2.0.29",
            "argon-2.0.29-windows-x86_64.zip",
            "279d81a8fda4a0f08d7b79ade261a79bbe748e2ae97fc2e311906d1c0738fbed",
        )),
        ("luau-lsp", "linux", "aarch64") => Some(release(
            "luau-lsp",
            "1.70.1",
            "JohnnyMorganz/luau-lsp",
            "1.70.1",
            "luau-lsp-linux-arm64.zip",
            "6062345b95124ca937b8c324b74bc3fddb1d6919ba133c58f8b17945ce1acbc2",
        )),
        ("luau-lsp", "linux", "x86_64") => Some(release(
            "luau-lsp",
            "1.70.1",
            "JohnnyMorganz/luau-lsp",
            "1.70.1",
            "luau-lsp-linux-x86_64.zip",
            "1a2ea1ae4f98f8946cefd970a4b54853e11ab4775e6932faa7f60cf920346567",
        )),
        ("luau-lsp", "macos", "aarch64" | "x86_64") => Some(release(
            "luau-lsp",
            "1.70.1",
            "JohnnyMorganz/luau-lsp",
            "1.70.1",
            "luau-lsp-macos.zip",
            "7d3936e8dec6dc77547abd061d2e950da392562a5f94858b880f23dba50d84cd",
        )),
        ("luau-lsp", "windows", "x86_64") => Some(release(
            "luau-lsp",
            "1.70.1",
            "JohnnyMorganz/luau-lsp",
            "1.70.1",
            "luau-lsp-win64.zip",
            "64225b9738102a30de6ee09fb28e5a3827edc402ecf2a6364af570312468159f",
        )),
        _ => None,
    }
}

fn binary_path(dir: &Path, name: &str) -> PathBuf {
    dir.join(format!("{name}{}", env::consts::EXE_SUFFIX))
}

fn version_output(path: &Path) -> Option<String> {
    let output = Command::new(path).arg("--version").output().ok()?;
    if !output.status.success() {
        return None;
    }
    Some(format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    ))
}

fn version_matches(path: &Path, version: &str) -> bool {
    version_output(path).is_some_and(|output| output.contains(version))
}

fn from_path(name: &str, version: &str) -> Option<PathBuf> {
    let path = env::var_os("PATH")?;
    env::split_paths(&path)
        .map(|dir| binary_path(&dir, name))
        .find(|candidate| candidate.is_file() && version_matches(candidate, version))
}

fn ensure_bin_dir(root: &Path) -> Result<PathBuf> {
    let tools = root.join("tools");
    if fs::symlink_metadata(&tools).is_ok_and(|m| m.file_type().is_symlink()) {
        bail!(
            "refusing to install tools through symlink {}",
            tools.display()
        );
    }
    fs::create_dir_all(&tools)?;
    let bin = tools.join("bin");
    match fs::symlink_metadata(&bin) {
        Ok(meta) if meta.file_type().is_symlink() => {
            bail!(
                "refusing to install tools through symlink {}",
                bin.display()
            )
        }
        Ok(meta) if !meta.is_dir() => bail!("tool directory is not a directory: {}", bin.display()),
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => fs::create_dir_all(&bin)?,
        Err(error) => return Err(error.into()),
    }
    Ok(bin)
}

fn download_archive(client: &Client, release: Release) -> Result<NamedTempFile> {
    let url = format!(
        "https://github.com/{}/releases/download/{}/{}",
        release.repository, release.tag, release.asset
    );
    let mut response = client
        .get(&url)
        .send()
        .and_then(reqwest::blocking::Response::error_for_status)
        .with_context(|| format!("downloading {} from {}", release.tool, url))?;
    if response.url().scheme() != "https" {
        bail!("refusing non-HTTPS tool download: {}", response.url());
    }
    if response
        .content_length()
        .is_some_and(|size| size > MAX_ARCHIVE)
    {
        bail!("tool archive exceeds {} MiB", MAX_ARCHIVE / (1024 * 1024));
    }
    let mut archive = NamedTempFile::new()?;
    let mut hash = Sha256::new();
    let mut total = 0u64;
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let read = response.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        total = total.saturating_add(read as u64);
        if total > MAX_ARCHIVE {
            bail!("tool archive exceeds {} MiB", MAX_ARCHIVE / (1024 * 1024));
        }
        hash.update(&buffer[..read]);
        archive.write_all(&buffer[..read])?;
    }
    if total == 0 {
        bail!("empty tool archive from {}", url);
    }
    let actual = hex::encode(hash.finalize());
    if actual != release.sha256 {
        bail!(
            "SHA-256 mismatch for {} {}: expected {}, got {}",
            release.tool,
            release.version,
            release.sha256,
            actual
        );
    }
    archive.flush()?;
    archive.as_file().sync_all()?;
    archive.as_file_mut().rewind()?;
    Ok(archive)
}

fn install_release(client: &Client, bin: &Path, release: Release) -> Result<()> {
    let downloaded = download_archive(client, release)?;
    let mut zip = ZipArchive::new(downloaded.reopen()?)
        .with_context(|| format!("{} release is not a valid ZIP archive", release.tool))?;
    let expected = format!("{}{}", release.tool, env::consts::EXE_SUFFIX);
    let mut match_index = None;
    for index in 0..zip.len() {
        let file = zip.by_index(index)?;
        let basename = file
            .name()
            .rsplit(|character| character == '/' || character == '\\')
            .next()
            .unwrap_or("");
        if !file.is_dir() && basename.eq_ignore_ascii_case(&expected) {
            if match_index.replace(index).is_some() {
                bail!(
                    "{} archive contains multiple {} binaries",
                    release.tool,
                    expected
                );
            }
        }
    }
    let index =
        match_index.ok_or_else(|| anyhow!("{} binary is absent from release archive", expected))?;
    let mut file = zip.by_index(index)?;
    let uncompressed_size = file.size();
    if uncompressed_size == 0 || uncompressed_size > MAX_BINARY {
        bail!(
            "{} binary has an invalid size: {uncompressed_size}",
            release.tool
        );
    }
    let target = binary_path(bin, release.tool);
    let mut staged = NamedTempFile::new_in(bin)?;
    let copied = std::io::copy(&mut file, &mut staged)?;
    if copied != uncompressed_size {
        bail!("{} binary size changed while extracting", release.tool);
    }
    staged.flush()?;
    staged.as_file().sync_all()?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        staged
            .as_file()
            .set_permissions(fs::Permissions::from_mode(0o755))?;
    }
    staged.persist(&target).map_err(|error| error.error)?;
    if !version_matches(&target, release.version) {
        let detail = version_output(&target).unwrap_or_else(|| "version command failed".into());
        bail!(
            "installed {} did not report version {}; got {}",
            release.tool,
            release.version,
            detail.trim()
        );
    }
    Ok(())
}

pub fn install(root: &Path) -> Result<()> {
    let bin = ensure_bin_dir(root)?;
    let os = env::consts::OS;
    let arch = env::consts::ARCH;
    let mut plan = Vec::new();
    let mut path_tools = Vec::new();
    for name in TOOLS {
        let target = binary_path(&bin, name);
        let version = release_for(name, os, arch)
            .map(|release| release.version)
            .unwrap_or_else(|| match name {
                "lute" => "1.0.0",
                "argon" => "2.0.29",
                "luau-lsp" => "1.70.1",
                _ => unreachable!(),
            });
        let exists = match fs::symlink_metadata(&target) {
            Ok(meta) if meta.file_type().is_symlink() => {
                if version_matches(&target, version) {
                    println!("toolchain|PRESENT|{name}|{version}");
                    continue;
                }
                bail!("refusing to replace tool symlink {}", target.display());
            }
            Ok(meta) if !meta.is_file() => {
                bail!("tool path is not a regular file: {}", target.display())
            }
            Ok(_) => true,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
            Err(error) => return Err(error.into()),
        };
        if exists && version_matches(&target, version) {
            println!("toolchain|PRESENT|{name}|{version}");
            continue;
        }
        if let Some(release) = release_for(name, os, arch) {
            plan.push((release, target.exists()));
        } else if !exists && from_path(name, version).is_some() {
            path_tools.push((name, version));
        } else {
            bail!(
                "no pinned {name} release for {os}/{arch}; supported setup targets are macOS arm64, Linux arm64/x86_64, and Windows x86_64"
            );
        }
    }
    let client = if plan.is_empty() {
        None
    } else {
        Some(
            Client::builder()
                .user_agent("rblx-harness/setup")
                .timeout(Duration::from_secs(180))
                .build()?,
        )
    };
    for (release, replacing) in plan {
        if replacing {
            println!("toolchain|UPDATING|{}|{}", release.tool, release.version);
        } else {
            println!("toolchain|DOWNLOADING|{}|{}", release.tool, release.version);
        }
        install_release(client.as_ref().unwrap(), &bin, release)
            .with_context(|| format!("installing {} {}", release.tool, release.version))?;
        println!("toolchain|INSTALLED|{}|{}", release.tool, release.version);
    }
    for (name, version) in path_tools {
        println!("toolchain|PATH|{name}|{version}");
    }
    Ok(())
}
