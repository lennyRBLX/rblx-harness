local RunService = game:GetService("RunService")

assert(RunService:IsStudio() and RunService:IsRunning(), "Hot reload is for Studio playtests only")

local Root = script.Parent
local PatchCore = require(Root.PatchCore)
local Command = Root.Command
local Records = {}
local Retained = {}
local Busy = false
local Faulted = false
local GenerationLimit = 24

local function Report(RequestId, Status, Message)
	Root:SetAttribute("RequestId", RequestId)
	Root:SetAttribute("Message", Message)
	Root:SetAttribute("Status", Status)
end

local function Patch(Request)
	local Target = Request.Target
	local Candidate = Request.Candidate
	assert(typeof(Target) == "Instance" and Target:IsA("ModuleScript"), "Target must be a ModuleScript")
	assert(
		typeof(Candidate) == "Instance" and Candidate:IsA("ModuleScript"),
		"Candidate must be a ModuleScript"
	)
	assert(Target ~= Candidate and Target:IsDescendantOf(game), "Target must be a live module")
	assert(Candidate.Parent == Target.Parent, "Candidate must preserve the target's parent")
	assert(
		Candidate:GetAttribute("HarnessHotReloadSession") == Root:GetAttribute("Session"),
		"Unowned candidate"
	)

	for _, Descendant in Candidate:GetDescendants() do
		assert(not Descendant:IsA("BaseScript"), "Candidates cannot contain executable scripts")
	end

	local Record = Records[Target]
	local Revision = Record and Record.Revision or 0
	assert(Request.ExpectedRevision == Revision, "Stale reload revision")
	local Current = require(Target)
	local Expected = PatchCore.Snapshot(Current)

	if Record then
		assert(Current == Record.Export, "Module export identity changed")
		assert(PatchCore.Matches(Current, Record.After), "Exports changed outside the reloader")
	end

	local Fresh = require(Candidate)
	assert(Fresh ~= Current, "Candidate returned the original module; no reload performed")
	local Before, After = PatchCore.Replace(Current, Fresh, Record and Record.After or Expected)
	local NextRevision = Revision + 1
	Records[Target] = {
		Export = Current,
		Before = Before,
		After = After,
		Revision = NextRevision,
		CanUndo = true,
	}
	Root:SetAttribute("Revision", NextRevision)
	return "Updated " .. Target:GetFullName() .. " to revision " .. NextRevision
end

local function Undo(Request)
	local Record = Records[Request.Target]
	assert(Record and Record.CanUndo, "No undo available for this module")
	assert(Request.ExpectedRevision == Record.Revision, "Stale undo revision")
	PatchCore.Replace(Record.Export, Record.Before, Record.After)
	Record.After = table.clone(Record.Before)
	Record.Before = nil
	Record.CanUndo = false
	Record.Revision += 1
	Root:SetAttribute("Revision", Record.Revision)
	return "Restored exports; runtime source text is unchanged"
end

Command.OnInvoke = function(Request)
	assert(type(Request) == "table", "Request must be a table")
	assert(Request.Session == Root:GetAttribute("Session"), "Wrong session")

	if Request.Action == "Status" then
		local Record = Records[Request.Target]
		return {
			Status = Root:GetAttribute("Status"),
			Message = Root:GetAttribute("Message"),
			RequestId = Root:GetAttribute("RequestId"),
			Revision = Record and Record.Revision or 0,
			CanUndo = Record and Record.CanUndo or false,
			RetainedCandidates = #Retained,
			CandidateLimit = GenerationLimit,
			Side = RunService:IsServer() and "Server" or "Client",
		}
	end

	assert(not Faulted, "A request timed out; this bridge requires a new playtest")
	assert(not Busy, "A reload is already in progress")
	assert(Request.Action == "Patch" or Request.Action == "Undo", "Unknown action")
	assert(type(Request.RequestId) == "string", "RequestId is required")

	if Request.Action == "Patch" then
		assert(#Retained < GenerationLimit, "Session generation limit reached")
		assert(typeof(Request.Candidate) == "Instance", "Candidate is required")
		assert(
			Request.Candidate:GetAttribute("HarnessHotReloadSession") == Request.Session,
			"Unowned candidate"
		)
	end
	Busy = true
	Report(Request.RequestId, "Pending", Request.Action)

	local Finished = false
	local Worker
	Worker = task.defer(function()
		if Request.Action == "Patch" and typeof(Request.Candidate) == "Instance" then
			table.insert(Retained, Request.Candidate)
		end

		local Success, Message = pcall(function()
			if Request.Action == "Patch" then
				return Patch(Request)
			end

			return Undo(Request)
		end)
		Finished = true
		Busy = false
		Report(Request.RequestId, Success and "Applied" or "Failed", tostring(Message))
	end)

	task.delay(8, function()
		if Finished then
			return
		end

		Faulted = true
		Busy = false
		pcall(task.cancel, Worker)
		Report(Request.RequestId, "TimedOut", "Module yielded too long; no further reloads in this session")
	end)

	return {
		Accepted = true,
		RequestId = Request.RequestId,
	}
end

Root:SetAttribute("Side", RunService:IsServer() and "Server" or "Client")
Root:SetAttribute("Status", "Ready")
