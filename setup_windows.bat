@echo off
REM ============================================================================
REM setup_windows.bat - bring a Windows harness\ + project pair (or set) up to
REM the versions shipped in this zip, and repair everything Windows cannot
REM carry natively.
REM
REM This script may ship at the ROOT of the update zip or inside harness\:
REM     harness\setup_windows.bat
REM     <Project>\        (any directory holding a root .roblox is a project)
REM The zip is made straight from the macOS working copies, so the payload may
REM contain .git, .serena, a macOS lute binary, and package symlinks stored
REM however the zip tool chose - all of that is handled below.
REM
REM TWO MODES (chosen by whether you pass a target argument):
REM   IN PLACE (default, no argument): the extracted folder IS the workspace.
REM       Extract the zip over your existing lua\ folder (so your .git is kept),
REM       or into a fresh folder, then run this script from there. It repairs
REM       the extracted harness\ + projects directly; nothing is mirrored or
REM       deleted.
REM   MIRROR (pass a folder): sync the extracted harness\ + projects ONTO a
REM       separate existing set at that folder with robocopy /MIR (files added,
REM       updated, and deleted to match the zip), EXCLUDING from the copy and
REM       PRESERVING in the target each repo's .git, .roblox, .serena, __pycache__,
REM       bin\ runtimes, the dev's .claude\settings.local.json, and junction
REM       points (/XJ).
REM
REM What it does (both modes):
REM   1. (mirror only) mirrors payload harness\ and each project over the
REM      target copies.
REM   2. installs the exact Roblox Codex permission profile, selects it as the
REM      default, and preserves unrelated user settings.
REM   3. regenerates native Windows Claude + Codex hooks and project config
REM      from the harness canon. Project trust and exact hook approval remain
REM      human actions in Codex through /hooks. Config is repaired before any
REM      standalone agent file is installed, so legacy role tables cannot
REM      collide with the standalone definitions.
REM   4. repairs what zip transport mangles, per project: Claude and Codex
REM      agent defs become real copies of harness\claude\agents\*.md and
REM      harness\openai\agents\*.toml, both writer skills become real copies,
REM      default.project.json becomes a deterministic real copy of the selected
REM      place project, and the shared
REM      package-museum links become real byte-copies of the harness\packages
REM      museum (Windows cannot use the authoring-side symlinks - see
REM      :fix_packages; without this step the project does not build). The
REM      user-scope roblox-new-game and math-tool skills become regular copied
REM      directories. The math-tool installer also merges its owned user hooks
REM      and installs its sha256-pinned symbolic runtime.
REM   5. fetches the pinned Windows Lute v1.0.0 and luau-lsp 1.68.1 runtimes,
REM      with release-asset sha256 verification.
REM      Upgrades are deliberate - bump the pin, re-run the verify suite as
REM      the canary.
REM   6. sanity checks: Python, Codex, luau-lsp 1.68.1, argon on PATH - the
REM      GATE4 set.
REM   7. best-effort lint: style_assess over each project with the sanctioned
REM      museum ignores - doctrine governs house-authored code. On Windows the
REM      museum is byte-copies, so the symlink filter cannot skip it; the two
REM      ignore globs stand in. Best-effort only - the gates still run their
REM      own checks per write.
REM
REM Notes for the developer:
REM   - Your .git dirs are untouched: after this runs, git status shows exactly
REM     what changed. Undo anything with git restore.
REM   - .claude\agents, .claude\skills, and the museum names inside Packages\
REM     and Modules\ are gitignored by the scaffold, so git status stays clean
REM     after the fixup. Materialized links are never committed from Windows;
REM     they are the authoring side's symlinks.
REM   - If you have uncommitted local work, the script shows it and asks
REM     before overwriting. Commit or stash first to be safe.
REM
REM Usage:   setup_windows.bat [targetLuaRoot]
REM Default: (no argument) operate in place on the extracted folder.
REM          Pass a folder to mirror the extract onto a separate harness\ +
REM          project set there instead.
REM Either way harness\ and the projects must sit side by side under one
REM parent: that layout is load-bearing - project CLAUDE.md files @import
REM ..\harness\shared\CORE.md from the project root; the script acts wherever
REM you extracted the sibling directories.
REM ============================================================================
setlocal enabledelayedexpansion

