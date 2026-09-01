@echo off
setlocal

REM Run from a project's initialized .roblox-harness submodule.
set "HARNESS=%~dp0"
for %%D in ("%HARNESS%..") do set "PROJECT=%%~fD"

if not exist "%HARNESS%shared\CORE.md" (
    echo ERROR: this script must remain at the rblx-harness checkout root.
    exit /b 2
)
if not exist "%PROJECT%\.roblox" (
    echo ERROR: %PROJECT% is not a .roblox project.
    exit /b 2
)

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo ERROR: Python 3 is required.
    exit /b 2
)

%PY% "%HARNESS%openai\setup\permissions_harness.py" --install
if errorlevel 1 exit /b 2

%PY% "%HARNESS%openai\setup\windows.py" --harness "%HARNESS%" --project "%PROJECT%"
if errorlevel 1 exit /b 2

for %%A in (reviewer debugger optimizer researcher maintainer) do (
    if not exist "%PROJECT%\.claude\agents" md "%PROJECT%\.claude\agents"
    copy /y "%HARNESS%claude\agents\%%A.md" "%PROJECT%\.claude\agents\%%A.md" >nul
    if not exist "%PROJECT%\.codex\agents" md "%PROJECT%\.codex\agents"
    copy /y "%HARNESS%openai\agents\%%A.toml" "%PROJECT%\.codex\agents\%%A.toml" >nul
)

if exist "%PROJECT%\.claude\skills\roblox-writer" rmdir /s /q "%PROJECT%\.claude\skills\roblox-writer"
if not exist "%PROJECT%\.claude\skills" md "%PROJECT%\.claude\skills"
xcopy /E /I /Y "%HARNESS%shared\skills\roblox-writer" "%PROJECT%\.claude\skills\roblox-writer" >nul

if exist "%PROJECT%\.agents\skills\roblox-writer" rmdir /s /q "%PROJECT%\.agents\skills\roblox-writer"
md "%PROJECT%\.agents\skills\roblox-writer\agents" >nul 2>nul
copy /y "%HARNESS%shared\skills\roblox-writer\SKILL.md" "%PROJECT%\.agents\skills\roblox-writer\SKILL.md" >nul
copy /y "%HARNESS%openai\skills\roblox-writer\agents\openai.yaml" "%PROJECT%\.agents\skills\roblox-writer\agents\openai.yaml" >nul

%PY% "%HARNESS%shared\skills\roblox-new-game\scripts\scaffold.py" refresh-instructions --root "%PROJECT%"
if errorlevel 1 exit /b 2
%PY% "%HARNESS%shared\skills\roblox-new-game\scripts\scaffold.py" materialize-default --root "%PROJECT%"
if errorlevel 1 exit /b 2
%PY% "%HARNESS%shared\skills\roblox-new-game\scripts\scaffold.py" backfill --shared "%PROJECT%\shared" --copy
if errorlevel 1 exit /b 2

if exist "%USERPROFILE%\.claude\skills\roblox-new-game" rmdir /s /q "%USERPROFILE%\.claude\skills\roblox-new-game"
if not exist "%USERPROFILE%\.claude\skills" md "%USERPROFILE%\.claude\skills"
xcopy /E /I /Y "%HARNESS%shared\skills\roblox-new-game" "%USERPROFILE%\.claude\skills\roblox-new-game" >nul

if exist "%USERPROFILE%\.agents\skills\roblox-new-game" rmdir /s /q "%USERPROFILE%\.agents\skills\roblox-new-game"
md "%USERPROFILE%\.agents\skills\roblox-new-game\agents" >nul 2>nul
xcopy /E /I /Y "%HARNESS%shared\skills\roblox-new-game" "%USERPROFILE%\.agents\skills\roblox-new-game" >nul
copy /y "%HARNESS%openai\skills\roblox-new-game\agents\openai.yaml" "%USERPROFILE%\.agents\skills\roblox-new-game\agents\openai.yaml" >nul

%PY% "%HARNESS%openai\setup\math_tool.py" --install
if errorlevel 1 exit /b 2
if not exist "%USERPROFILE%\.agents\skills\math-tool\SKILL.md" exit /b 2
if not exist "%USERPROFILE%\.claude\skills\math-tool\SKILL.md" exit /b 2

%PY% "%HARNESS%openai\setup\windows.py" --harness "%HARNESS%" --toolchain-only
if errorlevel 1 exit /b 2

echo roblox-harness-windows^|READY^|project=%PROJECT%
exit /b 0
