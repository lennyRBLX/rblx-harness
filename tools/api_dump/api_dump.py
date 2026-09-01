#!/usr/bin/env python3
"""api_dump — flat lookup over the Roblox API dump + creator-docs clone.

Reference verbs answer what a call IS; doc verbs answer what it is FOR.
Output is records, not a report: one record per line, pipe-delimited, fixed
field positions, `void` fills an empty field. The consumer is the researcher
agent — the schema lives in its def, never restated here.

  header   name|super|tags|sample|summary
  member   sig|ret|threadsafety|tags|sample|summary
  ops      op|a|b|ret|src
  docs     path|title|description
  ENV      ENV|cause|remedy

Exit codes: 0 ok · 2 crash · 3 environment precondition unmet.
Security-filtered by default: only Security.Read == "None" members surface;
--all lifts the filter for a deliberate lookup.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib  # noqa: E402

CACHE = gatelib.CACHE
DUMP_PATH = os.path.join(CACHE, "API-Dump.json")
DOCS_ROOT = os.path.join(CACHE, "creator-docs")
CONTENT = os.path.join(DOCS_ROOT, "content", "en-us")
ENGINE = os.path.join(CONTENT, "reference", "engine")
DOCS_INDEX = os.path.join(CACHE, "docs_index.json")
REFRESH_PATH = os.path.join(CACHE, "corpus-refresh.json")
SAMPLES_DIR = os.path.join(CACHE, "samples")
GLOBALS_PATH = os.path.join(CACHE, "api_globals.luau")
DUMP_URL = "https://raw.githubusercontent.com/MaximumADHD/Roblox-Client-Tracker/roblox/API-Dump.json"
DOCS_URL = "https://github.com/Roblox/creator-docs"
OVERLAY_PATH = os.path.join(HERE, "house_overlay.txt")

# class tags carried; member tags carried. CustomLuaState and NotBrowsable are
# dropped deliberately — dropping a tag never drops a member.
CLASS_TAGS = {"NotCreatable", "Service", "Deprecated", "NotReplicated", "PlayerReplicated"}
MEMBER_TAGS = {"Yields", "CanYield", "NoYield", "Hidden", "ReadOnly", "NotScriptable", "Deprecated"}

# WRIT23's arithmetic surface: the ops matrix ships rows for exactly these.
OPS_DATATYPES = ["Vector2", "Vector3", "Vector2int16", "Vector3int16", "CFrame", "UDim", "UDim2"]

# docs index exclusions; resources keeps only modules/ and feature-packages/
DOCS_EXCLUDE = ("education/", "production/", "creator-programs/")
RESOURCES_KEEP = ("resources/modules/", "resources/feature-packages/")

THROW_PATTERNS = [
    r"\bthrows?\b",
    r"\bwill throw\b",
    r"\bthrowing\b",
    r"\berror will be (?:generated|raised|thrown)\b",
    r"\ban error is (?:generated|raised|thrown)\b",
    r"\braises? an error\b",
    r"\bwill (?:error|raise)\b",
    r"\berrors? (?:if|when|upon|on)\b",
    r"\bresults? in an error\b",
]
THROW_RE = re.compile("|".join(THROW_PATTERNS), re.IGNORECASE)
NEGATION_RE = re.compile(r"\b(?:not|never|no|without|rather than)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)


def prose_throws(prose):
    """True when the prose documents a throw — negated mentions excluded
    ("will not error when...")."""
    for m in THROW_RE.finditer(prose):
        if not NEGATION_RE.search(prose[max(0, m.start() - 24):m.start()]):
            return True
    return False


def env_fail(cause, remedy):
    print("ENV|%s|%s" % (cause, remedy))
    sys.exit(3)


# ---------------------------------------------------------------- mini YAML --
# The creator-docs reference YAMLs are machine-generated and regular. This is a
# targeted parser for that subset, not a general YAML implementation: maps,
# lists of maps, block scalars (| and >, with - chomping), quoted scalars,
# inline [] and ''.


def _parse_scalar(s):
    s = s.strip()
    if s == "[]":
        return []
    if s == "{}":
        return {}
    if s in ("''", '""'):
        return ""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    if s == "null" or s == "~":
        return None
    return s


def parse_yaml(text):
    lines = []
    for raw in text.split("\n"):
        if raw.strip().startswith("#") and not lines:
            continue  # leading comment header
        lines.append(raw.rstrip("\n"))
    pos = [0]

    def indent_of(line):
        return len(line) - len(line.lstrip(" "))

    def skip_blank():
        while pos[0] < len(lines) and lines[pos[0]].strip() == "":
            pos[0] += 1

    def parse_block_scalar(indent):
        collected = []
        base = None
        while pos[0] < len(lines):
            line = lines[pos[0]]
            if line.strip() == "":
                collected.append("")
                pos[0] += 1
                continue
            ind = indent_of(line)
            if ind <= indent:
                break
            if base is None:
                base = ind
            collected.append(line[base:] if ind >= base else line.lstrip(" "))
            pos[0] += 1
        while collected and collected[-1] == "":
            collected.pop()
        return "\n".join(collected)

    def parse_map(indent):
        out = {}
        while pos[0] < len(lines):
            skip_blank()
            if pos[0] >= len(lines):
                break
            line = lines[pos[0]]
            ind = indent_of(line)
            if ind < indent or line.lstrip().startswith("- "):
                break
            if ind > indent:
                break  # malformed; stop rather than mis-nest
            body = line.strip()
            m = re.match(r"^([^:]+):(.*)$", body)
            if not m:
                pos[0] += 1
                continue
            key = _parse_scalar(m.group(1))
            rest = m.group(2).strip()
            pos[0] += 1
            if rest in ("|", "|-", "|+", ">", ">-", ">+"):
                out[key] = parse_block_scalar(indent)
            elif rest == "":
                skip_blank()
                if pos[0] < len(lines):
                    nxt = lines[pos[0]]
                    nind = indent_of(nxt)
                    if nind > indent and nxt.lstrip().startswith("- "):
                        out[key] = parse_list(nind)
                    elif nind > indent:
                        out[key] = parse_map(nind)
                    else:
                        out[key] = None
                else:
                    out[key] = None
            else:
                out[key] = _parse_scalar(rest)
        return out

    def parse_list(indent):
        out = []
        while pos[0] < len(lines):
            skip_blank()
            if pos[0] >= len(lines):
                break
            line = lines[pos[0]]
            ind = indent_of(line)
            if ind != indent or not line.lstrip().startswith("- "):
                break
            item_body = line.strip()[2:]
            item_indent = ind + 2
            if item_body == "":
                pos[0] += 1
                skip_blank()
                if pos[0] < len(lines) and indent_of(lines[pos[0]]) > ind:
                    out.append(parse_map(indent_of(lines[pos[0]])))
                else:
                    out.append(None)
            elif re.match(r"^[^:]+:(\s|$)", item_body) and not item_body.startswith("'") and not item_body.startswith('"'):
                # map item with first key inline: rewrite line as key at item_indent
                lines[pos[0]] = " " * item_indent + item_body
                out.append(parse_map(item_indent))
            else:
                out.append(_parse_scalar(item_body))
                pos[0] += 1
        return out

    skip_blank()
    return parse_map(indent_of(lines[pos[0]]) if pos[0] < len(lines) else 0)


_yaml_cache = {}


def load_yaml(path):
    if path not in _yaml_cache:
        try:
            with open(path, encoding="utf-8") as f:
                _yaml_cache[path] = parse_yaml(f.read())
        except OSError:
            _yaml_cache[path] = None
    return _yaml_cache[path]


# ------------------------------------------------------------------ helpers --

LINK_RE = re.compile(r"`?(?:Class|Enum|Datatype|Library|Global)\.([A-Za-z0-9_.:()]+?)(?:\|([^`]+?))?`")
TICK_RE = re.compile(r"`([^`]*)`")


def strip_markup(text):
    """Class.X|Y link markup stripped on the way out; backticks dropped."""
    if not text:
        return ""
    text = LINK_RE.sub(lambda m: m.group(2) if m.group(2) else m.group(1), text)
    text = TICK_RE.sub(r"\1", text)
    return text


def one_line(text):
    """Whitespace-collapsed, markup-stripped, pipe-safe field text."""
    text = strip_markup(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("|", "/")


def field(value):
    return value if value not in (None, "", []) else "void"


# ------------------------------------------------------------------- corpus --


def need_dump():
    if not os.path.exists(DUMP_PATH):
        env_fail("api-dump-absent", "api_dump --sync")


def need_docs():
    if not os.path.isdir(ENGINE):
        env_fail("creator-docs-absent", "api_dump --sync")


def docs_available():
    return os.path.isdir(ENGINE)


_dump = None


def load_dump():
    global _dump
    if _dump is None:
        with open(DUMP_PATH, encoding="utf-8") as f:
            _dump = json.load(f)
    return _dump


def classes_by_name():
    return {c["Name"]: c for c in load_dump()["Classes"]}


def ancestry(name, by_name):
    chain = []
    cur = by_name.get(name)
    while cur:
        sup = cur.get("Superclass")
        if not sup or sup == "<<<ROOT>>>":
            break
        chain.append(sup)
        cur = by_name.get(sup)
    return chain


def read_security(member):
    sec = member.get("Security", "None")
    if isinstance(sec, dict):
        return sec.get("Read", "None")
    return sec


def member_visible(member, lift):
    return lift or read_security(member) == "None"


def carried_tags(raw, keep):
    return [t for t in (raw or []) if isinstance(t, str) and t in keep]


def render_type(t):
    if isinstance(t, dict):
        name = t.get("Name", "void")
        if t.get("Category") == "Enum":
            return "Enum." + name
        return name
    return str(t)


def class_yaml(name):
    return load_yaml(os.path.join(ENGINE, "classes", name + ".yaml")) if docs_available() else None


def yaml_members(cy):
    """Member-name-keyed YAML entries for one class."""
    out = {}
    if not cy:
        return out
    for kind in ("properties", "methods", "events", "callbacks"):
        for entry in cy.get(kind) or []:
            if not isinstance(entry, dict):
                continue
            qual = entry.get("name", "")
            short = re.split(r"[.:]", qual)[-1] if qual else ""
            if short:
                out[short] = entry
    return out


# house overlay: human-ruled behavior the docs omit. member|behavior per line.
def load_overlay():
    out = {}
    if os.path.exists(OVERLAY_PATH):
        with open(OVERLAY_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|", 1)
                if len(parts) == 2:
                    out[parts[0].strip()] = parts[1].strip()
    return out


def overlay_for(class_name, member_name=None):
    ov = load_overlay()
    key = class_name if member_name is None else "%s:%s" % (class_name, member_name)
    hit = ov.get(key)
    if hit is None and member_name is not None:
        hit = ov.get("%s.%s" % (class_name, member_name))
    return hit


def summary_of(entry, dump_member=None):
    s = one_line(entry.get("summary")) if entry else ""
    dep = one_line(entry.get("deprecation_message")) if entry else ""
    if dep:
        s = (s + " - " + dep) if s else dep
    return s


def member_record(cls_name, m, ymembers, qualify=False):
    name = m["Name"]
    kind = m["MemberType"]
    entry = ymembers.get(name)
    prefix = cls_name if qualify else ""
    if kind == "Property":
        sig = "%s.%s" % (prefix, name)
        ret = render_type(m.get("ValueType"))
    elif kind == "Function":
        params = ",".join(
            "%s:%s%s" % (p.get("Name", ""), render_type(p.get("Type")), "=" + str(p["Default"]) if p.get("Default") not in (None, "") else "")
            for p in m.get("Parameters", [])
        )
        sig = "%s:%s(%s)" % (prefix, name, params)
        rt = m.get("ReturnType")
        if isinstance(rt, list):
            ret = ",".join(render_type(r) for r in rt) or "void"
        else:
            ret = render_type(rt) if rt else "void"
        if ret in ("null", "()", "Tuple"):
            ret = "void" if ret != "Tuple" else "Tuple"
    elif kind == "Event":
        params = ",".join("%s:%s" % (p.get("Name", ""), render_type(p.get("Type"))) for p in m.get("Parameters", []))
        sig = "%s.%s(%s)" % (prefix, name, params)
        ret = "RBXScriptSignal"
    else:  # Callback
        params = ",".join("%s:%s" % (p.get("Name", ""), render_type(p.get("Type"))) for p in m.get("Parameters", []))
        sig = "%s.%s(%s)" % (prefix, name, params)
        rt = m.get("ReturnType")
        ret = render_type(rt) if rt else "void"
    tags = carried_tags(m.get("Tags"), MEMBER_TAGS)
    sample = ""
    summary = ""
    if entry:
        cs = entry.get("code_samples") or []
        sample = cs[0] if cs else ""
        summary = summary_of(entry, m)
    house = overlay_for(cls_name, name)
    if house is not None:
        tags = tags + ["house"]
        summary = (summary + "; house: " + one_line(house)) if summary else "house: " + one_line(house)
    return "%s|%s|%s|%s|%s|%s" % (
        sig,
        field(ret),
        field(m.get("ThreadSafety", "")),
        field(",".join(tags)),
        field(sample),
        field(summary),
    )


def class_header(c, cy):
    name = c["Name"]
    by_name = classes_by_name()
    chain = ",".join(ancestry(name, by_name))
    tags = carried_tags(c.get("Tags"), CLASS_TAGS)
    sample = ""
    summary = ""
    if cy:
        cs = cy.get("code_samples") or []
        sample = cs[0] if cs else ""
        summary = summary_of(cy)
    house = overlay_for(name)
    if house is not None:
        tags = tags + ["house"]
        summary = (summary + "; house: " + one_line(house)) if summary else "house: " + one_line(house)
    return "%s|%s|%s|%s|%s" % (name, field(chain), field(",".join(tags)), field(sample), field(summary))


# -------------------------------------------------------------------- verbs --


def verb_class(name, lift, inherited=False):
    need_dump()
    by_name = classes_by_name()
    c = by_name.get(name)
    if c is None:
        print("miss|%s|no such class" % name)
        return
    cy = class_yaml(name)
    print(class_header(c, cy))
    todo = [c] + ([by_name[a] for a in ancestry(name, by_name) if a in by_name] if inherited else [])
    for cls in todo:
        ym = yaml_members(class_yaml(cls["Name"]))
        for m in cls.get("Members", []):
            if member_visible(m, lift):
                print(member_record(cls["Name"], m, ym, qualify=inherited and cls is not c))


def verb_props(name, lift):
    need_dump()
    c = classes_by_name().get(name)
    if c is None:
        print("miss|%s|no such class" % name)
        return
    ym = yaml_members(class_yaml(name))
    print(class_header(c, class_yaml(name)))
    for m in c.get("Members", []):
        if m["MemberType"] == "Property" and member_visible(m, lift):
            print(member_record(name, m, ym))


def verb_services():
    need_dump()
    names = sorted(c["Name"] for c in load_dump()["Classes"] if "Service" in (c.get("Tags") or []))
    print(",".join(names))


def enum_yaml(name):
    return load_yaml(os.path.join(ENGINE, "enums", name + ".yaml")) if docs_available() else None


def verb_enum(name, items=False):
    need_dump()
    enums = {e["Name"]: e for e in load_dump()["Enums"]}
    e = enums.get(name)
    if e is None:
        print("miss|%s|no such enum" % name)
        return
    ey = enum_yaml(name) or {}
    yitems = {i.get("name"): i for i in ey.get("items") or [] if isinstance(i, dict)}
    summary = one_line(ey.get("summary"))
    print("%s|void|%s|void|%s" % (name, field(",".join(carried_tags(e.get("Tags"), CLASS_TAGS))), field(summary)))
    if items:
        for it in e.get("Items", []):
            yi = yitems.get(it["Name"], {})
            tags = carried_tags(it.get("Tags"), MEMBER_TAGS)
            print(".%s|%s|void|%s|void|%s" % (it["Name"], it["Value"], field(",".join(tags)), field(one_line(yi.get("summary")))))


def library_yaml(name):
    return load_yaml(os.path.join(ENGINE, "libraries", name + ".yaml"))


def lib_member_records(name, ly, throws):
    for kind in ("properties", "functions"):
        for fn in ly.get(kind) or []:
            if not isinstance(fn, dict):
                continue
            qual = fn.get("name", "")
            short = qual.split(".")[-1]
            params = ",".join(
                "%s:%s%s"
                % (
                    p.get("name", ""),
                    re.sub(r"\s*\|\s*", "|", str(p.get("type", ""))),
                    "=" + str(p["default"]) if p.get("default") not in (None, "") else "",
                )
                for p in fn.get("parameters") or []
                if isinstance(p, dict)
            )
            if kind == "functions":
                sig = ".%s(%s)" % (short, params)
                rets = [r.get("type", "") for r in fn.get("returns") or [] if isinstance(r, dict)]
                ret = ",".join(r for r in rets if r) or "void"
                if ret == "()":
                    ret = "void"
            else:
                sig = ".%s" % short
                ret = fn.get("type", "void")
            tags = [t for t in fn.get("tags") or [] if isinstance(t, str)]
            if qual in throws:
                tags.append("Throws")
            ts = fn.get("thread_safety", "")
            yield "%s|%s|%s|%s|void|%s" % (sig, field(ret), field(ts), field(",".join(tags)), field(one_line(fn.get("summary"))))


def verb_library(name):
    need_docs()
    ly = library_yaml(name)
    if not ly:
        print("miss|%s|no such library" % name)
        return
    throws = synth_throws_libraries()
    print("%s|void|%s|void|%s" % (name, field(",".join(t for t in ly.get("tags") or [] if isinstance(t, str))), field(one_line(ly.get("summary")))))
    for rec in lib_member_records(name, ly, throws):
        print(rec)


def datatype_yaml(name):
    return load_yaml(os.path.join(ENGINE, "datatypes", name + ".yaml"))


def ops_rows(name):
    """Doc rows as-is, then number-side rows synthesized for * / // by
    position — `2 / v3` is not `v3 / 2` reversed. Any other undocumented pair
    stays invisible until tested in Studio; do not "fix" this back to a
    straight parse."""
    dy = datatype_yaml(name)
    if not dy:
        return []
    rows = []
    for op in dy.get("math_operations") or []:
        if not isinstance(op, dict):
            continue
        rows.append((op.get("operation", ""), op.get("type_a", ""), op.get("type_b", ""), op.get("return_type", ""), "doc"))
    synth = []
    for o, a, b, r, _ in rows:
        if o in ("*", "/", "//") and b == "number" and a != "number":
            synth.append((o, "number", a, r, "syn"))
    return rows + synth


def verb_ops(name):
    need_docs()
    rows = ops_rows(name)
    if not rows:
        print("miss|%s|no math_operations" % name)
        return
    for o, a, b, r, src in rows:
        print("%s|%s|%s|%s|%s" % (field(o), field(a), field(b), field(r), src))


def verb_describe(spec):
    need_docs()
    m = re.match(r"^([A-Za-z0-9_]+)[.:]([A-Za-z0-9_]+)$", spec)
    if not m:
        print("miss|%s|expected Class.Member" % spec)
        return
    cls, member = m.group(1), m.group(2)
    need_dump()
    c = classes_by_name().get(cls)
    ym = yaml_members(class_yaml(cls))
    entry = ym.get(member)
    if c is None or entry is None:
        print("miss|%s|not in corpus" % spec)
        return
    dm = next((x for x in c.get("Members", []) if x["Name"] == member), None)
    if dm is not None:
        print(member_record(cls, dm, ym))
    desc = strip_markup(entry.get("description") or "").strip()
    if desc:
        print(desc)


def verb_find(terms, lift):
    need_dump()
    terms = [t.lower() for t in terms if t]
    if not terms:
        print("miss|void|no terms")
        return
    scored = []

    def score(name, summary):
        s = 0
        lname, lsum = name.lower(), (summary or "").lower()
        for t in terms:
            if t in lname:
                s += 3
            s += lsum.count(t)
        return s

    by_name = classes_by_name()
    for cname, c in by_name.items():
        cy = class_yaml(cname)
        csum = one_line(cy.get("summary")) if cy else ""
        sc = score(cname, csum)
        if sc > 0:
            scored.append((sc, 0, ("class", c, cy, None)))
        ym = yaml_members(cy)
        for m in c.get("Members", []):
            if not member_visible(m, lift):
                continue
            entry = ym.get(m["Name"])
            msum = summary_of(entry, m) if entry else ""
            sc = score(m["Name"], msum)
            if sc > 0:
                scored.append((sc, 1, ("member", cname, m, ym)))
    for e in load_dump()["Enums"]:
        ey = enum_yaml(e["Name"]) or {}
        sc = score(e["Name"], one_line(ey.get("summary")))
        if sc > 0:
            scored.append((sc, 2, ("enum", e, ey, None)))
    scored.sort(key=lambda x: (-x[0], x[1]))
    for _, _, hit in scored[:20]:
        if hit[0] == "class":
            print(class_header(hit[1], hit[2]))
        elif hit[0] == "member":
            print(member_record(hit[1], hit[2], hit[3], qualify=True))
        else:
            e, ey = hit[1], hit[2]
            print("%s|void|%s|void|%s" % (e["Name"], field(",".join(carried_tags(e.get("Tags"), CLASS_TAGS))), field(one_line(ey.get("summary")))))


# ---------------------------------------------------------------- doc verbs --


def front_matter(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None, ""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not m:
        return None, text
    fm = {}
    for line in m.group(1).split("\n"):
        km = re.match(r"^(title|description):\s*(.*)$", line)
        if km:
            fm[km.group(1)] = _parse_scalar(km.group(2))
    return fm, text[m.end():]


def build_docs_index():
    """Build the generated index in memory. Only --sync installs it."""
    index = []
    for root, _, files in os.walk(CONTENT):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, CONTENT).replace(os.sep, "/")
            if rel.startswith(DOCS_EXCLUDE):
                continue
            if rel.startswith("resources/") and not rel.startswith(RESOURCES_KEEP):
                continue
            fm, _ = front_matter(full)
            if not fm or "title" not in fm:
                continue
            index.append({"path": rel, "title": str(fm.get("title", "")), "description": str(fm.get("description", ""))})
    return index


def install_docs_index(index):
    temporary = DOCS_INDEX + ".%d.tmp" % os.getpid()
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(index, f)
        f.write("\n")
    os.replace(temporary, DOCS_INDEX)


def docs_index():
    try:
        with open(DOCS_INDEX, encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, ValueError, UnicodeError):
        env_fail("docs-index-absent-or-malformed", "run api_dump --sync to rebuild the local docs index")
    if not isinstance(index, list):
        env_fail("docs-index-malformed", "run api_dump --sync to rebuild the local docs index")
    return index


def verb_docs(terms):
    need_docs()
    index = docs_index()
    if not isinstance(index, list):
        env_fail("docs-index-malformed", "api_dump --sync")
    terms = [t.lower() for t in terms if t]
    scored = []
    for entry in index:
        s = 0
        for t in terms:
            if t in entry["title"].lower():
                s += 3
            if t in entry["description"].lower():
                s += 1
            if t in entry["path"].lower():
                s += 1
        if s > 0:
            scored.append((s, entry))
    scored.sort(key=lambda x: -x[0])
    for _, entry in scored[:20]:
        print("%s|%s|%s" % (entry["path"], field(one_line(entry["title"])), field(one_line(entry["description"]))))


def slugify(heading):
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def doc_headings(body):
    return [m.group(2).strip() for m in re.finditer(r"^(#{1,4})\s+(.+)$", body, re.MULTILINE)]


def verb_doc(spec):
    need_docs()
    if "#" in spec:
        rel, anchor = spec.split("#", 1)
    else:
        rel, anchor = spec, None
    full = os.path.join(CONTENT, rel)
    if not os.path.exists(full):
        print("miss|%s|no such doc" % rel)
        return
    _, body = front_matter(full)
    if anchor is None and len(body.encode()) >= 20 * 1024:
        heads = [slugify(h) for h in doc_headings(body)]
        print("%s|%dKB|%s" % (rel, len(body.encode()) // 1024, field(",".join(heads))))
        return
    if anchor:
        lines = body.split("\n")
        out, level, capturing = [], None, False
        for line in lines:
            m = re.match(r"^(#{1,4})\s+(.+)$", line)
            if m:
                if capturing and len(m.group(1)) <= level:
                    break
                if slugify(m.group(2)) == anchor:
                    capturing = True
                    level = len(m.group(1))
            if capturing:
                out.append(line)
        if not out:
            print("miss|%s#%s|no such heading" % (rel, anchor))
            return
        body = "\n".join(out)
    sys.stdout.write(body if body.endswith("\n") else body + "\n")


def verb_code(spec):
    need_docs()
    full = os.path.join(CONTENT, spec)
    if not os.path.exists(full):
        print("miss|%s|no such doc" % spec)
        return
    _, body = front_matter(full)
    blocks = re.findall(r"```(?:lua|luau)\n(.*?)```", body, re.DOTALL)
    for i, block in enumerate(blocks, 1):
        print("%s#%d|api-evidence" % (spec, i))
        sys.stdout.write(block if block.endswith("\n") else block + "\n")


# ------------------------------------------------------------------- sample --


def verb_sample(spec):
    """YAML indexes, the rendered page holds the body. Empty code_samples means
    no sample and NO network. Fails soft: no connection -> no sample -> never a
    blocked write."""
    need_docs()
    m = re.match(r"^([A-Za-z0-9_]+):([A-Za-z0-9_]+)$", spec)
    if not m:
        print("miss|%s|expected Class:Member" % spec)
        return
    cls, member = m.group(1), m.group(2)
    cy = class_yaml(cls)
    if not cy:
        print("miss|%s|no class yaml" % cls)
        return
    entry = yaml_members(cy).get(member)
    refs = (entry.get("code_samples") or []) if entry else []
    if not refs:
        return  # no sample declared; no network
    declared = set()
    for kind in ("properties", "methods", "events", "callbacks"):
        for e in cy.get(kind) or []:
            if isinstance(e, dict) and (e.get("code_samples") or []):
                declared.add(re.split(r"[.:]", e.get("name", ""))[-1])
    cached = fetch_class_samples(cls, declared)
    if cached is None:
        sys.stderr.write("WARN sample-fetch-failed %s - serving nothing, never blocking\n" % cls)
        return
    body = cached.get(member)
    if not body:
        return
    print("%s:%s|api-evidence" % (cls, member))
    for block in body:
        sys.stdout.write(block if block.endswith("\n") else block + "\n")


def fetch_class_samples(cls, declared_members):
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    cache_path = os.path.join(SAMPLES_DIR, cls + ".json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    url = "https://create.roblox.com/docs/reference/engine/classes/" + cls
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", "replace")
    except Exception:
        return None
    # fenced blocks live in the embedded JSON payload as escaped markdown;
    # associate each to the nearest preceding member anchor.
    out = {}
    text = html.replace("\\n", "\n").replace('\\"', '"')
    pattern = re.compile(r"```lua\n(.*?)```", re.DOTALL)
    anchors = [(a.start(), a.group(1)) for a in re.finditer(r"\b([A-Za-z0-9_]+)\b", text) if a.group(1) in declared_members]
    for m in pattern.finditer(text):
        owner = None
        for pos, name in anchors:
            if pos < m.start():
                owner = name
            else:
                break
        if owner:
            out.setdefault(owner, []).append(m.group(1))
    expected = len(declared_members)
    if len(out) < expected:
        sys.stderr.write("WARN sample-anchor-parse %s: %d members extracted, %d declared\n" % (cls, len(out), expected))
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(out, f)
    except OSError:
        pass
    return out


# ---------------------------------------------------------- throws synthesis --


def _collapse(text):
    return re.sub(r"\s+", " ", text or "")


def synth_throws_classes():
    """Throws synthesized from documented prose — collapse whitespace before
    matching, the YAML wraps mid-phrase."""
    throws = set()
    if not docs_available():
        return throws
    cdir = os.path.join(ENGINE, "classes")
    for fn in sorted(os.listdir(cdir)):
        if not fn.endswith(".yaml"):
            continue
        cy = load_yaml(os.path.join(cdir, fn))
        if not cy:
            continue
        cls = cy.get("name", fn[:-5])
        for kind in ("properties", "methods", "events", "callbacks"):
            for e in cy.get(kind) or []:
                if not isinstance(e, dict):
                    continue
                prose = _collapse((e.get("summary") or "") + " " + (e.get("description") or ""))
                if prose_throws(prose):
                    short = re.split(r"[.:]", e.get("name", ""))[-1]
                    throws.add("%s:%s" % (cls, short))
    return throws


def synth_throws_libraries():
    throws = set()
    if not docs_available():
        return throws
    ldir = os.path.join(ENGINE, "libraries")
    for fn in sorted(os.listdir(ldir)):
        if not fn.endswith(".yaml"):
            continue
        ly = load_yaml(os.path.join(ldir, fn))
        if not ly:
            continue
        for kind in ("properties", "functions"):
            for e in ly.get(kind) or []:
                if not isinstance(e, dict):
                    continue
                prose = _collapse((e.get("summary") or "") + " " + (e.get("description") or ""))
                if prose_throws(prose):
                    throws.add(e.get("name", ""))
    return throws


# ------------------------------------------------------------- emit-globals --


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def emit_globals(updates_dir=None):
    need_dump()
    need_docs()
    dump = load_dump()
    services = sorted(c["Name"] for c in dump["Classes"] if "Service" in (c.get("Tags") or []))
    notcreatable = sorted(c["Name"] for c in dump["Classes"] if "NotCreatable" in (c.get("Tags") or []))
    yields, canyield, safeish = [], [], []
    streaming = []
    for c in dump["Classes"]:
        for m in c.get("Members", []):
            key = "%s:%s" % (c["Name"], m["Name"])
            tags = m.get("Tags") or []
            if "Yields" in tags:
                yields.append(key)
            if "CanYield" in tags:
                canyield.append(key)
            ts = m.get("ThreadSafety")
            if ts in ("Safe", "ReadSafe"):
                safeish.append((key, ts))
        if c["Name"] in ("Workspace", "Model"):
            for m in c.get("Members", []):
                if m["MemberType"] == "Property" and "Stream" in m["Name"]:
                    sec = m.get("Security", "None")
                    sec_read = sec.get("Read") if isinstance(sec, dict) else sec
                    sec_write = sec.get("Write") if isinstance(sec, dict) else sec
                    ptags = list(m.get("Tags") or [])
                    if sec_write and sec_write != "None":
                        ptags.append(sec_write)
                    streaming.append((m["Name"], c["Name"], ",".join(ptags)))
    by_name = {c["Name"]: c for c in dump["Classes"]}
    constraints = sorted(c["Name"] for c in dump["Classes"] if "Constraint" in ancestry(c["Name"], by_name))
    bodymovers = sorted(c["Name"] for c in dump["Classes"] if "BodyMover" in ancestry(c["Name"], by_name))
    class_throws = synth_throws_classes()
    lib_throws = synth_throws_libraries()
    all_throws = sorted(class_throws | lib_throws)
    ops = []
    for dt in OPS_DATATYPES:
        ops.extend(ops_rows(dt))
    doc_ops = sum(1 for r in ops if r[4] == "doc")
    updates = {}
    if updates_dir and os.path.isdir(updates_dir):
        for fn in sorted(os.listdir(updates_dir)):
            if not fn.endswith((".lua", ".luau")) or fn in ("init.lua", "init.luau"):
                continue
            try:
                with open(os.path.join(updates_dir, fn), encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            dm = re.search(r'ReleaseDate\s*=\s*"([^"]+)"', text)
            if dm:
                updates[os.path.splitext(fn)[0]] = dm.group(1)

    lines = ["-- generated by api_dump --emit-globals; regenerated by session-gate, never at write time", "return {"]
    lines.append("\tservices = { " + ", ".join(lua_str(s) for s in services) + " },")
    lines.append("\tnotcreatable = {")
    for n in notcreatable:
        lines.append("\t\t[%s] = true," % lua_str(n))
    lines.append("\t},")
    lines.append("\tconstraints = {")
    for n in constraints:
        lines.append("\t\t[%s] = true," % lua_str(n))
    lines.append("\t},")
    lines.append("\tbodymovers = {")
    for n in bodymovers:
        lines.append("\t\t[%s] = true," % lua_str(n))
    lines.append("\t},")
    lines.append("\tyields = {")
    for k in sorted(yields):
        lines.append("\t\t[%s] = true," % lua_str(k))
    lines.append("\t},")
    lines.append("\tcanyield = {")
    for k in sorted(canyield):
        lines.append("\t\t[%s] = true," % lua_str(k))
    lines.append("\t},")
    lines.append("\tthrows = {")
    for k in all_throws:
        lines.append("\t\t[%s] = true," % lua_str(k))
    lines.append("\t},")
    lines.append("\tthreadsafe = {")
    for k, ts in sorted(safeish):
        lines.append("\t\t[%s] = %s," % (lua_str(k), lua_str(ts)))
    lines.append("\t},")
    lines.append("\tstreaming = {")
    for name, cls, tags in sorted(streaming):
        lines.append("\t\t[%s] = { class = %s, tags = %s }," % (lua_str(name), lua_str(cls), lua_str(tags)))
    lines.append("\t},")
    lines.append("\tops = {")
    for o, a, b, r, src in ops:
        lines.append(
            "\t\t{ op = %s, a = %s, b = %s, ret = %s, src = %s }," % (lua_str(o), lua_str(a), lua_str(b), lua_str(r), lua_str(src))
        )
    lines.append("\t},")
    lines.append("\tupdates = {")
    for k, v in sorted(updates.items()):
        lines.append("\t\t[%s] = %s," % (lua_str(k), lua_str(v)))
    lines.append("\t},")
    lines.append("}")
    os.makedirs(CACHE, exist_ok=True)
    tmp = GLOBALS_PATH + ".%d.tmp" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, GLOBALS_PATH)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    print("%s|%dc|%ds|%dops|%dthrows" % (GLOBALS_PATH, len(dump["Classes"]), len(services), doc_ops, len(all_throws)))


def check_overlay():
    """Every house-overlay entry still names a live class or member."""
    need_dump()
    by_name = classes_by_name()
    dead = []
    for key in load_overlay():
        m = re.match(r"^([A-Za-z0-9_]+)(?:[.:]([A-Za-z0-9_]+))?$", key)
        if not m:
            dead.append(key)
            continue
        cls, member = m.group(1), m.group(2)
        c = by_name.get(cls)
        if c is None:
            dead.append(key)
        elif member and not any(x["Name"] == member for x in c.get("Members", [])):
            dead.append(key)
    for k in dead:
        print("overlay|%s|dead" % k)
    sys.exit(2 if dead else 0)


# --------------------------------------------------------------------- sync --


def sync():
    state, detail = gatelib.corpus_status()
    if state == "fresh":
        print("sync|fresh|no network or Creator Docs Git writes")
        return 0
    if state == "malformed":
        print("sync|repairing-malformed|%s" % one_line(detail))

    os.makedirs(CACHE, exist_ok=True)
    tmp = DUMP_PATH + ".%d.tmp" % os.getpid()
    try:
        req = urllib.request.Request(DUMP_URL, headers={"User-Agent": "harness/api_dump"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        dump = json.loads(data)
        if not isinstance(dump, dict) or not isinstance(dump.get("Classes"), list) or not isinstance(dump.get("Enums"), list):
            env_fail("api-dump-malformed", "retry api_dump --sync after the upstream response is valid")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, DUMP_PATH)
        print("dump|synced|%d bytes" % len(data))
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        env_fail("api-dump-sync-failed", "check network/cache permission, then retry api_dump --sync: %s" % str(e)[:120])

    git_environment = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_OPTIONAL_LOCKS="0")
    if not os.path.isdir(os.path.join(DOCS_ROOT, ".git")):
        clone_root = DOCS_ROOT + ".sync-%d" % os.getpid()
        shutil.rmtree(clone_root, ignore_errors=True)
        r = subprocess.run(
            ["git", "clone", "--depth", "1", DOCS_URL, clone_root],
            capture_output=True,
            text=True,
            env=git_environment,
        )
        if r.returncode != 0:
            shutil.rmtree(clone_root, ignore_errors=True)
            env_fail("creator-docs-sync-failed", "check network/cache permission, then retry api_dump --sync")
        quarantine = ""
        if os.path.exists(DOCS_ROOT):
            quarantine = DOCS_ROOT + ".malformed-%d" % int(time.time())
            try:
                os.replace(DOCS_ROOT, quarantine)
            except OSError as e:
                shutil.rmtree(clone_root, ignore_errors=True)
                env_fail("creator-docs-sync-failed", "could not quarantine malformed cache: %s" % str(e)[:120])
        try:
            os.replace(clone_root, DOCS_ROOT)
        except OSError as e:
            if quarantine and not os.path.exists(DOCS_ROOT):
                try:
                    os.replace(quarantine, DOCS_ROOT)
                except OSError:
                    pass
            shutil.rmtree(clone_root, ignore_errors=True)
            env_fail("creator-docs-sync-failed", "could not install repaired cache: %s" % str(e)[:120])
        print("docs|cloned|" + DOCS_ROOT)
    else:
        if state == "malformed":
            restored = subprocess.run(
                ["git", "-C", DOCS_ROOT, "restore", "--source=HEAD", "--worktree", "--", "."],
                capture_output=True,
                text=True,
                env=git_environment,
            )
            if restored.returncode != 0:
                env_fail("creator-docs-sync-failed", "could not restore malformed generated docs cache")
        r = subprocess.run(
            ["git", "-C", DOCS_ROOT, "pull", "--ff-only", "--deepen", "50"],
            capture_output=True,
            text=True,
            env=git_environment,
        )
        if r.returncode != 0:
            env_fail("creator-docs-sync-failed", "check network/cache permission, then retry api_dump --sync")
        print("docs|synced|" + DOCS_ROOT)

    index = build_docs_index()
    install_docs_index(index)
    print("index|rebuilt|%d files" % len(index))
    asset_error = gatelib.corpus_assets_error()
    if asset_error:
        env_fail("corpus-malformed", asset_error)
    temporary = REFRESH_PATH + ".%d.tmp" % os.getpid()
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump({"refreshed_at": time.time()}, f, sort_keys=True)
        f.write("\n")
    os.replace(temporary, REFRESH_PATH)
    print("refresh|successful|%d" % int(time.time()))
    return 0


# --------------------------------------------------------------------- main --


def main(argv):
    args = [a for a in argv if a != "--all"]
    lift = "--all" in argv
    if not args:
        print(__doc__.strip())
        return 0
    verb = args[0]
    rest = args[1:]
    if verb == "--sync":
        return sync()
    elif verb == "--emit-globals":
        updates = None
        if "--updates" in rest:
            i = rest.index("--updates")
            updates = rest[i + 1] if i + 1 < len(rest) else None
        emit_globals(updates)
    elif verb == "--check-overlay":
        check_overlay()
    elif verb == "class":
        verb_class(rest[0], lift)
    elif verb == "instance":
        verb_class(rest[0], lift, inherited=True)
    elif verb == "props":
        verb_props(rest[0], lift)
    elif verb == "services":
        verb_services()
    elif verb == "enum":
        verb_enum(rest[0], items=False)
    elif verb == "enumitems":
        verb_enum(rest[0], items=True)
    elif verb == "library":
        verb_library(rest[0])
    elif verb == "ops":
        verb_ops(rest[0])
    elif verb == "describe":
        verb_describe(rest[0])
    elif verb == "sample":
        verb_sample(rest[0])
    elif verb == "find":
        verb_find(rest, lift)
    elif verb == "docs":
        verb_docs(rest)
    elif verb == "doc":
        verb_doc(rest[0])
    elif verb == "code":
        verb_code(rest[0])
    else:
        print("miss|%s|unknown verb" % verb)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except BrokenPipeError:
        sys.exit(0)
    except Exception as e:  # crash is exit 2, distinct first token, nothing scanned
        sys.stderr.write("api_dump: CRASH %s: %s - nothing was scanned\n" % (type(e).__name__, e))
        sys.exit(2)
