#!/usr/bin/env python3
"""Check plan structure in files and Stop responses; snapshot edits at PreToolUse."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


MARKER = "<!-- rblx-plan -->"
SECTIONS = ("Architecture", "APIs", "Luau Types", "Milestones")
MILESTONE = re.compile(r"^### (M\d{2,}) — (.+)$", re.MULTILINE)
PLAN_NAME = re.compile(r"(?:^|[._ -])plan(?:[._ -]|$)", re.IGNORECASE)
NEGATIVE = re.compile(r"^(?:do not|don't|never|avoid|refrain from)\b", re.IGNORECASE)
CACHE = Path.home() / ".cache/harness/plan-gate"
FORMAT = Path(__file__).resolve().parents[1] / "PLAN.md"
SKIP = {".git", ".codex", ".agents", "node_modules", "rblx-harness"}


def prose(text):
    """Keep line positions while excluding fenced code from structural checks."""
    result, fence = [], None
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            result.append("")
        elif match:
            fence = match[1]
            result.append("")
        else:
            result.append(line)
    return "\n".join(result)


def is_plan(text, path=""):
    visible = prose(text)
    return bool(PLAN_NAME.search(Path(path).stem) or MARKER in visible
                or re.search(r"^# (?:.*\b)?Plan\s*$", visible, re.MULTILINE | re.IGNORECASE))


def unwrap(text):
    match = re.fullmatch(r"\s*<proposed_plan>\s*([\s\S]*?)\s*</proposed_plan>\s*", text)
    return match[1] if match else text.strip()


def validate(text):
    text = unwrap(text)
    visible = prose(text)
    errors = []
    if not text.startswith(MARKER + "\n# "):
        errors.append("Start with the rblx-plan marker and one deliverable title.")
    if len(re.findall(r"^# .+", visible, re.MULTILINE)) != 1:
        errors.append("Use one deliverable title.")
    headers = list(re.finditer(r"^## (.+)$", visible, re.MULTILINE))
    if [match[1] for match in headers] != list(SECTIONS):
        errors.append("Use sections in order: Architecture, APIs, Luau Types, Milestones.")
        return errors
    introduction = visible[:headers[0].start()]
    if not re.search(r"^Deliver .+\.$\nStore evidence at `[^`\n]+`\.$", introduction, re.MULTILINE):
        errors.append("Write Deliver and Store evidence at lines in template order.")
    sections = {}
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(visible)
        sections[header[1]] = visible[header.end():end].strip()
    for name in ("Architecture", "APIs"):
        if not sections[name]:
            errors.append("Fill %s or use —." % name)
        if re.search(r"^#{3,} ", sections[name], re.MULTILINE):
            errors.append("Keep %s within its template section." % name)
    if sections["APIs"] != "—":
        for row in sections["APIs"].splitlines():
            if row.strip() and not re.match(r"^- Use `[^`]+` .+; review .+", row):
                errors.append("List APIs as Use `API/signature` with caller/phase, behavior and a review reference.")
                break
    types = text.split("## Luau Types\n", 1)[-1].split("## Milestones\n", 1)[0].strip()
    if types != "—" and not re.fullmatch(r"```luau\s*\n\S[\s\S]*?\n```", types):
        errors.append("Declare Luau Types in one luau fence or use —.")
    milestones = sections["Milestones"]
    matches = list(MILESTONE.finditer(milestones))
    ids = [match[1] for match in matches]
    if len(ids) != len(set(ids)):
        errors.append("Assign each milestone a unique stable ID.")
    if not matches and milestones != "Complete.":
        errors.append("Add M01 — Deliverable milestones or write Complete.")
    if matches and milestones[:matches[0].start()].strip():
        errors.append("Start Milestones with its first milestone heading.")
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(milestones)
        body = milestones[match.end():end]
        fields = re.findall(r"^(Requires|Context|Write|Complete): (.+)$", body, re.MULTILINE)
        if [name for name, _ in fields] != ["Requires", "Context", "Write", "Complete"]:
            errors.append("%s: Fill Requires, Context, Write and Complete in order." % match[1])
        actions = re.findall(r"^(\d+)\. (.+)$", body, re.MULTILINE)
        if not actions or [int(number) for number, _ in actions] != list(range(1, len(actions) + 1)):
            errors.append("%s: Number actions consecutively from 1." % match[1])
        if not any(action.startswith("Verify ") for _, action in actions):
            errors.append("%s: Add a Verify action with acceptance and responsibility." % match[1])
        if actions:
            start = re.search(r"^\d+\. ", body, re.MULTILINE).start()
            write = re.search(r"^Write: .+$", body, re.MULTILINE)
            complete = re.search(r"^Complete: .+$", body, re.MULTILINE)
            if not write or not complete or not (write.end() < start < complete.start()) or body[complete.end():].strip():
                errors.append("%s: Place actions after Write and finish with Complete." % match[1])
        if re.search(r"^###", body, re.MULTILINE):
            errors.append("%s: Use ### M01 — Deliverable for each milestone heading." % match[1])
    for line in visible.splitlines():
        action = re.sub(r"^\s*(?:[-*+] |\d+\. )", "", line).lstrip()
        if NEGATIVE.match(action):
            errors.append("Use an affirmative command: %s" % line.strip()[:100])
        if re.match(r"^\s*[-*+] \[[xX]\]", line):
            errors.append("Archive verified completed milestones and remove their blocks.")
    template_prose = re.sub(r"`+[^`\n]*`+", "", visible)
    if re.search(r"<(?!https?://)[A-Za-z][^<>\n]*>", template_prose):
        errors.append("Replace template placeholders with task facts.")
    return errors


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            timeout=10, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    if result.returncode:
        raise ValueError("Read the project Git inventory: " + os.fsdecode(result.stderr).strip()[:180])
    return os.fsdecode(result.stdout)


def snapshot(cwd):
    root = Path(git(cwd, "rev-parse", "--show-toplevel").strip())
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.md")
    files = {}
    for name in sorted(set(names.split("\0")) - {""}):
        path = root / name
        if SKIP.intersection(Path(name).parts) or path.is_symlink() or not path.is_file() or path.resolve() == FORMAT:
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            continue
        text = path.read_text(encoding="utf-8")
        files[name] = {"hash": hashlib.sha256(text.encode()).hexdigest(), "plan": is_plan(text, name),
                       "ids": [list(item) for item in MILESTONE.findall(prose(text))] if is_plan(text, name) else []}
    return str(root), files


def state_path(payload):
    if not all(isinstance(payload.get(key), str) and payload[key] for key in ("cwd", "session_id", "turn_id")):
        return None
    key = str(Path(payload["cwd"]).resolve()) + "\0" + payload["session_id"]
    return CACHE / (hashlib.sha256(key.encode()).hexdigest() + ".json")


def read_state(path):
    return json.loads(path.read_text()) if path and path.exists() else {}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".plan-")
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(state, handle)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def observe(payload):
    """Capture the primary turn before its first local tool, including opaque shells."""
    path = state_path(payload)
    if not path or payload.get("agent_type") or payload.get("agent_id"):
        return 0
    try:
        state = read_state(path)
        if state.get("turn") != payload["turn_id"]:
            root, files = snapshot(payload["cwd"])
            for name in state.get("pending", []):
                if name in state.get("files", {}):
                    files[name] = state["files"][name]
            state.update(turn=payload["turn_id"], root=root, files=files)
            save_state(path, state)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.stderr.write("plan-gate: %s\n" % error)
        return 2
    return 0


def check_receipts(text, previous, root):
    ids = {item[0] for item in MILESTONE.findall(prose(text))}
    removed = {item[0] for item in previous.get("ids", [])} - ids
    if not removed:
        return []
    evidence = re.search(r"^Store evidence at `([^`\n]+)`\.$", text, re.MULTILINE)
    if not evidence:
        return ["Preserve the evidence directory for removed milestone receipts."]
    errors = []
    for milestone in sorted(removed):
        receipt = (Path(root) / evidence[1] / (milestone + ".md")).resolve()
        if not receipt.is_relative_to(Path(root).resolve()) or not receipt.is_file():
            errors.append("Save the %s completion receipt inside the project evidence directory." % milestone)
            continue
        archived = receipt.read_text(encoding="utf-8")
        if (not re.search(r"^Revision: \S.+$", archived, re.MULTILINE)
                or not re.search(r"^Evidence: \S.+$", archived, re.MULTILINE)
                or milestone not in {item[0] for item in MILESTONE.findall(prose(archived))}):
            errors.append("%s: Archive the milestone block with Revision and Evidence fields." % milestone)
    return errors


def evaluate(payload):
    errors = []
    path = state_path(payload)
    state = {}
    try:
        state = read_state(path)
        message = payload.get("last_assistant_message") or ""
        # Plan Mode also contains questions/status replies; validate deliverables only.
        response_plan = ("<proposed_plan>" in message or is_plan(message)
                         or (payload.get("permission_mode") == "plan"
                             and re.search(r"^(?:# |\d+\. )", prose(message), re.MULTILINE))
                         or state.get("response_pending", False))
        if response_plan:
            findings = validate(message)
            errors.extend("response: " + item for item in findings)
            state["response_pending"] = bool(findings)
        pending = set(state.get("pending", []))
        if state.get("files") is not None and state.get("root"):
            root, current = snapshot(state["root"])
            before = state["files"]
            changed = {name for name in set(before) | set(current)
                       if before.get(name, {}).get("hash") != current.get(name, {}).get("hash")
                       and (before.get(name, {}).get("plan") or current.get(name, {}).get("plan"))}
            pending.update(changed)
            failed = []
            for name in sorted(pending):
                target = Path(root) / name
                if not target.is_file():
                    findings = ["Keep the plan with Complete. until its completion receipts are retained."]
                else:
                    text = target.read_text(encoding="utf-8")
                    findings = validate(text) + check_receipts(text, before.get(name, {}), root)
                if findings:
                    failed.append(name)
                    errors.extend(name + ": " + item for item in findings)
            state["pending"] = failed
        if errors and path:
            save_state(path, state)
        elif path and path.exists():
            path.unlink()
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        errors.append("Read plan validation inputs: %s" % error)
    if errors:
        reason = "Use $rblx-plan and shared/PLAN.md; correct plan findings [TOK1]:\n" + "\n".join(errors[:8])
        if payload.get("stop_hook_active"):
            result = {"continue": False, "stopReason": reason, "systemMessage": "Plan validation remains unresolved. " + reason}
        else:
            result = {"decision": "block", "reason": reason}
        print(json.dumps(result))
    else:
        print("{}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.getcwd())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--file", action="append")
    mode.add_argument("--stdin", action="store_true")
    mode.add_argument("--event", choices=("Stop",))
    args = parser.parse_args(argv)
    try:
        if args.event:
            payload = json.load(sys.stdin)
            if not isinstance(payload, dict):
                raise ValueError("Supply a hook object.")
            return evaluate(payload)
        documents = [("stdin", sys.stdin.read())] if args.stdin else [
            (name, (Path(args.root) / name).read_text(encoding="utf-8")) for name in args.file]
        errors = [name + ": " + error for name, text in documents for error in validate(text)]
    except (OSError, ValueError) as error:
        errors = [str(error)]
    if errors:
        for error in errors:
            sys.stderr.write("plan-gate|ERROR|%s\n" % error)
        return 2
    print("plan-gate|READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