set "SCRIPT_ROOT=%~dp0"
if exist "%SCRIPT_ROOT%shared\CORE.md" (
    REM setup_windows.bat is inside harness\; payload projects are its siblings.
    for %%D in ("%SCRIPT_ROOT%..") do set "PAYLOAD=%%~fD\"
    set "HARNESS_PAYLOAD=%SCRIPT_ROOT%"
) else (
    REM setup_windows.bat is beside harness\ at the extracted zip root.
    set "PAYLOAD=%SCRIPT_ROOT%"
    set "HARNESS_PAYLOAD=%SCRIPT_ROOT%harness\"
)
REM Default target is the extracted folder itself - operate IN PLACE. Pass a
REM different folder as the first argument to instead MIRROR the extract onto a
REM separate existing harness\ + project set (the old staging->target workflow).
set "TARGET=%~1"
if not defined TARGET set "TARGET=%PAYLOAD%"
REM strip a trailing backslash so the in-place test matches PAYLOAD (which %~dp0
REM always ends with one)
if "%TARGET:~-1%"=="\" set "TARGET=%TARGET:~0,-1%"

set "INPLACE="
if /i "%PAYLOAD%"=="%TARGET%\" set "INPLACE=1"

echo == payload: %PAYLOAD%
if defined INPLACE (
    echo == target:  %TARGET%  ^(in place^)
) else (
    echo == target:  %TARGET%  ^(mirror^)
)

if not exist "%HARNESS_PAYLOAD%shared\CORE.md" (
    echo ERROR: harness\shared\CORE.md is not available in or beside this script folder.
    exit /b 2
)

REM ---- discover payload projects: .roblox is the sole managed-project signal --
set "PROJECTS="
for /d %%D in ("%PAYLOAD%*") do (
    if /i not "%%~nxD"=="harness" (
        if exist "%%~fD\.roblox" set "PROJECTS=!PROJECTS! %%~nxD"
    )
)
if not defined PROJECTS (
    echo NOTE: no project payload beside this script - only harness\ will be handled.
)
echo == projects:%PROJECTS%

if not exist "%TARGET%\" (
    echo ERROR: target root %TARGET% does not exist. Pass the folder that
    echo        contains your existing harness\ and projects as the first argument.
    exit /b 2
)
if not defined INPLACE (
    if not exist "%TARGET%\harness\" echo NOTE: %TARGET%\harness does not exist yet - it will be created fresh.
    for %%P in (%PROJECTS%) do (
        if not exist "%TARGET%\%%P\" echo NOTE: %TARGET%\%%P does not exist yet - it will be created fresh.
    )
)

REM ---- show local uncommitted work before overwriting -------------------------
where git >nul 2>nul
if not errorlevel 1 (
    call :show_dirty "%TARGET%\harness"
    for %%P in (%PROJECTS%) do call :show_dirty "%TARGET%\%%P"
)
REM in place with no repo = a fresh extract, not the dev's existing checkout:
REM the repairs still produce a buildable tree, but there is no version history
REM to fall back on. Extract over the existing lua\ folder to keep .git.
if defined INPLACE (
    for %%P in (%PROJECTS%) do (
        if not exist "%TARGET%\%%P\.git\" echo WARN: no %%P\.git here - this looks like a fresh extract, not your existing repo. The result builds, but your git history is not present. Extract over your existing lua\ folder to keep it.
    )
)

echo.
if defined INPLACE (
    echo This repairs the extracted harness\ and projects IN PLACE: materializes
    echo the package-museum links to real copies, rebuilds .claude links and
    echo default.project.json, and fetches the Lute runtime. Any existing .git is
    echo untouched. Nothing is deleted - files removed upstream are not pruned.
) else (
    echo This MIRRORS the zip's harness\ and projects over the target copies at
    echo %TARGET%. Files not in the zip are DELETED from the target - except
    echo .git, .roblox, .serena, __pycache__, bin, .DS_Store, settings.local.json, and
    echo junction points, which are never copied and never deleted.
)
choice /C YN /M "Continue"
if errorlevel 2 exit /b 1

REM ---- 1. mirror (skipped when operating in place) -----------------------------
if defined INPLACE goto :after_mirror
echo.
echo == syncing harness...
call :mirror "%HARNESS_PAYLOAD%" "%TARGET%\harness"
if errorlevel 1 exit /b 2
for %%P in (%PROJECTS%) do (
    echo == syncing %%P...
    call :mirror "%PAYLOAD%%%P" "%TARGET%\%%P"
    if errorlevel 1 exit /b 2
)
:after_mirror

