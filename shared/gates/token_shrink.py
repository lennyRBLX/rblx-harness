#!/usr/bin/env python3
"""Deterministic token shortening for validated agent records.

Only allowlisted prose fields change. Code-like spans and exact schema fields
stay byte-exact. The replacement set is measured with o200k_base and kept
small enough to audit without a tokenizer dependency at runtime.
"""

import argparse
import os
import re
import sys


PROSE_FIELDS = {
    "fact": (2,),
    "issue": (2, 3),
    "finding": (3, 4),
    "debug": (2, 3),
    "class": (3,),
    "api": (5,),
    "enum": (3,),
    "house": (2,),
    "sample": (2,),
    "miss": (2,),
    "fix": (2, 3),
    "diag": (1, 2),
    "opt": (2, 3),
    "clear": (2,),
}

# Prose pattern -> replacement. Each entry saves at least one o200k_base token in the
# fixed corpus. Ambiguous slash shorthand is disabled because ordinary words
# joined by `and` can also be a Luau expression.
CONTRACTIONS = (
    (re.compile(r"(?<![\w/])is not allowed to(?![\w/])"), "must not"),
    (re.compile(r"(?<![\w/])are not allowed to(?![\w/])"), "must not"),
    (re.compile(r"(?<![\w/])is required to(?![\w/])"), "must"),
    (re.compile(r"(?<![\w/])are required to(?![\w/])"), "must"),
    (re.compile(r"(?<![\w/])is able to(?![\w/])"), "can"),
    (re.compile(r"(?<![\w/])are able to(?![\w/])"), "can"),
    (re.compile(r"(?<![\w/])in order to(?![\w/])"), "to"),
)
SHORTHAND = (
    (re.compile(r"(?<![\w/])dexterity(?![\w/])"), "dex"),
)
EXACT_PROTECTED = re.compile(
    r"```.*?```|`[^`\n]*`|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'",
    re.DOTALL,
)
# Conservative Luau lexical shapes. These protect code-like spans without
# trying to parse natural language as a complete program. Ambiguous boolean
# phrases are protected because `input and output` is also valid Luau.
LUAU_PROTECTED = (
    re.compile(r"--.*$"),
    re.compile(r"\b(?:local|return|if|elseif|while|for|repeat|until|function|type|export)\b.*$"),
    re.compile(r"\b[A-Za-z_]\w*(?:[.:][A-Za-z_]\w*)*\s*(?:[+\-*/%]?=)(?!=).*?$"),
    re.compile(
        r"\b(?:not\s+)?[A-Za-z_]\w*(?:[.:][A-Za-z_]\w*)*"
        r"(?:\s*(?:~=|==|<=|>=|<|>)\s*(?:nil|true|false|-?\d+(?:\.\d+)?|[A-Za-z_]\w*(?:[.:][A-Za-z_]\w*)*))?"
        r"(?:\s+(?:and|or)\s+(?:not\s+)?[A-Za-z_]\w*(?:[.:][A-Za-z_]\w*)*"
        r"(?:\s*(?:~=|==|<=|>=|<|>)\s*(?:nil|true|false|-?\d+(?:\.\d+)?|[A-Za-z_]\w*(?:[.:][A-Za-z_]\w*)*))?)+"
    ),
    re.compile(r"\b[A-Za-z_]\w*(?:[.:][A-Za-z_]\w*)+(?:\s*\([^()\n]*\))?"),
    re.compile(r"\b[A-Za-z_]\w*\s*\([^()\n]*\)"),
    re.compile(r"\b[A-Za-z_]\w*\s*:\s*[A-Z][A-Za-z0-9_.?]*(?:\s*[|&]\s*[A-Z][A-Za-z0-9_.?]*)*"),
)
RECORD_TOKEN = re.compile(
    r"^(?:fact|issue|finding|debug|class|api|enum|doc|house|sample|miss|fix|diag|opt|clear|wait|ENV|rule|-?\d+)$"
)
SOURCE_SUFFIXES = (".lua", ".luau")


def _split_record(line):
    fields = []
    depth = 0
    current = ""
    for char in line:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "|" and depth == 0:
            fields.append(current)
            current = ""
        else:
            current += char
    fields.append(current)
    return fields


def _protected_spans(value):
    spans = [(match.start(), match.end()) for match in EXACT_PROTECTED.finditer(value)]
    for pattern in LUAU_PROTECTED:
        spans.extend((match.start(), match.end()) for match in pattern.finditer(value))
    if not spans:
        return []
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _contract(value, replacements):
    for pattern, replacement in replacements:
        value = pattern.sub(replacement, value)
    return value


def shrink_prose(value, spoken=False):
    """Shorten prose while leaving quoted and Luau-like spans byte-exact."""
    replacements = CONTRACTIONS if spoken else CONTRACTIONS + SHORTHAND
    spans = _protected_spans(value)
    if not spans:
        return _contract(value, replacements)
    output = []
    cursor = 0
    for start, end in spans:
        output.append(_contract(value[cursor:start], replacements))
        output.append(value[start:end])
        cursor = end
    output.append(_contract(value[cursor:], replacements))
    return "".join(output)


def validate_output_path(path):
    """Reject lexical or resolved Luau source destinations."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("output path is absent")
    lexical = os.path.abspath(os.path.expanduser(path))
    resolved = os.path.realpath(lexical)
    if lexical.casefold().endswith(SOURCE_SUFFIXES) or resolved.casefold().endswith(SOURCE_SUFFIXES):
        raise ValueError("token shortening must not write .lua or .luau files")
    return lexical


def shrink_return(agent, text, spoken=False):
    """Normalize allowlisted fields in an already validated agent return."""
    if not isinstance(text, str):
        return text
    lines = text.split("\n")
    for line_index, line in enumerate(lines[1:], start=1):
        fields = _split_record(line)
        indexes = PROSE_FIELDS.get(fields[0]) if fields else None
        if not indexes:
            continue
        for field_index in indexes:
            if field_index < len(fields):
                fields[field_index] = shrink_prose(fields[field_index], spoken=spoken)
        lines[line_index] = "|".join(fields)
    return "\n".join(lines)


def normalize_schema(text):
    """Repair safe delimiter padding and void fields before validation."""
    if not isinstance(text, str):
        return text
    lines = text.split("\n")
    for line_index, line in enumerate(lines[1:], start=1):
        fields = _split_record(line)
        if len(fields) < 2 or not RECORD_TOKEN.fullmatch(fields[0].strip()):
            continue
        lines[line_index] = "|".join(field.strip() or "void" for field in fields)
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shorten a validated agent return")
    parser.add_argument("--agent", required=True, choices=("debugger", "optimizer", "researcher", "reviewer"))
    parser.add_argument("--spoken", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    shortened = shrink_return(args.agent, sys.stdin.read(), spoken=args.spoken)
    if args.output:
        try:
            output = validate_output_path(args.output)
            with open(output, "w", encoding="utf-8") as handle:
                handle.write(shortened)
        except (OSError, ValueError) as error:
            sys.stderr.write("token-shrink: BLOCKED %s\n" % error)
            return 2
    else:
        sys.stdout.write(shortened)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
