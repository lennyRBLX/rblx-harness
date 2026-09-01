"""House output conventions shared by the Python tool wrappers.

Findings are records: line|col|id|subject|remedy, grouped under elided path
headers, sorted by line/col/id. Paths keep the root, the last two directories,
and the filename; the dot count is how many directories were elided; places/
drops and the place becomes the root.
"""

import os


def elide(path, root):
    """House path elision. `path` absolute or root-relative; `root` the
    project root."""
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except ValueError:
        rel = path
    rel = rel.replace(os.sep, "/")
    parts = [p for p in rel.split("/") if p and p != "."]
    if not parts:
        return rel
    if parts[0] == "places" and len(parts) >= 2:
        parts = parts[1:]  # place name becomes the root
    head, dirs, fname = parts[0], parts[1:-1], parts[-1]
    if len(parts) == 1:
        return parts[0]
    keep = dirs[-2:]
    elided = len(dirs) - len(keep)
    if elided <= 0:
        return "/".join([head] + dirs + [fname])
    return "/".join([head, "." * elided] + keep + [fname])


def render_findings(tool, findings, root, blocked=True, pre_lines=None):
    """findings: list of (path, line, col, id, subject, remedy).
    Returns the full output text, or "" when there is nothing to say."""
    out = []
    if pre_lines:
        out.extend(pre_lines)
    if not findings:
        return "\n".join(out) + ("\n" if out else "")
    if blocked:
        out.append("%s: BLOCKED" % tool)
        out.append("")
    by_path = {}
    order = []
    for f in findings:
        if f[0] not in by_path:
            by_path[f[0]] = []
            order.append(f[0])
        by_path[f[0]].append(f)
    for path in order:
        out.append(elide(path, root) + ":")
        out.append("")
        rows = sorted(by_path[path], key=lambda f: (f[1], f[2], f[3]))
        for _, line, col, fid, subject, remedy in rows:
            out.append("%d|%d|%s|%s|%s" % (line, col, fid, subject, remedy))
        out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"