REM .roblox is excluded from /MIR deletion and recreated from a managed payload
REM when the target is new. Existing target sentinels are never overwritten.
for %%P in (%PROJECTS%) do call :preserve_sentinel "%%P"

REM ---- detect Python (the package repair below needs it) -----------------------
set "PY="
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    echo ERROR: no Python launcher found - Python 3 is required to install the
    echo        Codex permission profile and run the harness gates.
    exit /b 2
)

REM ---- 2. exact user Codex permission profile ----------------------------------
echo.
%PY% "%TARGET%\harness\openai\setup\permissions_harness.py" --install
if errorlevel 1 (
    echo ERROR: the Roblox Codex permission profile was not installed.
    exit /b 2
)

REM ---- 3. regenerate config/hooks before standalone Codex agents ----------------
echo.
echo == regenerating Windows hooks and project config...
REM When hook bytes change, windows.py reports: open /hooks and approve them.
set "CODEX_PROJECT_ARGS="
for %%P in (%PROJECTS%) do set "CODEX_PROJECT_ARGS=!CODEX_PROJECT_ARGS! --project "%TARGET%\%%P""
%PY% "%TARGET%\harness\openai\setup\windows.py" --harness "%TARGET%\harness" !CODEX_PROJECT_ARGS!
if errorlevel 1 (
    echo ERROR: Codex and Claude integration files were not generated.
    exit /b 2
)

