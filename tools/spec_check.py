import json, re, sys
RULES, PLAN = "rules.json", "plan.revised.md"
ID = r'`((?:BC|WRIT|DATA|DEBUG|OPT|REV|TYPE|DES|GATE|OUT)\d+)`(?:\((\w[\w-]*)\))?'
SECT = {'CORE.md': r'### `CORE\.md`', '`style_assess` lint': r'- \*\*`style_assess`\*\*',
  '`style_assess --fix`': r'- \*\*`style_assess`\*\*', '`deny_scan`': r'- \*\*`deny_scan`\*\*',
  '`replication_audit`': r'- \*\*`replication_audit`\*\*', '`perf_audit`': r'- \*\*`perf_audit`\*\*',
  '`map_census`': r'- \*\*`map_census`\*\*', '`frame_census`': r'- \*\*`frame_census`\*\*',
  '`write-gate`': r'### `write-gate`', '`done-gate`': r'### `done-gate`',
  '`compact-gate`': r'### `compact-gate`', '`record_check`': r'### `record_check`',
  'deny': r'## Denies', '`roblox-writer` skill': r'### `roblox-writer`',
  '`roblox-new-game` skill': r'### `roblox-new-game`', 'debugger def': r'### `debugger`',
  'optimizer def': r'### `optimizer`', 'reviewer def': r'### `reviewer`'}
acc = {x['id'] for x in json.load(open(RULES))['rules'] if x['status'] == 'accepted'}
t = open(PLAN).read(); i = t.index('| Destination | Rules |'); body = t[:i]
rows = re.search(r'\| Destination \| Rules \|\n\|---\|---\|\n((?:\|.*\n)+)', t[i:]).group(1)
HEAD = re.compile(r'^(?:### |## |- \*\*`)', re.M)
pairs, orphans = [], []
for row in rows.strip().split('\n'):
    c = row.split('|'); dest = c[1].strip(); found = re.findall(ID, c[2])
    pairs += [(r, l or '') for r, l in found]
    if dest not in SECT: continue
    m = re.search(SECT[dest], body); n = HEAD.search(body, m.end())
    sec = body[m.start(): n.start() if n else len(body)]
    orphans += [(dest, r) for r, _ in found if not re.search(r'\b' + r + r'\b', sec)]
ids = [p[0] for p in pairs]
dupes = sorted(p for p in set(pairs) if pairs.count(p) > 1)
missing, extra = sorted(acc - set(ids)), sorted(set(ids) - acc)
print(f"coverage {len(pairs)} pairs · {len(set(ids))} unique · {len(acc)} accepted")
print(f"missing {missing} · extra {extra} · id+clause dupes {dupes or 'none'}")
print(f"orphan   {orphans or 'clean'}")
sys.exit(1 if (missing or extra or dupes or orphans) else 0)
