"""Generate source snapshot/persistence commands; never connect to Studio.

Shared exact-source, path and side handling for Studio command generators.
"""
import argparse
import json
from pathlib import Path


def literal(value):
    """Encode UTF-8 bytes as Luau literals without JSON's unsupported escapes."""
    if isinstance(value, list):
        return "{" + ", ".join(literal(item) for item in value) + "}"
    return '"' + "".join(
        "\\%03d" % byte if byte < 32 or byte > 126 or byte in (34, 92) else chr(byte)
        for byte in value.encode("utf-8")
    ) + '"'


def read_exact(path):
    return Path(path).read_bytes().decode("utf-8")


def side_guard(side):
    if side not in ("Edit", "Server", "Client"):
        raise ValueError("Select Edit, Server or Client")
    guard = '''local RunService = game:GetService("RunService")
assert(RunService:IsStudio(), "Studio only")
'''
    if side == "Edit":
        return guard + 'assert(not RunService:IsRunning(), "Select stopped Edit")\n'
    return guard + f'''assert(RunService:IsRunning() and RunService:Is{side}(), "Select running {side}")
'''


def target_code(path):
    segments = json.loads(path) if isinstance(path, str) else path
    if not isinstance(segments, list) or not segments or not all(isinstance(x, str) and x for x in segments):
        raise ValueError("--path must be a JSON array of nonempty instance names")
    return f'''local Target = game
for _, Segment in {literal(segments)} do
    local Match
    for _, Child in Target:GetChildren() do
        if Child.Name == Segment then
            assert(not Match, "Ambiguous path segment: " .. Segment)
            Match = Child
        end
    end
    assert(Match, "Missing path segment: " .. Segment)
    Target = Match
end
'''


def source_check(expected):
    return f'''local Editor = game:GetService("ScriptEditorService")
local Expected = {literal(read_exact(expected))}
assert(Target.Source == Expected, "Stored source changed; inspect before retrying")
'''


def build(args):
    if args.action == "persist" and (args.side != "Edit" or not all((args.source, args.expected, args.expected_editor))):
        raise ValueError("persist requires stopped Edit, --source, --expected and --expected-editor")
    header = side_guard(args.side) + target_code(args.path)
    header += 'assert(Target:IsA("LuaSourceContainer"), "Target must contain source")\n'
    if args.action == "snapshot":
        return header + '''local Editor = game:GetService("ScriptEditorService")
return {Path = Target:GetFullName(), Stored = Target.Source, Editor = Editor:GetEditorSource(Target)}
'''
    if args.action != "persist":
        raise ValueError("Unknown source action")
    return header + source_check(args.expected) + f'''local ExpectedEditor = {literal(read_exact(args.expected_editor))}
local NewSource = {literal(read_exact(args.source))}
assert(Editor:GetEditorSource(Target) == ExpectedEditor, "Editor draft changed; inspect before retrying")
Editor:UpdateSourceAsync(Target, function(Current)
    if Current ~= ExpectedEditor or Target.Source ~= Expected then
        return nil
    end
    return NewSource
end)
assert(Editor:GetEditorSource(Target) == NewSource, "Editor update was not applied")
assert(Target.Source == Expected or Target.Source == NewSource, "Stored source changed during edit")
if Target.Source ~= NewSource then
    Target.Source = NewSource
end
assert(Target.Source == NewSource and Editor:GetEditorSource(Target) == NewSource, "Source verification failed")
return {{Path = Target:GetFullName(), StoredMatches = true, EditorMatches = true}}
'''


def parser_for(description, actions, sides):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("action", choices=actions)
    parser.add_argument("--side", choices=sides, required=True)
    paths = parser.add_mutually_exclusive_group()
    paths.add_argument("--path", help="JSON array of exact instance names")
    paths.add_argument("--path-file", type=Path, help="JSON path file; avoids shell escaping")
    parser.add_argument("--source", type=Path, help="Reviewed new source file")
    parser.add_argument("--expected", type=Path, help="Exact stored source snapshot")
    parser.add_argument("--output", type=Path, required=True, help="Generated Luau; execution is separate")
    return parser


def generate(parser, builder, argv=None):
    args = parser.parse_args(argv)
    try:
        if args.path_file:
            args.path = read_exact(args.path_file)
        command = builder(args)
        inputs = (args.source, args.expected, args.path_file, getattr(args, "expected_editor", None))
        if any(path and args.output.resolve() == path.resolve() for path in inputs):
            raise ValueError("--output must not overwrite an input source or snapshot")
        args.output.write_text(command, encoding="utf-8", newline="\n")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Generated {args.action} for {args.side}: {args.output}")
    return 0


def main(argv=None):
    parser = parser_for(__doc__, ("snapshot", "persist"), ("Edit", "Server", "Client"))
    parser.add_argument("--expected-editor", type=Path, help="Exact editor draft snapshot for persist")
    return generate(parser, build, argv)


if __name__ == "__main__":
    raise SystemExit(main())