REM ---- 4. repair links the zip transport mangles --------------------------------
echo.
set "DISCOVERY_CHANGED="
for %%P in (%PROJECTS%) do (
    echo == repairing %%P Claude/Codex links and default.project.json...
    for %%A in (reviewer debugger optimizer researcher maintainer) do (
        if not exist "%TARGET%\%%P\.claude\agents\%%A.md" set "DISCOVERY_CHANGED=1"
        if exist "%TARGET%\%%P\.claude\agents\%%A.md" fc /b "%TARGET%\%%P\.claude\agents\%%A.md" "%TARGET%\harness\claude\agents\%%A.md" >nul 2>nul || set "DISCOVERY_CHANGED=1"
        if not exist "%TARGET%\%%P\.codex\agents\%%A.toml" set "DISCOVERY_CHANGED=1"
        if exist "%TARGET%\%%P\.codex\agents\%%A.toml" fc /b "%TARGET%\%%P\.codex\agents\%%A.toml" "%TARGET%\harness\openai\agents\%%A.toml" >nul 2>nul || set "DISCOVERY_CHANGED=1"
        call :fix_claude_agent "%%P" "%%A"
        if errorlevel 1 exit /b 2
        call :fix_codex_agent "%%P" "%%A"
        if errorlevel 1 exit /b 2
    )
    if not exist "%TARGET%\%%P\.claude\skills\roblox-writer\SKILL.md" set "DISCOVERY_CHANGED=1"
    if exist "%TARGET%\%%P\.claude\skills\roblox-writer\SKILL.md" fc /b "%TARGET%\%%P\.claude\skills\roblox-writer\SKILL.md" "%TARGET%\harness\shared\skills\roblox-writer\SKILL.md" >nul 2>nul || set "DISCOVERY_CHANGED=1"
    if not exist "%TARGET%\%%P\.agents\skills\roblox-writer\SKILL.md" set "DISCOVERY_CHANGED=1"
    if exist "%TARGET%\%%P\.agents\skills\roblox-writer\SKILL.md" fc /b "%TARGET%\%%P\.agents\skills\roblox-writer\SKILL.md" "%TARGET%\harness\shared\skills\roblox-writer\SKILL.md" >nul 2>nul || set "DISCOVERY_CHANGED=1"
    if not exist "%TARGET%\%%P\.agents\skills\roblox-writer\agents\openai.yaml" set "DISCOVERY_CHANGED=1"
    if exist "%TARGET%\%%P\.agents\skills\roblox-writer\agents\openai.yaml" fc /b "%TARGET%\%%P\.agents\skills\roblox-writer\agents\openai.yaml" "%TARGET%\harness\openai\skills\roblox-writer\agents\openai.yaml" >nul 2>nul || set "DISCOVERY_CHANGED=1"
    if exist "%TARGET%\%%P\CLAUDE.md" copy /y "%TARGET%\%%P\CLAUDE.md" "%TEMP%\harness-%%P-claude.before" >nul
    if not exist "%TARGET%\%%P\CLAUDE.md" set "DISCOVERY_CHANGED=1"
    if exist "%TARGET%\%%P\AGENTS.md" copy /y "%TARGET%\%%P\AGENTS.md" "%TEMP%\harness-%%P-agents.before" >nul
    if not exist "%TARGET%\%%P\AGENTS.md" set "DISCOVERY_CHANGED=1"
    call :fix_skill "%%P"
    call :fix_default_project "%%P"
    if errorlevel 1 exit /b 2
    %PY% "%TARGET%\harness\shared\skills\roblox-new-game\scripts\scaffold.py" refresh-instructions --root "%TARGET%\%%P"
    if errorlevel 1 (
        echo ERROR: %%P CLAUDE.md and AGENTS.md were not refreshed.
        exit /b 2
    )
    if exist "%TEMP%\harness-%%P-claude.before" fc /b "%TEMP%\harness-%%P-claude.before" "%TARGET%\%%P\CLAUDE.md" >nul 2>nul || set "DISCOVERY_CHANGED=1"
    if exist "%TEMP%\harness-%%P-agents.before" fc /b "%TEMP%\harness-%%P-agents.before" "%TARGET%\%%P\AGENTS.md" >nul 2>nul || set "DISCOVERY_CHANGED=1"
    del /q "%TEMP%\harness-%%P-claude.before" "%TEMP%\harness-%%P-agents.before" >nul 2>nul
    echo == materializing %%P package museum links as real copies...
    call :fix_packages "%%P"
)
if not exist "%USERPROFILE%\.agents\skills\roblox-new-game\SKILL.md" set "DISCOVERY_CHANGED=1"
if exist "%USERPROFILE%\.agents\skills\roblox-new-game\SKILL.md" fc /b "%USERPROFILE%\.agents\skills\roblox-new-game\SKILL.md" "%TARGET%\harness\shared\skills\roblox-new-game\SKILL.md" >nul 2>nul || set "DISCOVERY_CHANGED=1"
if not exist "%USERPROFILE%\.agents\skills\roblox-new-game\agents\openai.yaml" set "DISCOVERY_CHANGED=1"
if exist "%USERPROFILE%\.agents\skills\roblox-new-game\agents\openai.yaml" fc /b "%USERPROFILE%\.agents\skills\roblox-new-game\agents\openai.yaml" "%TARGET%\harness\openai\skills\roblox-new-game\agents\openai.yaml" >nul 2>nul || set "DISCOVERY_CHANGED=1"
if not exist "%USERPROFILE%\.agents\skills\math-tool\SKILL.md" set "DISCOVERY_CHANGED=1"
if exist "%USERPROFILE%\.agents\skills\math-tool\SKILL.md" fc /b "%USERPROFILE%\.agents\skills\math-tool\SKILL.md" "%TARGET%\harness\shared\skills\math-tool\SKILL.md" >nul 2>nul || set "DISCOVERY_CHANGED=1"
if not exist "%USERPROFILE%\.claude\skills\math-tool\SKILL.md" set "DISCOVERY_CHANGED=1"
if exist "%USERPROFILE%\.claude\skills\math-tool\SKILL.md" fc /b "%USERPROFILE%\.claude\skills\math-tool\SKILL.md" "%TARGET%\harness\shared\skills\math-tool\SKILL.md" >nul 2>nul || set "DISCOVERY_CHANGED=1"
call :fix_user_skill
if errorlevel 1 exit /b 2

REM ---- 5. pinned Windows toolchain ------------------------------------------------
echo.
%PY% "%TARGET%\harness\openai\setup\windows.py" --harness "%TARGET%\harness" --toolchain-only
if errorlevel 1 (
    echo ERROR: pinned Windows toolchain installation failed.
    exit /b 2
)

REM ---- 6. sanity checks ------------------------------------------------------------
echo.
echo == hooks use the detected Python executable with bytecode disabled.

