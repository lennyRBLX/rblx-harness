"""Narrow routing checks for known costly tool patterns; no session state.

This is a workflow guard, not a shell security parser. Dynamic commands stay
subject to CORE rules. An explicit reason exempts routing, never agent gates.
"""
import ast
import re
import shlex

LITERAL_CMD = re.compile(r'''\bcmd\s*:\s*("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''')
SUMMARY_FLAGS = {"--stat", "--numstat", "--shortstat", "--name-only", "--name-status",
                 "--check", "--summary", "--quiet", "--exit-code", "--raw", "--no-patch", "-s"}


def commands(payload):
    value = payload.get("tool_input", {})
    tool = str(payload.get("tool_name", "")).split(".")[-1].casefold()
    if isinstance(value, dict) and (tool.endswith("exec_command") or tool == "bash"):
        command = value.get("command", value.get("cmd"))
        return [command] if isinstance(command, str) else []
    if tool not in ("exec", "functions_exec"):
        return []
    source = value if isinstance(value, str) else value.get("code", "") if isinstance(value, dict) else ""
    found = []
    for match in LITERAL_CMD.finditer(source):
        try:
            found.append(ast.literal_eval(match[1]))
        except (SyntaxError, ValueError):
            pass
    return found


def segments(command):
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        parts, segment = [], []
        for token in lexer:
            if all(char in ";&|\n" for char in token):
                if segment:
                    parts.append(segment)
                segment = []
            else:
                segment.append(token)
        if segment:
            parts.append(segment)
        return parts
    except ValueError:
        return []


def reason(payload):
    if len(str(payload.get("harness_tool_reason") or "").strip()) >= 8:
        return ""
    api_queries = 0
    for command in commands(payload):
        for tokens in segments(command):
            assignments = []
            while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
                assignments.append(tokens.pop(0))
            if any(t.startswith("HARNESS_TOOL_REASON=") and len(t.split("=", 1)[1].strip()) >= 8 for t in assignments):
                continue
            if not tokens:
                continue
            if tokens[0] == "cat" and any(t.endswith((".luau", ".lua")) for t in tokens[1:]):
                return "whole Luau reads: use tools/context_pack.py read --file PATH; narrow rg/sed reads remain valid [TOOL3]"
            if tokens[0] == "git":
                index = 1
                while index < len(tokens) and tokens[index].startswith("-"):
                    takes_value = tokens[index] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env")
                    index += 2 if takes_value else 1
                if index < len(tokens) and tokens[index] == "diff":
                    options = tokens[index + 1:]
                    if "--" in options:
                        options = options[:options.index("--")]
                    patch_flags = {"-p", "-u", "--patch", "--patch-with-stat", "--patch-with-raw"}
                    if patch_flags.intersection(options) or not any(t.split("=", 1)[0] in SUMMARY_FLAGS for t in options):
                        return "review diffs: use tools/context_pack.py diff --path PATH (repeat --path); summary/check diffs remain valid [TOOL3]"
            for index, token in enumerate(tokens[:-1]):
                if token.endswith("api_dump.py") and tokens[index + 1] in ("access", "inventory", "behavior"):
                    api_queries += 1
    if api_queries > 1:
        return "combine API evidence with api_dump.py batch VERB QUERY ... [TOOL2]"
    return ""
