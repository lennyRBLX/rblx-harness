"""Generate game-side reload commands for an audited flat-export module.

Offline only. Execute the generated Luau through the selected Studio connector.
Source snapshots and persistence belong to `studio source`.
"""
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio_source import generate, literal, parser_for, read_exact, side_guard, source_check, target_code


def asset_literal(path):
    source = read_exact(path)
    if "\r" in source:
        return literal(source)
    equals = "="
    while "]" + equals + "]" in source:
        equals += "="
    return "[" + equals + "[\n" + source + "]" + equals + "]"


def build(args):
    if (not args.session or len(args.session) > 48 or
            not all(c.isascii() and (c.isalnum() or c in "_-") for c in args.session)):
        raise ValueError("--session must be 1-48 ASCII letters, digits, underscores or hyphens")
    if args.side not in ("Server", "Client"):
        raise ValueError("Reload requires Server or Client")
    parent = 'game:GetService("ServerScriptService")' if args.side == "Server" else 'game:GetService("Players").LocalPlayer:WaitForChild("PlayerScripts", 5)'
    header = side_guard(args.side) + f'''local Parent = {parent}
assert(Parent, "Runtime container missing")
local Session = {literal(args.session)}
local Root = Parent:FindFirstChild({literal('__HarnessHotReload_' + args.session)})
'''
    if args.action == "bootstrap":
        assets = Path(__file__).resolve().parent
        runner_class = "Script" if args.side == "Server" else "LocalScript"
        return header + f'''if Root then
    assert(Root:GetAttribute("Session") == Session, "Name collision")
    return Root:GetAttributes()
end
Root = Instance.new("Folder")
Root.Name = {literal('__HarnessHotReload_' + args.session)}
Root:SetAttribute("Session", Session)
Root:SetAttribute("Status", "Booting")
local Core = Instance.new("ModuleScript")
Core.Name = "PatchCore"
Core.Source = {asset_literal(assets / 'PatchCore.luau')}
Core.Parent = Root
local Command = Instance.new("BindableFunction")
Command.Name = "Command"
Command.Parent = Root
local Runner = Instance.new({literal(runner_class)})
Runner.Name = "Runner"
Runner.Source = {asset_literal(assets / 'Bridge.server.luau')}
Runner.Parent = Root
Root.Parent = Parent
return Root:GetAttributes()
'''
    header += 'assert(Root and Root:GetAttribute("Session") == Session, "Bootstrap this side first")\n'
    if args.action == "poll":
        return header + "return Root:GetAttributes()\n"
    header += 'assert(Root:GetAttribute("Status") ~= "Booting", "Bridge is not ready")\n'
    header += target_code(args.path)
    header += 'assert(Target:IsA("ModuleScript"), "Target must be a ModuleScript")\n'
    if args.action == "status":
        return header + 'return Root.Command:Invoke({Action = "Status", Target = Target, Session = Session})\n'
    if args.action not in ("patch", "undo"):
        raise ValueError("Unknown reload action")
    if type(args.revision) is not int or args.revision < 0:
        raise ValueError("--revision must be the current nonnegative target revision")
    request_id = uuid.uuid4().hex
    request = f'''local Request = {{
    Action = {literal(args.action.title())}, Session = Session, Target = Target,
    ExpectedRevision = {args.revision}, RequestId = {literal(request_id)},
}}
'''
    if args.action == "undo":
        return header + request + "return Root.Command:Invoke(Request)\n"
    if not args.source or not args.expected or not args.audited:
        raise ValueError("patch requires --source, --expected and --audited after reviewing the module and callers")
    return header + request + source_check(args.expected) + f'''assert(Editor:GetEditorSource(Target) == Expected, "Editor draft differs; inspect before retrying")
assert(Target.Archivable, "Target is not Archivable")
local State = Root.Command:Invoke({{Action = "Status", Target = Target, Session = Session}})
assert(State.Revision == Request.ExpectedRevision, "Stale revision")
assert(State.Status ~= "Pending" and State.Status ~= "TimedOut", "Bridge unavailable")
assert(State.RetainedCandidates < State.CandidateLimit, "Candidate limit reached")
local Candidate = Target:Clone()
for _, Descendant in Candidate:GetDescendants() do
    if Descendant:IsA("BaseScript") then
        Candidate:Destroy()
        error("Executable descendants require a project adapter")
    end
end
Candidate.Name = {literal('__HotCandidate_' + request_id)}
Candidate:SetAttribute("HarnessHotReloadSession", Session)
Candidate.Source = {literal(read_exact(args.source))}
Candidate.Parent = Target.Parent
Request.Candidate = Candidate
local Success, Result = pcall(function() return Root.Command:Invoke(Request) end)
if not Success then
    Candidate:Destroy()
    error(Result)
end
return {{RequestId = Request.RequestId, Candidate = Candidate:GetFullName(), Accepted = Result.Accepted}}
'''


def main(argv=None):
    parser = parser_for(__doc__, ("bootstrap", "patch", "undo", "status", "poll"), ("Server", "Client"))
    parser.add_argument("--session", required=True, help="Unique ID per playtest")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--audited", action="store_true", help="Module and actual consumers meet the pure flat-export contract")
    return generate(parser, build, argv)


if __name__ == "__main__":
    raise SystemExit(main())