set "LSPVER="
for /f "delims=" %%V in ('"%TARGET%\harness\tools\bin\luau-lsp.exe" --version 2^>nul') do set "LSPVER=%%V"
if "%LSPVER%"=="1.68.1" (
    echo == luau-lsp 1.68.1 - matches the harness pin.
) else (
    echo ERROR: bundled luau-lsp version "%LSPVER%" does not match 1.68.1.
    exit /b 2
)
where argon >nul 2>nul
if errorlevel 1 (
    echo WARN: argon is not on PATH - boot_smoke needs its sourcemap and Studio
    echo       sync runs through it.
)

REM ---- 7. verify ---------------------------------------------------------------------
if not defined PY goto :report
echo.
echo == style_assess with the sanctioned museum ignores - doctrine governs house code...
for %%P in (%PROJECTS%) do (
    if exist "%TARGET%\%%P\shared\src\" (
        %PY% "%TARGET%\harness\tools\style_assess\style_assess.py" --root "%TARGET%\%%P" ^
            --ignore "**/ReplicatedStorage/Packages/**" --ignore "**/ServerScriptService/Modules/**" ^
            shared/ places/
        if errorlevel 1 (
            echo WARN: style_assess reported findings or a setup error in %%P - the
            echo       machine floor needs argon and luau-lsp on PATH and the lute
            echo       runtime above.
        ) else (
            echo    %%P clean.
        )
    )
)

:report
echo.
echo == setup complete.
echo == Roblox is the default permission mode.
if defined DISCOVERY_CHANGED echo == agent, skill, or instruction bytes changed; retry host discovery and continue this task.
where git >nul 2>nul
if not errorlevel 1 (
    echo == what this update changed - per repo git status:
    if exist "%TARGET%\harness\.git\" git -C "%TARGET%\harness" status --short
    for %%P in (%PROJECTS%) do (
        if exist "%TARGET%\%%P\.git\" git -C "%TARGET%\%%P" status --short
    )
    echo    .claude and museum entries are gitignored by the scaffold, so a
    echo    clean status is expected. Anything else showing changed is real.
    echo    Do not commit materialized links from Windows; they are macOS-
    echo    authoring links.
)
exit /b 0

REM ============================ subroutines ====================================

:show_dirty
if not exist "%~1\.git\" exit /b 0
set "DIRTY="
for /f "delims=" %%L in ('git -C "%~1" status --porcelain 2^>nul') do set "DIRTY=1"
if defined DIRTY (
    echo.
    echo WARN: %~1 has uncommitted local changes that the sync may OVERWRITE:
    git -C "%~1" status --short
)
exit /b 0

:mirror
robocopy "%~1" "%~2" /MIR /XJ /XD .git .serena __pycache__ bin /XF .roblox .DS_Store settings.local.json /NFL /NDL /NJH /NP
if errorlevel 8 (
    echo ERROR: robocopy failed syncing %~2 - see output above.
    exit /b 1
)
exit /b 0

:preserve_sentinel
if not exist "%TARGET%\%~1\.roblox" type nul > "%TARGET%\%~1\.roblox"
exit /b 0

:fix_claude_agent
set "T=%TARGET%\%~1\.claude\agents\%~2.md"
if not exist "%TARGET%\%~1\.claude\agents\" md "%TARGET%\%~1\.claude\agents" >nul 2>nul
if exist "%T%" del /f "%T%" >nul 2>nul
copy /y "%TARGET%\harness\claude\agents\%~2.md" "%T%" >nul
if errorlevel 1 (
    echo ERROR: could not install Claude agent %~2 for %~1.
    exit /b 1
)
exit /b 0

:fix_codex_agent
set "T=%TARGET%\%~1\.codex\agents\%~2.toml"
if not exist "%TARGET%\%~1\.codex\agents\" md "%TARGET%\%~1\.codex\agents" >nul 2>nul
if exist "%T%" del /f "%T%" >nul 2>nul
copy /y "%TARGET%\harness\openai\agents\%~2.toml" "%T%" >nul
if errorlevel 1 (
    echo ERROR: could not install Codex agent %~2 for %~1.
    exit /b 1
)
exit /b 0

