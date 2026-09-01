--[[
Updates:
	The content-drop lifecycle driver (KNOWLEDGE_BASIS §3.6). Each direct child
	module is a self-contained update carrying ReleaseDate + Start(silent) +
	Destroy + Events. Content is cumulative and permanent once shipped — only
	featuring rotates: every released update Starts (silently when it is not
	the latest), only the latest runs its event layer, and the previously
	featured one is Destroy()-ed.

	The started/featured set replicates as BoolValues under a
	ReplicatedStorage.Updates folder (true = featured, false = content only) —
	Folder + ValueObjects per KNOWLEDGE_BASIS §3.4. New updates come from
	create_boilerplate (kind: update); ship one with the ship-update skill.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local m = {
	Ran = false,

	Events = {},

	__modules = {},

	Started = {},
	Active = {}
}

local stateFolder = nil

-- privates
local function shouldBeActive(updateData)
	if not updateData.ReleaseDate or workspace:GetServerTimeNow() < updateData.ReleaseDate then
		return false
	end

	return true
end

local function replicateState(name, featured)
	local state = stateFolder:FindFirstChild(name) or Instance.new("BoolValue")
	state.Value = featured
	if not state.Parent then
		state.Name = name
		state.Parent = stateFolder
	end
end

function m:update()
	local latest, t = nil, 0
	for name, s in pairs(self.__modules) do
		local releaseT = s.ReleaseDate
		if releaseT and releaseT >= t and shouldBeActive(s) then
			t = releaseT
			latest = name
		end
	end

	-- deactivate the previously featured update
	for name, s in pairs(self.__modules) do
		if latest ~= name and self.Active[name] then
			local success, msg = pcall(s.Destroy, s)
			if not success then
				warn("FAILED TO DESTROY UPDATE '" .. name .. "'; ERROR:", msg)
			end

			self.Active[name] = false
			replicateState(name, false)
		end
	end

	-- start newly-eligible updates (silent unless featured)
	for name, s in pairs(self.__modules) do
		local active = latest == name
		if s.ReleaseDate and not self.Started[name] and (shouldBeActive(s) or active) then
			local success, err = pcall(s.Start, s, not active)
			if not success then
				warn("FAILED TO START UPDATE '" .. name .. "' ERROR:", err)
			end

			self.Started[name] = true
			self.Active[name] = active
			replicateState(name, active)
		end
	end
end

-- functions
function m:IsActive(name)
	return self.Active[name] == true
end

function m:Start()
	stateFolder = ReplicatedStorage:FindFirstChild("Updates") or Instance.new("Folder")
	if not stateFolder.Parent then
		stateFolder.Name = "Updates"
		stateFolder.Parent = ReplicatedStorage
	end

	for _, module in pairs(script:GetChildren()) do
		local e, msg = pcall(require, module)
		if not e then
			warn("ERROR WHILE REQUIRING UPDATE '" .. module.Name .. "'; ERROR:", msg)
			continue
		elseif not msg.Destroy then
			warn("UPDATE '" .. module.Name .. "' MISSING :Destroy")
		elseif not msg.ReleaseDate then
			warn("UPDATE '" .. module.Name .. "' MISSING .ReleaseDate")
		end

		if msg.Events then
			self.Events[module.Name] = msg.Events
		end

		self.__modules[module.Name] = msg
	end

	self:update()
	self.Ran = true

	task.spawn(function()
		while shared.Running do
			self:update()
			task.wait(30)
		end
	end)
end

return m