:fix_skill
set "T=%TARGET%\%~1\.claude\skills\roblox-writer"
if not exist "%TARGET%\%~1\.claude\skills\" md "%TARGET%\%~1\.claude\skills" >nul 2>nul
if exist "%T%\" rmdir /s /q "%T%" >nul 2>nul
if exist "%T%" del /f "%T%" >nul 2>nul
xcopy /E /I /Y "%TARGET%\harness\shared\skills\roblox-writer" "%T%" >nul
REM Codex discovers the same SKILL.md format at .agents\skills
set "T=%TARGET%\%~1\.agents\skills\roblox-writer"
if not exist "%TARGET%\%~1\.agents\skills\" md "%TARGET%\%~1\.agents\skills" >nul 2>nul
if exist "%T%\" rmdir /s /q "%T%" >nul 2>nul
if exist "%T%" del /f "%T%" >nul 2>nul
md "%T%\agents" >nul 2>nul
copy /y "%TARGET%\harness\shared\skills\roblox-writer\SKILL.md" "%T%\SKILL.md" >nul
copy /y "%TARGET%\harness\openai\skills\roblox-writer\agents\openai.yaml" "%T%\agents\openai.yaml" >nul
exit /b 0

:fix_user_skill
REM roblox-new-game is a user-scope skill - one copied directory per machine, not per
REM project. Misinstalling it into a project is what session-gate check #10
REM tests for.
set "T=%USERPROFILE%\.claude\skills\roblox-new-game"
if not exist "%USERPROFILE%\.claude\skills\" md "%USERPROFILE%\.claude\skills" >nul 2>nul
if exist "%T%\" rmdir /s /q "%T%" >nul 2>nul
if exist "%T%" del /f "%T%" >nul 2>nul
xcopy /E /I /Y "%TARGET%\harness\shared\skills\roblox-new-game" "%T%" >nul
set "T=%USERPROFILE%\.agents\skills\roblox-new-game"
if not exist "%USERPROFILE%\.agents\skills\" md "%USERPROFILE%\.agents\skills" >nul 2>nul
if exist "%T%\" rmdir /s /q "%T%" >nul 2>nul
if exist "%T%" del /f "%T%" >nul 2>nul
xcopy /E /I /Y "%TARGET%\harness\shared\skills\roblox-new-game" "%T%" >nul
if not exist "%T%\agents" md "%T%\agents" >nul 2>nul
copy /y "%TARGET%\harness\openai\skills\roblox-new-game\agents\openai.yaml" "%T%\agents\openai.yaml" >nul
if exist "%T%\" echo == user skill roblox-new-game materialized for Claude + Codex.
%PY% "%TARGET%\harness\openai\setup\math_tool.py" --install
if errorlevel 1 (
    echo ERROR: user math-tool skill, hooks, or pinned runtime was not installed.
    exit /b 1
)
exit /b 0

:fix_default_project
%PY% "%TARGET%\harness\shared\skills\roblox-new-game\scripts\scaffold.py" materialize-default --root "%TARGET%\%~1"
if errorlevel 1 (
    echo ERROR: deterministic default.project.json selection failed for %~1.
    exit /b 1
)
exit /b 0

:fix_packages
REM The project's shared package roots (ReplicatedStorage\Packages,
REM ServerScriptService\Modules) are per-file symlinks into harness\packages -
REM the museum lives in harness, edits happen there. Windows cannot USE those
REM links: a git checkout without Developer Mode / core.symlinks turns each
REM into a junk text file holding the link target, and zip transport mangles
REM them further, so the project will not build until they are materialized.
REM Re-emit the museum as real byte-copies. The Python path is authoritative:
REM it clears whatever mangled thing arrived (junk file, stale dir, reparse
REM point), copies the museum fresh, and preserves the scaffold-written
REM .luaurc plus any project-unique packages.
if defined PY (
    %PY% "%TARGET%\harness\shared\skills\roblox-new-game\scripts\scaffold.py" backfill --shared "%TARGET%\%~1\shared" --copy
    if not errorlevel 1 exit /b 0
    echo WARN: python backfill failed - falling back to robocopy /E.
)
REM Fallback (no Python): merge-copy the museum over the linked roots. /E adds
REM and overwrites without deleting, so .luaurc and project-unique packages
REM survive; it assumes the arriving links were dereferenced to real files by
REM the zip.
robocopy "%TARGET%\harness\packages\ReplicatedStorage\Packages" "%TARGET%\%~1\shared\src\ReplicatedStorage\Packages" /E /NFL /NDL /NJH /NJS /NP >nul
robocopy "%TARGET%\harness\packages\ServerScriptService\Modules" "%TARGET%\%~1\shared\src\ServerScriptService\Modules" /E /NFL /NDL /NJH /NJS /NP >nul
exit /b 0
